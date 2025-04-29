# main.py
import os
import json
import asyncio
import base64

from fastapi import FastAPI, WebSocket, Query
from fastapi.responses import PlainTextResponse
from twilio.twiml.voice_response import VoiceResponse
from twilio.rest import Client
from dotenv import load_dotenv
import websockets as dg_ws_client

from fastapi.responses import PlainTextResponse

# 1) Load env & creds
load_dotenv()
TWILIO_SID    = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_TOKEN  = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_NUMBER = os.getenv("TWILIO_NUMBER")
PASSENGER_NO  = os.getenv("PASSENGER_NUMBER")
DG_API_KEY    = os.getenv("DEEPGRAM_API_KEY")

# 2) Instantiate FastAPI app
app = FastAPI()

# 3) Configure Twilio REST client
twilio_client = Client(TWILIO_SID, TWILIO_TOKEN)

# 4) TwiML /voice webhook
@app.post("/voice")
async def voice_webhook():
    resp = VoiceResponse()
    # start streaming media to our /media WS
    resp.start().stream(url=f"wss://YOUR_DOMAIN/media?callSid={{{{CallSid}}}}")
    # bridge to passenger
    resp.dial(PASSENGER_NO)
    return PlainTextResponse(str(resp), media_type="application/xml")

@app.get("/")
async def health_check():
    return PlainTextResponse("✅ Service is up", status_code=200)

# 5) Media‐stream websocket handler
FRAUD_KEYWORDS = {"otp", "pin", "transfer money", "account number"}

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
    print(f"[{callSid}] WS open")
    
    # connect Deepgram
    async with dg_ws_client.connect(DG_URL) as dg_ws:
        async def forward_audio():
            async for msg in ws.iter_text():
                payload = json.loads(msg)["media"]["payload"]
                await dg_ws.send(base64.b64decode(payload))

        async def process_stt():
            async for dg_msg in dg_ws:
                text = json.loads(dg_msg)["channel"]["alternatives"][0]["transcript"].lower()
                if any(kw in text for kw in FRAUD_KEYWORDS):
                    print(f"[{callSid}] 🚨 Fraud keyword detected: {text}")
                    # hangup via Twilio REST API
                    twilio_client.calls(callSid).update(twiml="<Response><Hangup/></Response>")
                    break

        await asyncio.gather(forward_audio(), process_stt())

    await ws.close()
    print(f"[{callSid}] WS closed")

# 6) Run with: uvicorn main:app --reload --port 8000
