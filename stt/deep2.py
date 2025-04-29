import os
import asyncio
import json
import pyaudio
import websockets
import tkinter as tk
from tkinter import messagebox
import threading
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Read your Deepgram API key from the environment
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
if not DEEPGRAM_API_KEY:
    raise RuntimeError("Set DEEPGRAM_API_KEY in your environment")

# Fraud detection keywords
fraud_keywords = [
    "otp", "one time password", "ek baar ka password",
    "account number", "bank account",
    "debit card", "credit card",
    "upi pin", "upi password",
    "send money", "transfer money",
    "bank verification", "account verification",
    "kyc update", "kyc verification",
    "government penalty", "fine", "penalty",
    "urgent", "emergency", "immediately",
    "password", "pin", "secret code"
]

# Flag to control the audio stream
stop_flag = threading.Event()

def show_fraud_alert():
    """Popup a fraud warning"""
    root = tk.Tk()
    root.withdraw()
    messagebox.showwarning("⚠️ Fraud Detected!", "Suspicious conversation detected.\nCall halted.")
    root.destroy()

# Build the Deepgram WebSocket URL with query parameters
DG_URL = (
    "wss://api.deepgram.com/v1/listen"
    "?encoding=linear16"
    "&sample_rate=44100"
    "&channels=1"
    "&punctuate=true"
)

async def transcribe_live():
    # Set up PyAudio for microphone capture
    pa = pyaudio.PyAudio()
    stream = pa.open(
        format=pyaudio.paInt16,
        channels=1,
        rate=16000,
        input=True,
        frames_per_buffer=1024,
    )

    try:
        # Connect with proper authentication header
        async with websockets.connect(
            DG_URL,
            additional_headers={"Authorization": f"Token {DEEPGRAM_API_KEY}"}
        ) as ws:
            print("🟢 Connected to Deepgram, start speaking…")
            
            async def send_audio():
                try:
                    while not stop_flag.is_set():
                        data = stream.read(1024, exception_on_overflow=False)
                        await ws.send(data)  # send raw PCM bytes
                except websockets.ConnectionClosed:
                    print("🔴 Connection closed during audio sending")
                except Exception as e:
                    print(f"Error sending audio: {str(e)}")

            async def receive_transcripts():
                try:
                    async for message in ws:
                        if stop_flag.is_set():
                            break
                            
                        res = json.loads(message)
                        # ignore interim results unless you want them; only print finals
                        if res.get("is_final"):
                            transcript = res["channel"]["alternatives"][0]["transcript"]
                            print(f"🗣  {transcript}")
                            
                            # Check for fraud keywords
                            transcript_lower = transcript.lower()
                            for keyword in fraud_keywords:
                                if keyword in transcript_lower:
                                    print(f"🚨 FRAUD DETECTED! (Keyword: {keyword.upper()})")
                                    stop_flag.set()
                                    show_fraud_alert()
                                    break
                except websockets.ConnectionClosed:
                    print("🔴 Connection closed during transcript receiving")
                except Exception as e:
                    print(f"Error receiving transcripts: {str(e)}")

            # Run sending and receiving concurrently
            await asyncio.gather(send_audio(), receive_transcripts())

    except Exception as e:
        print(f"Connection error: {str(e)}")
    finally:
        # Clean up
        stream.stop_stream()
        stream.close()
        pa.terminate()
        print("🔴 Connection closed")

if __name__ == "__main__":
    try:
        asyncio.run(transcribe_live())
    except KeyboardInterrupt:
        print("\nInterrupted by user, exiting…")
    except Exception as e:
        print(f"Error: {str(e)}") 