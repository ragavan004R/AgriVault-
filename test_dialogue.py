"""Simulated conversations. Run: python test_dialogue.py (no server or phone needed)."""
import os
import tempfile

os.environ["AGRIVAULT_DB"] = os.path.join(tempfile.mkdtemp(), "test.db")
import dialogue as d


def talk(sid, lines, phone="+919999900000"):
    reply, done = d.handle(sid, "", phone)
    print("BOT :", reply)
    for line in lines:
        print("USER:", line)
        reply, done = d.handle(sid, line, phone)
        print("BOT :", reply)
    return done


print("--- English, step by step ---")
os.environ["AGRIVAULT_LANG"] = "en"
assert talk("a", ["paddy", "30 quintals", "Thanjavur", "10", "yes"])

print("\n--- English, everything in one sentence ---")
reply, _ = d.handle("b", "I want to store 50 quintals of onion", "+919888800000")
print("BOT :", reply)
for line in ["Madurai", "7", "yes"]:
    print("USER:", line)
    reply, done = d.handle("b", line, "+919888800000")
    print("BOT :", reply)
assert done

print("\n--- Caller says no, restarts, then books ---")
assert talk("c", ["groundnut", "20", "Salem", "5", "no", "tomato", "15", "Erode", "3", "yes"])

print("\n--- Tamil ---")
os.environ["AGRIVAULT_LANG"] = "ta"
assert talk("d", ["நெல்", "௩௦ குவிண்டால்", "தஞ்சாவூர்", "10", "ஆம்"])

print("\n--- Silence ends the call politely ---")
os.environ["AGRIVAULT_LANG"] = "en"
d.handle("e", "", "+910000000000")
for _ in range(3):
    reply, done = d.handle("e", "", "+910000000000")
print("BOT :", reply)
assert done

rows = d.list_bookings()
print("\nBookings saved:", len(rows))
for r in rows:
    print(r)
assert len(rows) == 4
print("\nAll tests passed")
