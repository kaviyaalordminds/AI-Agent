"""Standalone login-hang diagnostic — run directly on the machine where the
20-second login hang is happening, with the backend NOT necessarily running
(this talks to Postgres and Argon2 directly, bypassing FastAPI entirely).

Usage (from the backend/ directory, same venv/.env the backend itself uses):

    python diagnose_login.py your@email.com

It times, in isolation, the exact operations login() performs:
  1. Opening a SQLAlchemy engine connection to DATABASE_URL (connection
     acquisition — the classic "Windows localhost is slow" suspect).
  2. A raw "SELECT 1" on that connection (proves the socket/round-trip
     itself is fast once connected).
  3. The actual `SELECT * FROM users WHERE email = ...` lookup query.
  4. An isolated Argon2 hash + verify round-trip using a throwaway string
     (NOT your real password — this only measures how fast the Argon2
     algorithm runs on this machine's CPU, independent of any real
     credential).

Never prints your password, any password hash, session tokens, or
SECRET_KEY — only elapsed times and non-secret metadata (whether a user
row was found, its id/email-verified flag).

Any single step taking more than ~1 second is the culprit; everything
below that is expected to be tens of milliseconds.
"""
import sys
import time

if len(sys.argv) != 2:
    print("Usage: python diagnose_login.py your@email.com")
    sys.exit(1)

target_email = sys.argv[1].strip().lower()


def step(label):
    print(f"\n--- {label} ---")
    return time.perf_counter()


def done(t0, label):
    elapsed = time.perf_counter() - t0
    flag = "  <-- SLOW (>1s)" if elapsed > 1.0 else ""
    print(f"[{label}] completed in {elapsed:.3f}s{flag}")
    return elapsed


total_start = time.perf_counter()
results = {}

# --- 0. Import app config / settings (loads .env) ---
t0 = step("0. Load settings (.env) — no I/O yet")
from app.core.config import get_settings  # noqa: E402

settings = get_settings()
results["load_settings"] = done(t0, "load_settings")
# Print the DB host/port only (never the password segment of the URL).
try:
    from urllib.parse import urlsplit

    parsed = urlsplit(settings.database_url)
    safe_target = f"{parsed.hostname}:{parsed.port}{parsed.path}"
except Exception:
    safe_target = "<could not parse DATABASE_URL>"
print(f"DATABASE_URL target (host/port/db only): {safe_target}")

# --- 1. Raw engine connection (connection acquisition) ---
t0 = step("1. Open SQLAlchemy engine connection (connection acquisition)")
from sqlalchemy import create_engine, text  # noqa: E402

engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)
conn = engine.connect()
results["connect"] = done(t0, "connect")

# --- 2. SELECT 1 (raw round-trip once connected) ---
t0 = step("2. SELECT 1 (raw round-trip on the already-open connection)")
conn.execute(text("SELECT 1"))
results["select_1"] = done(t0, "select_1")

# --- 3. Real user lookup query (same shape as login()'s query) ---
t0 = step(f"3. User lookup for {target_email!r} (same query login() runs)")
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.models.user import User  # noqa: E402

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
db = SessionLocal()
user = db.query(User).filter(User.email == target_email).first()
results["user_lookup"] = done(t0, "user_lookup")
if user is None:
    print(f"No user found for {target_email!r} (this alone does not explain a hang — "
          f"login() returns a fast 401 in that case).")
else:
    print(f"Found user id={user.id}, email_verified={user.email_verified}, is_active={user.is_active}")

db.close()
conn.close()

# --- 4. Isolated Argon2 hash + verify (throwaway string, NOT your password) ---
t0 = step("4. Argon2 hash+verify round-trip (throwaway test string, not your real password)")
from argon2 import PasswordHasher  # noqa: E402

hasher = PasswordHasher()
test_hash = hasher.hash("diagnostic-only-value-not-a-real-password")
hasher.verify(test_hash, "diagnostic-only-value-not-a-real-password")
results["argon2"] = done(t0, "argon2")

# --- Summary ---
total_elapsed = time.perf_counter() - total_start
print("\n=== SUMMARY ===")
for label, elapsed in results.items():
    flag = "  <-- SLOW (>1s)" if elapsed > 1.0 else ""
    print(f"{label:20s} {elapsed:8.3f}s{flag}")
print(f"{'TOTAL':20s} {total_elapsed:8.3f}s")
print(
    "\nIf every step above is well under 1s but the browser still hangs for "
    "~20s on POST /auth/login, the bottleneck is NOT the database, the user "
    "lookup, or Argon2 — it is somewhere between the browser and the "
    "FastAPI process itself (e.g. rate limiter, CORS/OPTIONS preflight, "
    "session-cookie write, an antivirus/firewall intercepting the loopback "
    "connection, or a proxy). If one step IS slow, that pinpoints the "
    "exact bottleneck to fix next."
)
