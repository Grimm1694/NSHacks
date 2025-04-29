import os
import json
import asyncio
import base64

from fastapi import FastAPI, WebSocket, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from twilio.twiml.voice_response import VoiceResponse
from twilio.rest import Client
import websockets
from dotenv import load_dotenv

# ─── 1) Load & validate environment ─────────────────────────────────────────────

load_dotenv()  # read .env

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN  = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_NUMBER      = os.getenv("TWILIO_NUMBER")
PASSENGER_NUMBER   = os.getenv("PASSENGER_NUMBER")
DG_API_KEY         = os.getenv("DEEPGRAM_API_KEY")
DOMAIN             = os.getenv("PUBLIC_DOMAIN")  
#   e.g. abcd1234.ngrok.io or your real HTTPS domain

if not all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN,
            TWILIO_NUMBER, PASSENGER_NUMBER,
            DG_API_KEY, DOMAIN]):
    raise RuntimeError(
        "Missing one of: TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, "
        "TWILIO_NUMBER, PASSENGER_NUMBER, DEEPGRAM_API_KEY, PUBLIC_DOMAIN"
    )

# ─── 2) FastAPI + CORS + Twilio client ────────────────────────────────────────

app = FastAPI(title="Fraud Detection Proxy")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# ─── 3) In-memory WebSocket manager for frontend clients ───────────────────────

class ConnectionManager:
    def __init__(self):
        self.connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.connections.append(ws)

    def disconnect(self, ws: WebSocket):
        self.connections.remove(ws)

    async def broadcast(self, message: dict):
        for ws in self.connections:
            await ws.send_json(message)

manager = ConnectionManager()

# ─── 4) Health-check ───────────────────────────────────────────────────────────

@app.get("/")
async def health_check():
    return PlainTextResponse("✅ Service is up")

# ─── 5) Twilio Voice webhook: start media stream + dial passenger ─────────────

@app.post("/voice")
async def voice_webhook():
    twiml = VoiceResponse()
    # 1) Launch media stream
    stream_url = f"wss://{DOMAIN}/media?callSid={{{{CallSid}}}}"
    twiml.start().stream(url=stream_url)
    # 2) Bridge to the passenger’s device
    twiml.dial(PASSENGER_NUMBER)
    return PlainTextResponse(str(twiml), media_type="application/xml")

# ─── 6) Deepgram media-stream & fraud detection ────────────────────────────────

FRAUD_KEYWORDS = {
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
}

DG_URL = (
    "wss://api.deepgram.com/v1/listen"
    f"?access_token={DG_API_KEY}"
    "&encoding=linear16"
    "&sample_rate=16000"
    "&channels=1"
    "&punctuate=true"
    "&interim_results=true"
)

@app.websocket("/media")
async def media_stream(ws: WebSocket, callSid: str = Query(...)):
    await ws.accept()
    print(f"[{callSid}] 📡 Media WS connected")

    async with websockets.connect(DG_URL) as dg_ws:
        async def forward_audio():
            async for msg in ws.iter_text():
                data = json.loads(msg)
                payload = data.get("media", {}).get("payload")
                if not payload:
                    continue
                pcm = base64.b64decode(payload)
                await dg_ws.send(pcm)

        async def receive_stt():
            async for dg_msg in dg_ws:
                res = json.loads(dg_msg)
                transcript = res["channel"]["alternatives"][0]["transcript"].strip()
                is_final   = res.get("is_final", False)
                if not transcript:
                    continue
                print(f"[{callSid}] 🗣 {transcript}")

                # Detect fraud keywords
                text_lower = transcript.lower()
                detected = [kw for kw in FRAUD_KEYWORDS if kw in text_lower]
                fraud = bool(detected)

                # Broadcast to any UI clients
                await manager.broadcast({
                    "callSid":        callSid,
                    "transcript":     transcript,
                    "is_final":       is_final,
                    "fraud_detected": fraud,
                    "keywords":       detected,
                })

                # If fraud, hang up the call immediately
                if fraud:
                    print(f"[{callSid}] 🚨 Fraud! Hanging up")
                    twilio_client.calls(callSid).update(
                        twiml="<Response><Hangup/></Response>"
                    )
                    break

        # Run both loops concurrently
        await asyncio.gather(forward_audio(), receive_stt())

    await ws.close()
    print(f"[{callSid}] 📴 Media WS closed")

# ─── 7) Front-end WebSocket for live updates ───────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await manager.connect(ws)
    try:
        while True:
            # Keep the connection open; we never expect the client to send data here
            await ws.receive_text()
    except:
        pass
    finally:
        manager.disconnect(ws)

# ─── 8) Run the app ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
