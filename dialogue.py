"""AgriVault dialogue engine.

Collects booking details (crop, quantity, village, days) one question at a time,
confirms them, then hands the booking to the backend:
  1. saves it in a local SQLite database, and
  2. optionally POSTs it as JSON to BACKEND_URL (your real backend).

Pure standard library, so it can be tested without a phone or a web server.
"""
import base64
import json
import os
import random
import re
import sqlite3
import urllib.parse
import urllib.request
from contextlib import closing

SLOTS = ["crop", "quantity", "village", "days"]
TAMIL_DIGITS = str.maketrans("௦௧௨௩௪௫௬௭௮௯", "0123456789")

# canonical key -> (words to listen for, Tamil name used when speaking Tamil)
CROPS = {
    "paddy": (["paddy", "rice", "நெல்", "அரிசி"], "நெல்"),
    "groundnut": (["groundnut", "peanut", "நிலக்கடலை", "வேர்க்கடலை"], "நிலக்கடலை"),
    "onion": (["onion", "வெங்காயம்"], "வெங்காயம்"),
    "potato": (["potato", "உருளைக்கிழங்கு"], "உருளைக்கிழங்கு"),
    "tomato": (["tomato", "தக்காளி"], "தக்காளி"),
    "chilli": (["chilli", "chili", "மிளகாய்"], "மிளகாய்"),
    "banana": (["banana", "வாழை"], "வாழைப்பழம்"),
}
YES = {"yes", "yeah", "yep", "ok", "okay", "confirm", "correct", "ஆம்", "ஆமாம்", "சரி"}
NO = {"no", "nope", "cancel", "இல்லை", "வேண்டாம்"}

PROMPTS = {
    "en": {
        "greet": "Welcome to AgriVault cold storage booking.",
        "ask_crop": "Which crop do you want to store?",
        "ask_quantity": "How many quintals?",
        "ask_village": "Which village are you calling from?",
        "ask_days": "For how many days?",
        "confirm": "You want to store {quantity} quintals of {crop} from {village} "
                   "for {days} days. Say yes to confirm, or no to start again.",
        "done": "Your booking is confirmed. Your booking ID is {booking_id}. "
                "Your entry code is {code}. Thank you.",
        "unclear": "Sorry, I did not understand.",
        "restart": "Okay, let us start again.",
        "silent_end": "I could not hear you. Please call again. Goodbye.",
        "sms": "AgriVault booking {booking_id} confirmed: {quantity} quintals of {crop}, "
               "{village}, {days} days. Entry code: {code}.",
    },
    "ta": {
        "greet": "அக்ரிவால்ட் குளிர்பதனக் கிடங்கு முன்பதிவுக்கு வரவேற்கிறோம்.",
        "ask_crop": "எந்தப் பயிரை சேமிக்க வேண்டும்?",
        "ask_quantity": "எத்தனை குவிண்டால்?",
        "ask_village": "நீங்கள் எந்த ஊரில் இருக்கிறீர்கள்?",
        "ask_days": "எத்தனை நாட்களுக்கு?",
        "confirm": "{village} ஊரிலிருந்து {quantity} குவிண்டால் {crop}, {days} நாட்களுக்கு "
                   "சேமிக்க வேண்டும். உறுதிப்படுத்த ஆம் என்று சொல்லுங்கள், "
                   "மீண்டும் தொடங்க இல்லை என்று சொல்லுங்கள்.",
        "done": "உங்கள் முன்பதிவு உறுதியானது. முன்பதிவு எண் {booking_id}. "
                "நுழைவு குறியீடு {code}. நன்றி.",
        "unclear": "மன்னிக்கவும், புரியவில்லை.",
        "restart": "சரி, மீண்டும் தொடங்குவோம்.",
        "silent_end": "குரல் கேட்கவில்லை. மீண்டும் அழைக்கவும். நன்றி.",
        "sms": "அக்ரிவால்ட் முன்பதிவு {booking_id} உறுதி: {quantity} குவிண்டால் {crop}, "
               "{village}, {days} நாட்கள். நுழைவு குறியீடு: {code}.",
    },
}

SESSIONS = {}  # session id (call SID or chat id) -> state


# ---------- config helpers (read env each time so tests can switch) ----------
def lang():
    return "ta" if os.getenv("AGRIVAULT_LANG", "en").startswith("ta") else "en"


def db_path():
    return os.getenv("AGRIVAULT_DB", "agrivault.db")


def say(key, **kw):
    return PROMPTS[lang()][key].format(**kw)


def crop_label(key):
    return CROPS[key][1] if lang() == "ta" else key


# ---------- parsing ----------
def _number(text):
    m = re.search(r"\d+(?:\.\d+)?", text.translate(TAMIL_DIGITS))
    return float(m.group()) if m else None


def _find_crop(text):
    for key, (words, _) in CROPS.items():
        if any(w in text for w in words):
            return key
    return None


def _next_missing(s):
    for slot in SLOTS:
        if slot not in s["slots"]:
            return slot
    return None


def _next_prompt(s):
    slot = _next_missing(s)
    if slot:
        return say("ask_" + slot)
    sl = s["slots"]
    return say("confirm", quantity=sl["quantity"], crop=crop_label(sl["crop"]),
               village=sl["village"], days=sl["days"])


