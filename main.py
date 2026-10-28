"""AgriVault prototype server.

POST /voice        -> a phone call arrives (set this as your number's webhook)
POST /voice/step   -> each thing the caller says (speech-to-text done by the provider)
POST /chat         -> the same chatbot over plain text (Telegram/WhatsApp/web can call this)
GET  /bookings     -> bookings collected so far
"""
from xml.sax.saxutils import escape

from fastapi import FastAPI, Form
from fastapi.responses import Response
from pydantic import BaseModel

import dialogue as d

app = FastAPI(title="AgriVault prototype")


def _speech_lang():
    return "ta-IN" if d.lang() == "ta" else "en-IN"


def _xml(body):
    return Response(content=f'<?xml version="1.0" encoding="UTF-8"?><Response>{body}</Response>',
                    media_type="application/xml")


def _ask(reply):
    """Speak the reply, then listen for the caller's answer."""
    lang = _speech_lang()
    return _xml(
        f'<Gather input="speech" language="{lang}" action="/voice/step" method="POST" '
        f'speechTimeout="auto" timeout="6"><Say language="{lang}">{escape(reply)}</Say></Gather>'
        f'<Redirect method="POST">/voice/step</Redirect>')  # runs only if nothing was heard


def _finish(reply):
    return _xml(f'<Say language="{_speech_lang()}">{escape(reply)}</Say><Hangup/>')


@app.post("/voice")
async def voice(CallSid: str = Form(""), From: str = Form("")):
    reply, done = d.handle(CallSid, "", From)
    return _finish(reply) if done else _ask(reply)


@app.post("/voice/step")
async def voice_step(CallSid: str = Form(""), From: str = Form(""),
                     SpeechResult: str = Form("")):
    reply, done = d.handle(CallSid, SpeechResult, From)
    return _finish(reply) if done else _ask(reply)


class ChatIn(BaseModel):
    session_id: str
    message: str = ""
    phone: str = "chat"


@app.post("/chat")
def chat(body: ChatIn):
    reply, done = d.handle(body.session_id, body.message, body.phone)
    return {"reply": reply, "done": done}


@app.get("/bookings")
def bookings():
    return d.list_bookings()


@app.get("/")
def health():
    return {"status": "AgriVault prototype running"}
