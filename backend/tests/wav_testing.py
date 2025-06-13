from pydub import AudioSegment
audio = AudioSegment.from_wav("C:/Users/Maggie/Desktop/Shortreels_v2/backend/data/output/voice_test1234_1741081078.wav")
print("Audio Duration:", len(audio) / 1000, "seconds")
