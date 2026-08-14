from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHash

# Argon2id (argon2-cffi's default `PasswordHasher` uses the Argon2id variant).
_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        _hasher.verify(password_hash, password)
        return True
    except (VerifyMismatchError, VerificationError, InvalidHash):
        return False


def needs_rehash(password_hash: str) -> bool:
    """True when stored hash params are weaker than current recommended params."""
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHash:
        return True
