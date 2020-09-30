import soundcard

print("all speakers")
spk_all = soundcard.all_speakers()
for spk in spk_all:
    print("  " + str(spk))

print("default speakers")
spk_default = soundcard.default_speaker()
print("  " + str(spk_default))
