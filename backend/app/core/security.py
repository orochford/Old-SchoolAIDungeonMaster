import secrets
from datetime import datetime, timedelta
from typing import Optional


def generate_session_token(length: int = 32) -> str:
    """Generate a secure random session token."""
    return secrets.token_urlsafe(length)


def generate_api_key() -> str:
    """Generate a secure API key."""
    return secrets.token_hex(32)


class SessionManager:
    """Simple in-memory session manager for game sessions."""

    def __init__(self, session_timeout_hours: int = 24):
        self._sessions: dict[str, dict] = {}
        self._timeout = timedelta(hours=session_timeout_hours)

    def create_session(self, session_id: str, data: dict) -> str:
        token = generate_session_token()
        self._sessions[token] = {
            "session_id": session_id,
            "data": data,
            "created_at": datetime.utcnow(),
            "last_active": datetime.utcnow(),
        }
        return token

    def get_session(self, token: str) -> Optional[dict]:
        session = self._sessions.get(token)
        if not session:
            return None

        if datetime.utcnow() - session["last_active"] > self._timeout:
            del self._sessions[token]
            return None

        session["last_active"] = datetime.utcnow()
        return session

    def invalidate_session(self, token: str) -> bool:
        if token in self._sessions:
            del self._sessions[token]
            return True
        return False

    def cleanup_expired(self) -> int:
        now = datetime.utcnow()
        expired = [
            token
            for token, session in self._sessions.items()
            if now - session["last_active"] > self._timeout
        ]
        for token in expired:
            del self._sessions[token]
        return len(expired)


session_manager = SessionManager()
