import hashlib
import secrets

# Raw tokens (session cookies, email verification links, password reset
# links) are only ever handed to the client. The database stores a SHA-256
# hash of the token, so a leaked database dump cannot be used to forge
# sessions or reset links.


def generate_token(n_bytes: int = 32) -> str:
    return secrets.token_urlsafe(n_bytes)


def hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def constant_time_compare(a: str, b: str) -> bool:
    return secrets.compare_digest(a, b)
