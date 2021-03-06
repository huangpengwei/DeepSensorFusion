import torch
import torch.utils.data
import scipy.io
import scipy.signal
import numpy as np
import skimage.transform
import matplotlib.pyplot as plt
np.set_printoptions(threshold=np.nan)
np.seterr(all='raise')

class ToTensor(object):
    """Crop randomly the image in a sample.

    Args:
        output_size (tuple or int): Desired output size. If int, square crop
            is made.
    """

    def __init__(self):
        pass

    def __call__(self, sample):
        rates, spad, bins_hr, intensity, bins = sample['rates'],\
                                                sample['spad'],\
                                                sample['bins_hr'],\
                                                sample['intensity'],\
                                                sample['bins']
        sins = sample['signal_ppp']
        coates = torch.from_numpy(sample['coates'])
        med = torch.from_numpy(sample['med'])
        rates = torch.from_numpy(rates)
        spad = torch.from_numpy(spad)
        bins_hr = torch.from_numpy(bins_hr)
        intensity = torch.from_numpy(intensity)
        bins = torch.from_numpy(bins)
        sins = torch.from_numpy(sins)
        return {'rates': rates, 'spad': spad,
                'bins_hr': bins_hr, 'bins': bins,
                'intensity': intensity, 'signal_ppp':sins,'coates': coates, 'med': med}


class RandomCrop(object):
    """Crop randomly the image in a sample.

    Args:
        output_size (tuple or int): Desired output size. If int, square crop
            is made.
    """

    def __init__(self, output_size, intensity_scale=1):
        self.output_size = output_size
        self.intensity_scale = intensity_scale

    def __call__(self, sample):
        rates, spad, bins_hr, intensity, bins = sample['rates'],\
                                                sample['spad'],\
                                                sample['bins_hr'],\
                                                sample['intensity'],\
                                                sample['bins']
        sins = sample['signal_ppp']
        coates = sample['coates']

        h, w = spad.shape[2:]
        new_h = self.output_size
        new_w = self.output_size
        iscale = self.intensity_scale

        top = np.random.randint(0, h - new_h)
        left = np.random.randint(0, w - new_w)

        med = sample['med'][:, top: top + new_h, left: left + new_w]

        rates = rates[:, :, top: top + new_h,
                      left: left + new_w]
        # handle spad differently due to weirdness
        spad = spad[:, :, top: top + new_h,
                    left: left + new_w]
        bins_hr = bins_hr.squeeze()[8*top: 8*top + 8*new_h,
                                    8*left: 8*left + 8*new_w]
        bins_hr = skimage.transform.resize(bins_hr,
                                           (iscale * self.output_size,
                                            iscale * self.output_size),
                                           mode='constant')
        bins_hr = bins_hr.reshape([1, iscale * self.output_size,
                                   iscale * self.output_size])
        bins = bins[:, top: top + new_h,
                    left: left + new_w]
        sins = sins[:, top: top + new_h,
                    left: left + new_w]
        coates = coates[:, top: top + new_h,
                        left: left + new_w]
        intensity = intensity.squeeze()[8*top: 8*top + 8*new_h,
                                        8*left: 8*left + 8*new_w]
        intensity = skimage.transform.resize(intensity,
                                             (iscale * self.output_size,
                                              iscale * self.output_size),
                                             mode='constant')
        intensity = intensity.reshape([1, iscale * self.output_size,
                                       iscale * self.output_size])

        return {'rates': rates, 'spad': spad,
                'bins_hr': bins_hr, 'bins': bins,
                'intensity': intensity, 'signal_ppp':sins,'coates': coates, 'med': med}


