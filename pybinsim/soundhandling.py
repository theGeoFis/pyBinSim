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

import logging
import threading
import time
import re

import numpy as np
import soundfile as sf


class AudioBuffer(object):
    """ Class to handle the audio buffer and serve it to pyBinSim """

    def __init__(self, block_size, n_channels):

        self.log = logging.getLogger("pybinsim.SoundHandler")

        self.n_channels = n_channels
        self.chunk_size = block_size
        self.bufferSize = block_size * 2
        self.buffer = np.zeros([self.n_channels, self.bufferSize])
        self.active_channels = n_channels

    def buffer_add_silence(self):
        self.buffer[:self.active_channels, :-self.chunk_size] = self.buffer[:self.active_channels, self.chunk_size:]
        self.buffer[:self.active_channels, -self.chunk_size:] = np.zeros([self.active_channels, self.chunk_size])

    def buffer_add_sound(self, new_chunk):
        self.buffer[:self.active_channels, :-self.chunk_size] = self.buffer[:self.active_channels, self.chunk_size:]
        self.buffer[:self.active_channels, -self.chunk_size:] = new_chunk

    def buffer_flush(self):
        self.buffer = np.zeros([self.n_channels, self.bufferSize])

    def buffer_read(self, new_chunk):
        buffer_content = self.buffer[:self.active_channels, :-self.chunk_size]
        self.buffer_add_sound(new_chunk)
        return buffer_content

    def get_sound_channels(self):
        return self.active_channels


class SoundSceneHandler(object):
    """ Class to read audio from files, update the soundscene and serve it the audio buffer """

    def __init__(self, block_size, n_channels, fs):

        self.log = logging.getLogger("pybinsim.SceneHandler")

        self.fs = fs
        self.n_channels = n_channels
        self.chunk_size = block_size
        self.sound_events = dict()
        self.scene = np.zeros([n_channels, block_size])
        self.scene_chunk = np.zeros([n_channels, block_size])
        self.sound_file = np.zeros((0, 0))
        self.soundPath = ''
        self.soundFileList = []

    def request_chunk(self):

        for sound in self.sound_events.values():
            if sound.is_running:
                chunk = sound.request_chunk()
                # print("Size: ", chunk.shape[0])
                self.scene[sound.channel, :] = chunk
        
        self.scene_chunk = self.scene
        self.scene_flush()
        
        return self.scene_chunk

    def scene_flush(self):
        self.scene = np.zeros([self.n_channels, self.chunk_size])

    def control_sound_event(self, event_data):
        key = event_data[0]
        command = event_data[1]
        if len(event_data) == 3:
            add_info = event_data[2]
        else:
            add_info = None

        if command == 'pause':
            self.sound_events[key].pause_sound()
        elif command == 'stop':
            self.sound_events[key].stop_sound()
        elif command == 'start':
            self.sound_events[key].start_sound(add_info)
        elif command == 'sendto':
            self.sound_events[key].place_sound(add_info)
        else:  
            raise ValueError('Unknown soundevent command!')
    
    def read_sound_files(self, sound_file_list):
        """load all files for the audio installation"""
        sound_file_list = str.split(sound_file_list, ';')
        self.soundFileList = sound_file_list
        self.log.info("Audio Files: {}".format(str(self.soundFileList)))

        for sound in self.soundFileList:
            self.log.info('Loading new sound file')

            #get id and type of soundfile
            match = re.search(r"(?P<id>[0-9]{3})(?P<type>[slt])ID_", sound)
            key = match.group('id')
            event_type = match.group('type')

            audio_file_data, fs = sf.read(sound, dtype='float32', )
            assert fs == self.fs

            self.log.debug("audio_file_data: {} MB".format(audio_file_data.nbytes // 1024 // 1024))
            self.sound_file = np.asmatrix(audio_file_data)

            # free data
            audio_file_data = None

            if self.sound_file.shape[0] > self.sound_file.shape[1]:
                self.sound_file = self.sound_file.transpose()

            self.active_channels = self.sound_file.shape[0]

            if self.sound_file.shape[1] % self.chunk_size != 0:
                length_diff = self.chunk_size - (self.sound_file.shape[1] % self.chunk_size)
                zeros = np.zeros((self.sound_file.shape[0], length_diff), dtype=np.float32)

                self.log.debug("Zeros size: {} Byte".format(zeros.nbytes))
                self.log.debug("Zeros shape: {} ({})".format(zeros.shape, zeros.dtype))
                self.log.debug("Soundfile size: {} MiB".format(self.sound_file.nbytes // 1024 // 1024))
                self.log.debug("Soundfile shape: {} ({})".format(self.sound_file.shape, self.sound_file.dtype))
                self.sound_file = np.concatenate(
                    (self.sound_file, zeros),
                    1
                )
                self.log.debug("Soundfile size after concat: {} MiB".format(self.sound_file.nbytes // 1024 // 1024))
                self.log.debug(
                    "Soundfile shape after concat: {} ({})".format(self.sound_file.shape, self.sound_file.dtype))

            #collect SoundEvent in dictionary
            self.sound_events[key] = SoundEvent(self.sound_file, key, event_type, self.chunk_size)
            self.log.info('Loaded new sound file\n')


class SoundEvent(object):
    """Storing sounds as events and interfacing with storage"""
    
    def __init__(self, sound, id='000', type='l', chunk_size=0):

        self.sound_id = id
        self.is_running = False
        self.channel = 0 #placed on which channel
        self.channel_weight = 0 #two channels for phantom source
        self.chunk_size = chunk_size

        if type == 'l':
            self.loopSound = True
            self.is_running = True
        else:
            self.loopSound = False
            self.is_running = False
        
        self.sound = sound
        self.n_channels = sound.shape[0]
        self.frame_count = 0

    def start_sound(self, channel=None):
        if channel:
            self.channel = channel

        self.is_running = True
        return

    def stop_sound(self):
        self.frame_count = 0
        self.is_running = False
        return

    def pause_sound(self):
        self.is_running = False
        return

    def request_chunk(self):

        if (self.frame_count + 1) * self.chunk_size < self.sound.shape[1] and self.is_running:
            chunk = self.sound[:, self.frame_count * self.chunk_size: (self.frame_count + 1) * self.chunk_size]
            self.frame_count += 1
        elif self.loopSound and self.is_running:
            chunk = self.sound[:, 0: self.chunk_size]
            self.frame_count = 1
        elif self.is_running:
            chunk = np.zeros([self.n_channels, self.chunk_size])
            self.frame_count = 0
            self.is_running = False
        else:
            return None

        return chunk

    def place_sound(self, channel):
        self.channel = channel
