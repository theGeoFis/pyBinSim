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
import multiprocessing
from pathlib import Path
import pickle
from timeit import default_timer
from typing import Tuple

import numpy as np
import pyfftw


nThreads = multiprocessing.cpu_count()


class ConvolverFFTW:
    """
    Class for convolving mono (usually for virtual sources) or stereo input (usually for HP compensation)
    with a BRIRsor HRTF
    """

    def __init__(self, ir_size: int, block_size: int, process_stereo: bool):
        start = default_timer()

        self.log = logging.getLogger("pybinsim.ConvolverFFTW")
        self.log.info("Convolver: Start Init")

        # pyFFTW Options
        pyfftw.interfaces.cache.enable()
        # effort='FFTW_MEASURE'
        effort = 'FFTW_PATIENT'
        # effort ='FFTW_EXHAUSTIVE' # takes 5..10 minutes

        # Get Basic infos
        self.IR_size = ir_size
        self.block_size = block_size

        # floor (integer) division in python 2 & 3
        self.IR_blocks = self.IR_size // block_size

        # Calculate LINEAR crossfade windows
        #self.crossFadeIn = np.array(range(0, self.block_size), dtype='float32')
        #self.crossFadeIn *= 1 / float((self.block_size - 1))
        #self.crossFadeOut = np.flipud(self.crossFadeIn)

        # Calculate COSINE-Square crossfade windows
        self.crossFadeOut = np.array(range(0, self.block_size), dtype='float32')
        self.crossFadeOut = np.square(
            np.cos(self.crossFadeOut/(self.block_size-1)*(np.pi/2)))
        self.crossFadeIn = np.flipud(self.crossFadeOut)

        # Filter format: [nBlocks,blockSize*2]

        pn_temporary = Path(__file__).parent.parent / "tmp"
        fn_wisdom = pn_temporary / "fftw_wisdom.pickle"
        if pn_temporary.exists() and fn_wisdom.exists():
            loaded_wisdom = pickle.load(open(fn_wisdom, 'rb'))
            pyfftw.import_wisdom(loaded_wisdom)

        # Create Input Buffers and create fftw plans. These need to be memory aligned, because they are ransformed to
        # freq domain regularly
        self.log.info("Convolver: Start Init buffer fft plans")
        self.buffer = pyfftw.zeros_aligned(self.block_size * 2, dtype='float32')
        self.bufferFftPlan = pyfftw.builders.rfft(self.buffer,
                                                  overwrite_input=True,
                                                  threads=nThreads,
                                                  planner_effort=effort,
                                                  avoid_copy=True)

        self.buffer2 = pyfftw.zeros_aligned(
            self.block_size * 2, dtype='float32')
        self.buffer2FftPlan = pyfftw.builders.rfft(self.buffer2,
                                                   overwrite_input=True,
                                                   threads=nThreads,
                                                   planner_effort=effort,
                                                   avoid_copy=True)

        # Create arrays for the filters and the FDLs.
        self.log.info("Convolver: Start Init filter fft plans")
        self.TF_left_blocked = np.zeros(
            (self.IR_blocks, self.block_size + 1), dtype='complex64')
        self.TF_right_blocked = np.zeros(
            (self.IR_blocks, self.block_size + 1), dtype='complex64')
        self.TF_left_blocked_previous = np.zeros(
            (self.IR_blocks, self.block_size + 1), dtype='complex64')
        self.TF_right_blocked_previous = np.zeros(
            (self.IR_blocks, self.block_size + 1), dtype='complex64')

        self.filter_fftw_plan = pyfftw.builders.rfft(np.zeros(self.block_size, dtype=np.float32),
                                                     n=self.block_size * 2,
                                                     overwrite_input=True,
                                                     threads=nThreads,
                                                     planner_effort=effort,
                                                     avoid_copy=False)

        self.FDL_size = self.IR_blocks * (self.block_size + 1)
        self.FDL_left = np.zeros(self.FDL_size, dtype='complex64')
        self.FDL_right = np.zeros(self.FDL_size, dtype='complex64')

        # Arrays for the result of the complex multiply and add
        # These should be memory aligned because ifft is performed with these data
        self.resultLeftFreq = pyfftw.zeros_aligned(
            self.block_size + 1, dtype='complex64')
        self.resultRightFreq = pyfftw.zeros_aligned(
            self.block_size + 1, dtype='complex64')
        self.resultLeftFreqPrevious = pyfftw.zeros_aligned(
            self.block_size + 1, dtype='complex64')
        self.resultRightFreqPrevious = pyfftw.zeros_aligned(
            self.block_size + 1, dtype='complex64')

        self.log.info("Convolver: Start Init result ifft plans")
        self.resultLeftIFFTPlan = pyfftw.builders.irfft(self.resultLeftFreq,
                                                        overwrite_input=True,
                                                        threads=nThreads,
                                                        planner_effort=effort,
                                                        avoid_copy=True)
        self.resultRightIFFTPlan = pyfftw.builders.irfft(self.resultRightFreq,
                                                         overwrite_input=True,
                                                         threads=nThreads,
                                                         planner_effort=effort,
                                                         avoid_copy=True)

        self.log.info("Convolver: Start Init result prvieous fft plans")
        self.resultLeftPreviousIFFTPlan = pyfftw.builders.irfft(self.resultLeftFreqPrevious,
                                                                overwrite_input=True,
                                                                threads=nThreads,
                                                                planner_effort=effort,
                                                                avoid_copy=True)
        self.resultRightPreviousIFFTPlan = pyfftw.builders.irfft(self.resultRightFreqPrevious,
                                                                 overwrite_input=True,
                                                                 threads=nThreads,
                                                                 planner_effort=effort,
                                                                 avoid_copy=True)

        # save FFTW plans to recover for next pyBinSim session
        collected_wisdom = pyfftw.export_wisdom()
        if not pn_temporary.exists():
            pn_temporary.mkdir(parents=True)
        pickle.dump(collected_wisdom, open(fn_wisdom, "wb"))

        # Result of the ifft is stored here
        self.outputLeft = np.zeros(self.block_size, dtype='float32')
        self.outputRight = np.zeros(self.block_size, dtype='float32')

        # Counts how often process() is called
        self.processCounter = 0

        # Flag for interpolation of output blocks (result of process())
        self.interpolate = False

        # Select mono or stereo processing
        self.processStereo = process_stereo

        end = default_timer()
        delta = end - start
        self.log.info(f"Convolver: Finished Init (took {delta}s)")

    def get_counter(self) -> int:
        """
        Returns processing counter
        :return: processing counter
        """
        return self.processCounter

    def transform_filter(self, filter_) -> None:
        """
        Transform filter to freq domain

        :param filter:
        :return: transformed filter
        """

        # Get blocked IRs
        IR_left_blocked, IR_right_blocked = filter_.getFilter()

        self.TF_left_blocked = np.zeros(
            [self.IR_blocks, self.block_size + 1], dtype='complex64')
        self.TF_right_blocked = np.zeros(
            [self.IR_blocks, self.block_size + 1], dtype='complex64')

        for ir_block_count in range(0, self.IR_blocks):
            self.TF_left_blocked[ir_block_count] = self.filter_fftw_plan(
                IR_left_blocked[ir_block_count])
            self.TF_right_blocked[ir_block_count] = self.filter_fftw_plan(
                IR_right_blocked[ir_block_count])

    def setIR(self, filter_, do_interpolation: bool) -> None:
        """
        Hand over a new set of filters to the convolver
        and define if you want to perform an interpolation/crossfade

        :param filter:
        :param do_interpolation:
        :return: None
        """
        # Save old filters in case interpolation is needed
        self.TF_left_blocked_previous = self.TF_left_blocked
        self.TF_right_blocked_previous = self.TF_right_blocked

        # apply new filters
        self.transform_filter(filter_)

        # Interpolation means cross fading the output blocks (linear interpolation)
        self.interpolate = do_interpolation

    def process_nothing(self) -> None:
        """
        Just for testing
        :return: None
        """
        self.processCounter += 1

    def fill_buffer_mono(self, block: np.ndarray) -> None:
        """
        Copy mono soundblock to input Buffer;
        Transform to Freq. Domain and store result in FDLs
        :param block: Mono sound block
        :return: None
        """

        if block.size < self.block_size:
            # print('Fill up last block')
            block = np.concatenate(
                (block, np.zeros((1, (self.block_size - block.size)), dtype=np.float32)), 1)

        if self.processCounter == 0:
            # insert first block to buffer
            self.buffer[self.block_size:] = block

        else:
            # shift buffer
            self.buffer = np.roll(self.buffer, -self.block_size)
            # insert new block to buffer
            self.buffer[self.block_size:self.block_size * 2] = block
            # shift FDLs
            self.FDL_left = np.roll(self.FDL_left, self.block_size + 1)
            self.FDL_right = np.roll(self.FDL_right, self.block_size + 1)

            # transform buffer into freq domain and copy to FDLs
        self.FDL_left[:self.block_size + 1] = self.FDL_right[:self.block_size + 1] = self.bufferFftPlan(
            self.buffer)

    def fill_buffer_stereo(self, block: np.ndarray) -> None:
        """
        Copy stereo soundblock to input Buffer1 and Buffer2;
        Transform to Freq. Domain and store result in FDLs

        :param block:
        :return: None
        """

        if block.size < self.block_size:
            # print('Fill up last block')
            # print(np.shape(block))
            appendix = np.zeros(
                ((self.block_size - block.size), 2), dtype=np.float32)
            block = np.concatenate((block, appendix), 0)

        if self.processCounter == 0:
            # insert first block to buffer
            self.buffer[self.block_size:] = block[:, 0]
            self.buffer2[self.block_size:] = block[:, 1]

        else:
            # shift buffer
            self.buffer = np.roll(self.buffer, -self.block_size)
            self.buffer2 = np.roll(self.buffer2, -self.block_size)
            # insert new block to buffer
            self.buffer[self.block_size:] = block[:, 0]
            self.buffer2[self.block_size:] = block[:, 1]
            # shift FDLs
            self.FDL_left = np.roll(self.FDL_left, self.block_size + 1)
            self.FDL_right = np.roll(self.FDL_right, self.block_size + 1)

        # transform buffer into freq domain and copy to FDLs
        self.FDL_left[:self.block_size + 1] = self.bufferFftPlan(self.buffer)
        self.FDL_right[:self.block_size + 1] = self.buffer2FftPlan(self.buffer2)

    def multiply_and_add(self,
                         IR_block_count: int,
                         result: np.ndarray,
                         input1: np.ndarray,
                         input2: np.ndarray) -> np.ndarray:

        # Discard old data on the beginning of a new sound block
        snippet2 = input2[(IR_block_count * (self.block_size + 1))
                           :((IR_block_count + 1) * (self.block_size + 1))]
        if IR_block_count == 0:
            result = input1[IR_block_count]*snippet2

        else:
            result += input1[IR_block_count]*snippet2

        return result

    def process(self, block: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """
        Main function

        :param block:
        :return: (outputLeft, outputRight)
        """

        # First: Fill buffer and FDLs with current block
        if not self.processStereo:
            # print('Convolver Mono Processing')
            self.fill_buffer_mono(block)
        else:
            # print('Convolver Stereo Processing')
            self.fill_buffer_stereo(block)

        # Second: multiplication with IR block und accumulation with previous data
        for irBlockCount in range(self.IR_blocks):
            # Always convolute current filter
            self.resultLeftFreq[:] = self.multiply_and_add(irBlockCount,
                                                           self.resultLeftFreq,
                                                           self.TF_left_blocked,
                                                           self.FDL_left)
            self.resultRightFreq[:] = self.multiply_and_add(irBlockCount,
                                                            self.resultRightFreq,
                                                            self.TF_right_blocked,
                                                            self.FDL_right)

            # Also convolute old filter if interpolation needed
            if self.interpolate:
                self.resultLeftFreqPrevious[:] = self.multiply_and_add(irBlockCount,
                                                                       self.resultLeftFreqPrevious,
                                                                       self.TF_left_blocked_previous,
                                                                       self.FDL_left)
                self.resultRightFreqPrevious[:] = self.multiply_and_add(irBlockCount,
                                                                        self.resultRightFreqPrevious,
                                                                        self.TF_right_blocked_previous,
                                                                        self.FDL_right)

        # Third: Transformation back to time domain
        self.outputLeft = self.resultLeftIFFTPlan(self.resultLeftFreq)[
            self.block_size:self.block_size * 2]
        self.outputRight = self.resultRightIFFTPlan(self.resultRightFreq)[
            self.block_size:self.block_size * 2]

        if self.interpolate:
            # fade over full block size
            # print('do block interpolation')
            prevLeftIFFTPlan = self.resultLeftPreviousIFFTPlan(
                self.resultLeftFreqPrevious)
            prevLeftIFFTPlan = prevLeftIFFTPlan[self.block_size:self.block_size * 2]
            self.outputLeft = self.outputLeft * self.crossFadeIn + \
                prevLeftIFFTPlan * self.crossFadeOut

            prevRightIFFTPlan = self.resultRightPreviousIFFTPlan(
                self.resultRightFreqPrevious)
            prevRightIFFTPlan = prevRightIFFTPlan[self.block_size:self.block_size * 2]
            self.outputRight = self.outputRight * self.crossFadeIn + \
                prevRightIFFTPlan * self.crossFadeOut

        self.processCounter += 1
        self.interpolate = False

        return self.outputLeft, self.outputRight

    def close(self) -> None:
        print("Convolver: close")
        # TODO: do something here?
