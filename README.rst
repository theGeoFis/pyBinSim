.. image:: https://travis-ci.org/pyBinSim/pyBinSim.svg?branch=master
    :target: https://travis-ci.org/pyBinSim/pyBinSim

PyBinSim
========

Install
-------

::

    $ conda create --name binsim python=3.5 numpy
    $ source activate binsim
    $ pip install pybinsim
    
On linux, make sure that gcc and the development headers for libfftw and portaudio are installed, before invoking `pip install pybinsim`.
For ubuntu::

    $ apt-get install gcc portaudio19-dev libfftw3-dev
    

Run
---

Create ``pyBinSimSettings.txt`` file with content like this

::

    soundfile 002lIDsignals/test441kHz.wav;002sIDsignals/test2441kHz.wav;
    blockSize 512
    filterSize 16384
    filterList brirs/filter_list_kemar5.txt
    maxChannels 2
    samplingRate 44100
    enableCrossfading True
    useHeadphoneFilter False
    loudnessFactor 0.5
    loopSound False


Start Binaural Simulation

::

    import pybinsim
    import logging

    pybinsim.logger.setLevel(logging.DEBUG)    # defaults to INFO
    #Use logging.WARNING for printing warnings only

    with pybinsim.BinSim('pyBinSimSettings.txt') as binsim:
        binsim.stream_start()

Description
===========

Basic principle:
----------------

Depending on the number of maxChannels the corresponding number of virtual sound sources is created. The filter for each sound source can selected and activitated via OSC messages. The messages basically contain the number
index of the channel for which the filter should be switched and an identifier string to address the correct filter. The correspondence between parameter value and filter is determined by a filter list which can be adjusted individually for the specific use case. Furthermore OSC messages can be used to interact with the soundscene, for example by playing a sound on a certain channel. For this, the specified soundfiles are loaded into pybinsim as soundevents with specified ID's. 
    
Config parameter description:
-----------------------------

soundfile: 
    Defines \000sID*.wav file which is played back at startup. Sound file can contain up to maxChannels audio channels. Also accepts multiple files separated by ';'; Example: 'soundfile signals/002lID_sound1.wav;001sID_signals/sound2.wav
    The ID part contains a 3 dgit number as the actual ID and a type specifier "l" for looping sound and "s" for single sound. Single sounds are played only once (e.g. for pistol shots) and looping sounds are looped (e.g. for ambient sound), and can be paused and stopped via OSC (see the example).
blockSize: 
    Number of samples which are processed per block. Low values reduce delay but increase cpu load.
filterSize: 
    Defines filter size of the filters loaded with the filter list. Filter size should be a mutltiple of blockSize.
maxChannels: 
    Maximum number of sound sources/audio channels which can be controlled during runtime. The value for maxChannels must match or exceed the number of channels of soundFile(s).
samplingRate: 
    Sample rate for filters and soundfiles. Caution: No automatic sample rate conversion.
enableCrossfading: 
    Enable cross fade between audio blocks. Set 'False' or 'True'.
useHeadphoneFilter: 
    Enables headhpone equalization. The filterset should contain a filter with the identifier HPFILTER. Set 'False' or 'True'.
loudnessFactor: 
    Factor for overall output loudness. Attention: Clipping may occur
loopSound:
    Enables looping of sound file or sound file list. Set 'False' or 'True'.


OSC Messages and filter lists:
------------------------------

Example line from filter list:
165 2 0 0 0 0 brirs/kemar5/kemar_0_165.wav

To activate this filter for the third channel (counting starts at zero) for your wav file you have to send the following message to the pc where pyBinSim runs (port 10000):

::

    /pyBinSim 2 165 2 0 0 0 0
        

If you want to control the sound events, send
::

    /pyBinSimSoundevent/001/start/1

Where 001 is the sound ID, start is the command, and 1 is the channel number.
The audiofile has to be located on the pc where pyBinSim runs. Files are not transmitted over network.




Reference:
----------

Please cite our work:

Neidhardt, A.; Klein, F.; Knoop, N. and Köllmer, T., "Flexible Python tool for dynamic binaural synthesis applications", 142nd AES Convention, Berlin, 2017.



