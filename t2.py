import sounddevice as sd
import numpy as np
import requests
import io
import wave
import tkinter as tk
from tkinter import messagebox
import threading
from dotenv import load_dotenv
import os
load_dotenv()

HF_API_TOKEN = os.getenv("HF_API_TOKEN")
API_URL = "https://api-inference.huggingface.co/models/openai/whisper-large-v3-turbo"

fraud_keywords = [
    "otp", "one time password", "account number", "debit card",
    "upi pin", "send money", "bank verification", "kyc update",
    "government penalty", "block your account"
]

# Flag to control the recording loop5
stop_flag = threading.Event()

def show_fraud_alert():
    """Display a warning message when fraud is detected."""
    root = tk.Tk()
    root.withdraw()
    messagebox.showwarning("⚠️ Fraud Detected!", "Suspicious conversation detected.\nCall has been halted.")
    root.destroy()

def record_audio(duration=5, samplerate=16000):
    """Record audio from the microphone for a given duration."""
    print("🎙️ Recording...")
    recording = sd.rec(int(duration * samplerate), samplerate=samplerate, channels=1, dtype='float32')
    sd.wait()
    # Convert the recording to a WAV format in memory
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit PCM
        wf.setframerate(samplerate)
        int16_audio = (recording * 32767).astype(np.int16)
        wf.writeframes(int16_audio.tobytes())
    buffer.seek(0)
    return buffer

def transcribe_audio(buffer):
    """Send the audio buffer to Hugging Face's API for transcription."""
    headers = {
        "Authorization": f"Bearer {HF_API_TOKEN}",
        "Content-Type": "audio/wav"
    }
    print("📡 Sending audio to Hugging Face...")
    response = requests.post(API_URL, headers=headers, data=buffer.read())
    response.raise_for_status()
    result = response.json()
    return result.get('text', '').lower().strip()

def fraud_detection(text):
    """Check the transcribed text for any fraud-related keywords."""
    print(f"📝 Transcribed Text: {text}")
    for keyword in fraud_keywords:
        if keyword in text:
            print(f"🚨 FRAUD Detected (Keyword: {keyword.upper()})")
            stop_flag.set()
            show_fraud_alert()
            break

def listen_loop():
    """Continuously record and process audio until a fraud keyword is detected."""
    while not stop_flag.is_set():
        buffer = record_audio(duration=5)
        try:
            text = transcribe_audio(buffer)
            fraud_detection(text)
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    listen_loop()
