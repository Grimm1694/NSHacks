import os
import time
import wave
import numpy as np
import pyaudio
import json
from groq import Groq

# ——— Groq client setup ———
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# ——— Audio constants ———
CHUNK      = 1024
FORMAT     = pyaudio.paInt16
CHANNELS   = 1
RATE       = 16000
RECORD_SEC = 5
ALERT_FREQ = 1000   # Hz
ALERT_DUR  = 0.5    # seconds

p = pyaudio.PyAudio()

def record_chunk():
    """Record RECORD_SEC seconds from mic and return raw bytes."""
    stream = p.open(format=FORMAT, channels=CHANNELS,
                    rate=RATE, input=True,
                    frames_per_buffer=CHUNK)
    frames = []
    for _ in range(int(RATE / CHUNK * RECORD_SEC)):
        frames.append(stream.read(CHUNK, exception_on_overflow=False))
    stream.stop_stream()
    stream.close()
    return b"".join(frames)

def save_audio(audio_bytes, filename="temp.wav"):  # ← Remove /tmp/ and just use "temp.wav"
    """Save audio bytes to a WAV file."""
    with wave.open(filename, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(p.get_sample_size(FORMAT))
        wf.setframerate(RATE)
        wf.writeframes(audio_bytes)
    return filename


def transcribe(audio_bytes):
    """Transcribe audio using Groq's Whisper model."""
    audio_path = save_audio(audio_bytes)
    with open(audio_path, "rb") as file:
        transcription = groq_client.audio.transcriptions.create(
            file=("temp.wav", file.read()),
            model="whisper-large-v3-turbo",
            response_format="verbose_json"
        )
    return transcription.text.strip()

def detect_fraud(text):
    """Use Groq LLaMA to classify fraud intent."""
    prompt = (
        "Classify whether the following transcript contains fraud or malicious intent.\n"
        "Respond only with JSON: {\"fraud\":true/false,\"confidence\":<0.0–1.0>}.\n\n"
        f"Transcript: \"\"\"{text}\"\"\""
    )
    response = groq_client.chat.completions.create(
        model="llama3-70b-8192",
        messages=[
            {"role": "system", "content": "You are a helpful assistant that outputs JSON only."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.0,
        max_tokens=100
    )
    out = response.choices[0].message.content.strip()
    try:
        fraud_obj = json.loads(out)
        return fraud_obj.get("fraud", False), fraud_obj.get("confidence", 0.0)
    except Exception as e:
        print(f"JSON parsing error: {e}")
        return False, 0.0

def alert_beep():
    """Play a simple sine‐wave beep using PyAudio."""
    stream = p.open(format=pyaudio.paFloat32,
                    channels=1, rate=RATE, output=True)
    t = np.linspace(0, ALERT_DUR, int(RATE * ALERT_DUR), False)
    tone = np.sin(ALERT_FREQ * 2 * np.pi * t).astype(np.float32)
    stream.write(tone.tobytes())
    stream.stop_stream()
    stream.close()

def main_loop():
    print("🎙️ Starting real-time fraud monitor using Groq Whisper + LLaMA… Press Ctrl+C to stop.")
    try:
        while True:
            audio = record_chunk()
            text  = transcribe(audio)
            if not text:
                continue

            print(f"Transcript: {text!r}")
            fraud, conf = detect_fraud(text)
            print(f"Fraud? {fraud} (confidence={conf:.2f})")

            if fraud and conf > 0.7:
                print("⚠️ Fraud detected! Beeping...")
                alert_beep()

            time.sleep(0.1)

    except KeyboardInterrupt:
        print("\n👋 Exiting...")
    finally:
        p.terminate()

if __name__ == "__main__":
    main_loop()
