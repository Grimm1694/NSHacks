import torch
import whisper
import sounddevice as sd
import numpy as np
import threading
import tkinter as tk
from tkinter import messagebox

# Step 1: Load Whisper Model
model = whisper.load_model("small")  # Small & fast

# Step 2: Define Fraud Keywords and Phrases
fraud_keywords = [
    "otp", "one time password", "account number", "debit card",
    "upi pin", "send money", "bank verification", "kyc update",
    "government penalty", "block your account"
]

# Step 3: Global flag to stop recording
stop_flag = threading.Event()

# Step 4: Fraud Alert Popup
def show_fraud_alert():
    root = tk.Tk()
    root.withdraw()  # Hide the main window
    messagebox.showwarning("⚠️ Fraud Detected!", "Suspicious conversation detected.\nCall has been stopped for your safety.")
    root.destroy()

# Step 5: Audio Callback
def callback(indata, frames, time, status):
    if status:
        print(status)
    audio_data = indata[:, 0]  # Use first channel (mono)

    # Convert audio to np array
    audio_np = np.array(audio_data, dtype=np.float32)

    # Transcribe live
    result = model.transcribe(audio_np, fp16=False)
    text = result["text"].lower().strip()
    
    if text:
        print(f"📝 Transcribed: {text}")

    # Check for fraud keywords
    for keyword in fraud_keywords:
        if keyword in text:
            print(f"🚨 Detected keyword: {keyword.upper()}")
            stop_flag.set()  # Set flag to stop recording
            show_fraud_alert()  # Show alert
            break  # No need to check further

# Step 6: Start Listening
def listen():
    samplerate = 16000  # Whisper expects 16kHz
    duration = 20  # Record small chunks

    print("🛡️ Listening for fraud... Press CTRL+C to manually stop.")

    with sd.InputStream(channels=1, samplerate=samplerate, callback=callback):
        while not stop_flag.is_set():
            sd.sleep(duration * 1000)

if __name__ == "__main__":
    listen()
