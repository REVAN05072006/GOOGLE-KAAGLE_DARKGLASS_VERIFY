# security.py
import os
import time
import hmac
import hashlib
from dotenv import load_dotenv
load_dotenv()

HMAC_SECRET = os.getenv("CAPTCHA_HMAC_SECRET")
if not HMAC_SECRET:
    raise SystemExit("ERROR: Add CAPTCHA_HMAC_SECRET to your .env")

WINDOW_SECONDS = 300  # 5-minute window for signature tolerance

def sign_payload(session_id: str, payload_str: str) -> str:
    ts = str(int(time.time() // WINDOW_SECONDS))
    msg = f"{session_id}|{payload_str}|{ts}"
    return hmac.new(HMAC_SECRET.encode(), msg.encode(), hashlib.sha256).hexdigest()

def verify_signature(session_id: str, payload_str: str, signature: str) -> bool:
    ts_now = int(time.time() // WINDOW_SECONDS)
    for offset in (0, -1):  # allow current and previous window
        ts = str(ts_now + offset)
        msg = f"{session_id}|{payload_str}|{ts}"
        expected = hmac.new(HMAC_SECRET.encode(), msg.encode(), hashlib.sha256).hexdigest()
        if hmac.compare_digest(expected, signature):
            return True
    return False
