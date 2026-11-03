# AgriVault call + chatbot prototype

A caller (or chat user) is asked for **crop, quantity, village and days**. The bot confirms
the details, saves the booking and hands it to the backend, then gives a booking ID and a
4-digit entry code.

## Files
- `dialogue.py`: the chatbot logic and the hand-off to the backend (standard library only)
- `main.py`: FastAPI server with the phone-call webhook, a chat endpoint and a bookings list
- `test_dialogue.py`: simulated English and Tamil conversations (runs without a server)
- `requirements.txt`

## 1. Run the test (no setup needed)
    python test_dialogue.py

## 2. Run the server
    pip install -r requirements.txt
    uvicorn main:app --reload --port 8000

Try the chatbot without a phone:

    curl -X POST localhost:8000/chat -H "Content-Type: application/json" \
      -d '{"session_id":"t1","message":"hi"}'
    curl -X POST localhost:8000/chat -H "Content-Type: application/json" \
      -d '{"session_id":"t1","message":"paddy"}'

Continue with quantity, village, days and "yes". Then open `localhost:8000/bookings`.

## 3. Connect a real phone number
1. Expose your server: `ngrok http 8000` and copy the https URL.
2. Buy a voice number from a provider (Twilio shown here; other providers can send the
   same kind of webhook).
3. In the number's settings, set "A call comes in" to `POST https://<your-ngrok-url>/voice`.
4. Call the number. The provider converts speech to text and sends it to `/voice/step`.

The webhook format used here is Twilio's (`CallSid`, `From`, `SpeechResult`). Exotel,
Knowlarity or Ozonetel use different formats, so `main.py` would need a small adapter.

## 4. Hand bookings to your backend
Set `BACKEND_URL` and every confirmed booking is also POSTed to it as JSON:

    BACKEND_URL=https://your-backend/api/bookings uvicorn main:app --port 8000

Payload: `booking_id, phone, entry_code, crop, quantity, village, days`.

## Settings (environment variables)
- `AGRIVAULT_LANG`: `en` (default) or `ta` for Tamil prompts and speech recognition
- `AGRIVAULT_DB`: SQLite file path (default `agrivault.db`)
- `BACKEND_URL`: optional, where to forward confirmed bookings
- `TWILIO_SID`, `TWILIO_TOKEN`, `TWILIO_FROM`: optional, send the SMS receipt through Twilio
  (without them the SMS text is only printed in the server log)

## Not done yet
- Matching the booking to an actual cold storage and checking free capacity
- Sending SMS through an Indian provider (MSG91 or Fast2SMS need DLT registration of the sender ID and message template)
- Smarter understanding (the bot uses keyword and number matching, not an LLM)
- Tamil voice quality and recognition accuracy need testing on a live call, and the
  provider's Tamil text-to-speech voice should be checked
- Session state is kept in memory, so restarting the server drops calls in progress
