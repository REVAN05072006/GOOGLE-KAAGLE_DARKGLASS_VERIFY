# sessions.py
import uuid
import time
import threading

class InMemorySession:
    def __init__(self):
        self.lock = threading.Lock()
        self.sessions = {}
        self.last_cleanup = time.time()

    def create(self):
        sid = uuid.uuid4().hex[:12]
        with self.lock:
            self.sessions[sid] = {
                "created": time.time(),
                "captcha": None,
                "attempts": 0,
                "last_attempt": 0,
                "generation_count": 0
            }
            self._cleanup()
        return sid

    def get(self, sid):
        with self.lock:
            s = self.sessions.get(sid)
            if not s:
                return None
            if time.time() - s["created"] > 3600:
                del self.sessions[sid]
                return None
            return s

    def update(self, sid, data):
        with self.lock:
            if sid in self.sessions:
                self.sessions[sid].update(data)
                self._cleanup()

    def _cleanup(self):
        now = time.time()
        if now - self.last_cleanup > 300:
            expired = [k for k, v in self.sessions.items() if now - v["created"] > 3600]
            for k in expired:
                del self.sessions[k]
            self.last_cleanup = now

session_store = InMemorySession()
