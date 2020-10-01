import soundcard as sc
import numpy as np


def print_all_devices() -> None:
    print("speakers")
    spk_all = sc.all_speakers()
    spk_default = sc.default_speaker()
    for spk in spk_all:
        prefix = "* " if str(spk) == str(spk_default) else "  "
        print(prefix + str(spk))

    print("microphones")
    mic_all = sc.all_microphones()
    mic_default = sc.default_microphone()
    for mic in mic_all:
        prefix = "* " if str(mic) == str(mic_default) else "  "
        print(prefix + str(mic))


def test_tone() -> None:
    spk = sc.default_speaker()
    print(spk)

    block_size = 256
    cosinus = np.cos(np.linspace(0, 2*np.pi, block_size, endpoint=False))
    cosinus = np.tile(cosinus, (2, 1)).T

    with spk.player(samplerate=48000, blocksize=block_size) as sp:
        while True:
            sp.play(cosinus * 0.1)


if __name__ == "__main__":
    print_all_devices()
    test_tone()