def _extract(s, text, expected=None):
    slots = s["slots"]
    t = text.lower()
    n = _number(text)
    if "crop" not in slots:
        crop = _find_crop(t)
        if crop:
            slots["crop"] = crop
    if "quantity" not in slots and n and (
            expected == "quantity" or re.search(r"quintal|குவிண்டால்", t)):
        slots["quantity"] = int(n) if n == int(n) else n
    if "days" not in slots and n and expected == "days":
        slots["days"] = int(n)
    if "village" not in slots and expected == "village" and text:
        slots["village"] = text.strip(" .,!?").title()


def _remember(s, reply):
    s["last"] = reply
    return reply


# ---------- the conversation ----------
def handle(sid, text, phone=""):
    """Process one caller/chat turn. Returns (reply_text, conversation_finished)."""
    text = (text or "").strip()
    s = SESSIONS.get(sid)

    if s is None:  # first turn: greet, and pick up anything already said
        s = SESSIONS[sid] = {"slots": {}, "stage": "collect", "silent": 0,
                             "last": "", "phone": phone}
        _extract(s, text, expected=None)
        if _next_missing(s) is None:
            s["stage"] = "confirm"
        return _remember(s, say("greet") + " " + _next_prompt(s)), False

    if not text:  # caller said nothing: repeat, then give up after 3 tries
        s["silent"] += 1
        if s["silent"] >= 3:
            SESSIONS.pop(sid, None)
            return say("silent_end"), True
        return s["last"], False
    s["silent"] = 0

    if s["stage"] == "confirm":
        words = {w.strip(".,!?") for w in text.lower().split()}
        if words & YES:
            booking_id, code = create_booking(s["phone"] or phone, s["slots"])
            sl = s["slots"]
            send_sms(s["phone"] or phone, say(
                "sms", booking_id=booking_id, code=code, quantity=sl["quantity"],
                crop=crop_label(sl["crop"]), village=sl["village"], days=sl["days"]))
            SESSIONS.pop(sid, None)
            return say("done", booking_id=booking_id, code=" ".join(code)), True
        if words & NO:
            s["slots"], s["stage"] = {}, "collect"
            return _remember(s, say("restart") + " " + _next_prompt(s)), False
        return _remember(s, say("unclear") + " " + _next_prompt(s)), False

    before = dict(s["slots"])
    _extract(s, text, expected=_next_missing(s))
    if s["slots"] == before:  # nothing understood
        return _remember(s, say("unclear") + " " + _next_prompt(s)), False
    if _next_missing(s) is None:
        s["stage"] = "confirm"
    return _remember(s, _next_prompt(s)), False


# ---------- hand-off to the backend ----------
def create_booking(phone, slots):
    code = f"{random.randint(0, 9999):04d}"
    with closing(sqlite3.connect(db_path())) as db:
        db.execute("""CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT, phone TEXT, crop TEXT,
            quantity REAL, village TEXT, days INTEGER, entry_code TEXT,
            status TEXT, created_at TEXT)""")
        cur = db.execute(
            "INSERT INTO bookings (phone, crop, quantity, village, days, entry_code,"
            " status, created_at) VALUES (?,?,?,?,?,?,?,datetime('now'))",
            (phone, slots["crop"], slots["quantity"], slots["village"],
             slots["days"], code, "confirmed"))
        db.commit()
        booking_id = cur.lastrowid
    _forward({"booking_id": booking_id, "phone": phone, "entry_code": code, **slots})
    return booking_id, code


def send_sms(phone, text):
    """Send the booking receipt by SMS (Twilio REST API, set TWILIO_SID/TOKEN/FROM).

    Without those settings it only prints the message, so tests and demos still run.
    """
    sid, token = os.getenv("TWILIO_SID"), os.getenv("TWILIO_TOKEN")
    sender = os.getenv("TWILIO_FROM")
    if not (sid and token and sender and phone):
        print(f"[SMS not sent, no provider configured] to {phone}: {text}")
        return False
    try:
        data = urllib.parse.urlencode({"To": phone, "From": sender, "Body": text}).encode()
        req = urllib.request.Request(
            f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
            data=data, method="POST")
        auth = base64.b64encode(f"{sid}:{token}".encode()).decode()
        req.add_header("Authorization", "Basic " + auth)
        urllib.request.urlopen(req, timeout=5)
        return True
    except Exception as exc:  # a failed SMS must not break the call
        print("SMS failed:", exc)
        return False


def _forward(payload):
    """POST the booking to your real backend if BACKEND_URL is set."""
    url = os.getenv("BACKEND_URL")
    if not url:
        return
    try:
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode(), method="POST",
            headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=5)
    except Exception as exc:  # never break the call because the backend is down
        print("backend forward failed:", exc)


def list_bookings():
    with closing(sqlite3.connect(db_path())) as db:
        db.row_factory = sqlite3.Row
        try:
            return [dict(r) for r in db.execute("SELECT * FROM bookings ORDER BY id DESC")]
        except sqlite3.OperationalError:  # table not created yet
            return []
