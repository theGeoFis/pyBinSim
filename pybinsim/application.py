# This file is part of the pyBinSim project.
#
# Copyright (c) 2017 A. Neidhardt, F. Klein, N. Knoop, T. Köllmer
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

""" Module contains main loop and configuration of pyBinSim """
import logging
import time

import numpy as np
import soundcard as sc

from pybinsim.convolver import ConvolverFFTW
from pybinsim.filterstorage import FilterStorage
from pybinsim.osc_receiver import OscReceiver
from pybinsim.pose import Pose
from pybinsim.soundhandler import SoundHandler


def parse_boolean(any_value):

    if type(any_value) == bool:
        return any_value

    # str -> bool
    if any_value == 'True':
        return True
    if any_value == 'False':
        return False

    return None


class BinSimConfig:
    def __init__(self):

        self.log = logging.getLogger("pybinsim.BinSimConfig")

        # Default Configuration
        self.configurationDict = {'soundfile': '',
                                  'blockSize': 256,
                                  'filterSize': 16384,
                                  'filterList': 'brirs/filter_list_kemar5.txt',
                                  'enableCrossfading': False,
                                  'useHeadphoneFilter': False,
                                  'loudnessFactor': float(1),
                                  'maxChannels': 8,
                                  'samplingRate': 44100,
                                  'loopSound': True}

    def read_from_file(self, fn_config_file: str) -> None:
        config = open(fn_config_file, 'r')

        for line in config:
            line_content = str.split(line)
            key = line_content[0]
            value = line_content[1]

            if key in self.configurationDict:
                config_value_type = type(self.configurationDict[key])

                if config_value_type is bool:
                    # evaluate 'False' to False
                    boolean_config = parse_boolean(value)

                    if boolean_config is None:
                        self.log.warning(
                            f"Cannot convert {value} to bool. (key: {key}")

                    self.configurationDict[key] = boolean_config
                else:
                    # use type(str) - ctors of int, float, ...
                    self.configurationDict[key] = config_value_type(value)

            else:
                self.log.warning('Entry ' + key + ' is unknown')

    def get(self, setting: str):
        return self.configurationDict[setting]


class BinSim:
    """
    Main pyBinSim program logic
    """

    def __init__(self, fn_config_file: str):

        self.log = logging.getLogger("pybinsim.BinSim")
        self.log.info("BinSim: init")

        # Read Configuration File
        self.config = BinSimConfig()
        self.config.read_from_file(fn_config_file)

        self.nChannels = self.config.get('maxChannels')
        self.sampleRate = self.config.get('samplingRate')
        self.blockSize = self.config.get('blockSize')

        self.result = None
        self.block = None
        self.stream = None

        self.convolverWorkers = []
        self.initialize_pybinsim()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.__cleanup()

    def stream_start(self) -> None:
        self.log.info("BinSim: stream_start")

        stream_callback = audio_callback(self)

        spk = sc.get_speaker("Analog")
        with spk.player(samplerate=self.sampleRate, blocksize=self.blockSize) as sp:
            while True:
                result = stream_callback(self.blockSize)
                sp.play(result)

    def initialize_pybinsim(self) -> None:
        self.result = np.empty([self.blockSize, 2], dtype=np.float32)
        self.block = np.empty(
            [self.nChannels, self.blockSize], dtype=np.float32)

        # Create FilterStorage
        filter_size = self.config.get('filterSize')
        self.filterStorage = FilterStorage(filter_size,
                                           self.blockSize,
                                           self.config.get('filterList'))

        # Start an oscReceiver
        self.oscReceiver = OscReceiver()
        self.oscReceiver.start_listening()
        time.sleep(1)

        # Create SoundHandler
        self.soundHandler = SoundHandler(self.blockSize,
                                         self.nChannels,
                                         self.sampleRate,
                                         self.config.get('loopSound'))

        soundfile_list = self.config.get('soundfile')
        self.soundHandler .request_new_sound_file(soundfile_list)

        # Create N convolvers depending on the number of wav channels
        self.log.info('Number of Channels: ' + str(self.nChannels))
        self.convolvers = [None] * self.nChannels
        for n in range(self.nChannels):
            self.convolvers[n] = ConvolverFFTW(
                filter_size, self.blockSize, False)

        # HP Equalization convolver
        self.convolverHP = None
        if self.config.get('useHeadphoneFilter'):
            self.convolverHP = ConvolverFFTW(filter_size, self.blockSize, True)
            hpfilter = self.filterStorage.get_headphone_filter()
            self.convolverHP.setIR(hpfilter, False)

    def __cleanup(self) -> None:
        # Close everything when BinSim is finished
        self.filterStorage.close()
        self.oscReceiver.close()

        for n in range(self.nChannels):
            self.convolvers[n].close()

        if self.config.get('useHeadphoneFilter'):
            if self.convolverHP:
                self.convolverHP.close()


def audio_callback(binsim: BinSim):
    """ Wrapper for callback to hand over custom data """

    def callback(block_size):
        # print("audio callback")

        current_soundfile_list = binsim.oscReceiver.get_sound_file_list()
        if current_soundfile_list:
            binsim.soundHandler.request_new_sound_file(current_soundfile_list)

        # Get sound block. At least one convolver should exist
        num_channels = binsim.soundHandler.get_sound_channels()
        binsim.block[:num_channels, :] = binsim.soundHandler.buffer_read()

        # Update Filters and run each convolver with the current block
        do_crossfading = callback.config.get('enableCrossfading')
        for n in range(num_channels):
            convolver = binsim.convolvers[n]

            # Get new Filter
            if binsim.oscReceiver.is_filter_update_necessary(n):
                filterValueList = binsim.oscReceiver.get_current_values(n)
                pose = Pose.from_filterValueList(filterValueList)
                filter_ = binsim.filterStorage.get_filter(pose)
                convolver.setIR(filter_, do_crossfading)

            left, right = convolver.process(binsim.block[n, :])

            # Sum results from all convolvers
            if n == 0:
                binsim.result[:, 0] = left
                binsim.result[:, 1] = right
            else:
                binsim.result[:, 0] += left
                binsim.result[:, 1] += right

        # Finally apply Headphone Filter
        if callback.config.get('useHeadphoneFilter'):
            hp_result = binsim.convolverHP.process(binsim.result)
            binsim.result[:, 0] = hp_result[0]
            binsim.result[:, 1] = hp_result[1]

        # Scale data
        if num_channels != 0:
            binsim.result /= num_channels * 2
        binsim.result *= callback.config.get('loudnessFactor')

        if np.max(np.abs(binsim.result)) > 1:
            binsim.log.warn('Clipping occurred: Adjust loudnessFactor!')

        return binsim.result[:block_size]

    callback.config = binsim.config

    return callback