class SpadDataset(torch.utils.data.Dataset):
    def __init__(self, datapath, noise_param, transform=None):
        res = 64
        """__init__
        :param datapath: path to text file with list of
                        training files (intensity files)
        :param transform: transform (callable, optional):
                        Optional transform to be applied
                        on a sample.
        """
        with open(datapath) as f:
            self.intensity_files = f.read().split()
        self.spad_files = []
        for idx, n in enumerate(noise_param):
            self.spad_files.extend([intensity.replace('processed', 'spad').replace('intensity', 'spad')
                                    .replace('.mat', '_p{}.mat'.format(n))
                                    for intensity in self.intensity_files])
        # print(datapath)
        # print(len(self.spad_files))

        intensity_files_orig = self.intensity_files.copy()
        for idx, n in enumerate(noise_param):
            if idx > 0:
                self.intensity_files.extend(intensity_files_orig)

        self.transform = transform

        self.dark_img = np.asarray(scipy.io.loadmat(
            'simulated_data/dark_img.mat')['dark_img']).reshape([50, 64])
        self.dark_img = np.transpose(np.tile(np.mean(self.dark_img[:,0:res]),[res, 1]))

    def __len__(self):
        return len(self.spad_files)

    def tryitem(self, idx):
        res = 64
        num_bins = 1024
        pulse_max_idx = 7 - 1
        N = 500
        # lamda = 1
        # mu = 200
        signal_level = 10
        background_level = 50
        intensity = np.asarray(scipy.io.loadmat(
            self.intensity_files[idx])['intensity']).astype(
                np.float32).reshape([1, 512, 512]) / 255

        # low/high resolution depth maps
        bins = (np.asarray(scipy.io.loadmat(
            self.spad_files[idx])['bin']).astype(
                np.float32).reshape([64, 64])-1)[None, :, :]

        bins_hr = (np.asarray(scipy.io.loadmat(
            self.spad_files[idx])['bin_hr']).astype(
                np.float32).reshape([512, 512])-1)[None, :, :]

        rates = np.zeros((res, res, num_bins))

        signal_ppp = np.asarray(scipy.io.loadmat(
            self.spad_files[idx])['signal_ppp']).reshape([64, 64])
        # signal_ppp *= mu
        signal_ppp = signal_ppp / np.mean(signal_ppp) * signal_level
        ambient_ppp = np.asarray(scipy.io.loadmat(
            self.spad_files[idx])['ambient_ppp']).reshape([64, 64])
        # ambient_ppp *= lamda
        ambient_ppp = ambient_ppp / np.mean(ambient_ppp) * background_level / num_bins
        ambient_ppp += self.dark_img / num_bins
        ambient_ppp = ambient_ppp / np.mean(ambient_ppp) * background_level / num_bins

        pulse = np.asarray(scipy.io.loadmat(
            self.spad_files[idx])['pulse']).reshape([64, 64, 16])

        rates[:,:,0:np.shape(pulse)[2]] = pulse
        rates[:,:,0:np.shape(pulse)[2]] = np.multiply(rates[:,:,0:np.shape(pulse)[2]], np.tile(np.expand_dims(signal_ppp, 2), [1, 1, np.shape(pulse)[2]]))
        rates = rates + np.tile(np.expand_dims(ambient_ppp, 2), [1, 1, num_bins])

        # opt filtering
        filtering_fractions = 1 / np.multiply(num_bins, ambient_ppp)
        filtering_fractions = np.minimum(1, filtering_fractions)
        rates = np.multiply(rates, np.expand_dims(filtering_fractions, axis=2))

        for jj in range(res):
            for kk in range(res):
                # print(rates[jj, kk, 0:num_bins])
                # print(int(bins[0, jj, kk]) - pulse_max_idx)
                rates[jj, kk, 0:num_bins] = np.roll(rates[jj, kk, 0:num_bins], int(bins[0, jj, kk]) - pulse_max_idx)
        old_rates = np.copy(rates)
        rates = np.concatenate((rates, np.zeros((res, res, 1))), axis=2)

        for jj in range(res):
            for kk in range(res):
                # print(rates[jj, kk, 0:num_bins])
                temp = np.exp(- np.concatenate(([0], np.cumsum(rates[jj, kk, 0:num_bins]))))
                rates[jj, kk, :] = [1] - np.concatenate((np.exp(- rates[jj, kk, 0:num_bins]), [0]))
                rates[jj, kk, :] = np.multiply(rates[jj, kk, :], temp)

        # print(np.sum(rates, axis=1))
        # print(np.shape(np.sum(rates, axis=1)))

        # rates = np.maximum(rates, 0)
        # rates = np.divide(rates, np.expand_dims(np.sum(rates, axis=2), 2))
        # print(np.sum(rates, axis=2))

        detections = np.random.binomial(N, rates)

        # apply coates transformation
        denoms = N - np.concatenate((np.zeros((res, res, 1)), np.cumsum(detections[:, :, 0:num_bins], axis=2)), axis=2)
        quotients = np.nan_to_num(detections / denoms)
        quotients = quotients[:, :, 0:num_bins].reshape([1, 64, 64, -1])
        detections = detections[:, :, 0:num_bins].reshape([1, 64, 64, -1])
        spad = quotients
        spad = np.transpose(spad, (0, 3, 1, 2))

        # max correlation
        correlations = np.copy(quotients)
        for jj in range(res):
            for kk in range(res):
                correlations[0, jj, kk, :] = np.correlate(quotients[0, jj, kk, :], pulse[jj, kk, :], "same")

        coates = np.argmax(correlations, axis=3) / 1023

        # median filtering
        med = scipy.signal.medfilt(coates, [1, 5, 5])

        #old_rates = rates
        old_rates = old_rates[:, :, 0:num_bins].reshape([1, 64, 64, -1])
        old_rates = np.transpose(old_rates, (0, 3, 1, 2))
        old_rates = old_rates / np.sum(old_rates, axis=1)[None, :, :, :]

        bins /= 1023
        bins_hr /= 1023


        # simulated spad measurements
        # spad = np.asarray(scipy.sparse.csc_matrix.todense(scipy.io.loadmat(
        #     self.spad_files[idx])['spad'])).reshape([1, 64, 64, -1])
        # spad = np.transpose(spad, (0, 3, 2, 1))

        # # normalized pulse
        # rates = np.asarray(scipy.io.loadmat(
        #     self.spad_files[idx])['rates']).reshape([1, 64, 64, -1])
        # rates = np.transpose(rates, (0, 3, 1, 2))
        # rates = rates / np.sum(rates, axis=1)[None, :, :, :]

        # sample metainfo
        # sbr = np.asarray(scipy.io.loadmat(
        #     self.spad_files[idx])['SBR']).astype(np.float32)
        # photons = np.asarray(scipy.io.loadmat(
        #     self.spad_files[idx])['photons']).astype(np.float32)
        signal_ppp = np.multiply(signal_ppp, filtering_fractions)
        signal_ppp = signal_ppp.reshape([1, 64, 64])        
        #print(np.shape(signal_ppp))
        #print(np.shape(intensity))
        
        #intensity = np.copy(signal_ppp)
        
        sample = {'rates': old_rates, 'spad': spad, 'bins_hr': bins_hr,
                  'intensity': intensity, 'bins': bins, 'signal_ppp':signal_ppp,'coates': coates, 'med': med}

        if self.transform:
            sample = self.transform(sample)

        return sample

    def __getitem__(self, idx):
        try:
            #print("trying idx: " + str(idx))
            sample = self.tryitem(idx)
        except Exception as e:
            print(idx, e)
            idx = idx + 1
            sample = self.tryitem(idx)
        return sample
