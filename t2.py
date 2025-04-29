import os
import asyncio
import json
import pyaudio
import websockets

# Read your Deepgram API key from the environment
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
if not DEEPGRAM_API_KEY:
    raise RuntimeError("Set DEEPGRAM_API_KEY in your environment")  # :contentReference[oaicite:0]{index=0}

# Build the Deepgram WebSocket URL with query parameters
# encoding=linear16, sample_rate=44100, channels=1, and punctuate=true for basic formatting
DG_URL = (
    "wss://api.deepgram.com/v1/listen"
    f"?access_token={DEEPGRAM_API_KEY}"
    "&encoding=linear16"
    "&sample_rate=44100"
    "&channels=1"
    "&punctuate=true"
)  # :contentReference[oaicite:1]{index=1}

async def transcribe_live():
    # Set up PyAudio for microphone capture
    pa = pyaudio.PyAudio()
    stream = pa.open(
        format=pyaudio.paInt16,
        channels=1,
        rate=44100,
        input=True,
        frames_per_buffer=1024,
    )

    async with websockets.connect(DG_URL) as ws:
        print("🟢 Connected to Deepgram, start speaking…")
        
        async def send_audio():
            try:
                while True:
                    data = stream.read(1024, exception_on_overflow=False)
                    await ws.send(data)  # send raw PCM bytes
            except websockets.ConnectionClosed:
                pass

        async def receive_transcripts():
            try:
                async for message in ws:
                    res = json.loads(message)
                    # ignore interim results unless you want them; only print finals
                    if res.get("is_final"):
                        transcript = res["channel"]["alternatives"][0]["transcript"]
                        print(f"🗣  {transcript}")
            except websockets.ConnectionClosed:
                pass

        # Run sending and receiving concurrently
        await asyncio.gather(send_audio(), receive_transcripts())

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
