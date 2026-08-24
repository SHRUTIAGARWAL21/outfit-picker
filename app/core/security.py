"""Password hashing.

The golden rule of passwords: NEVER store the real password. If our database
ever leaked, the attacker must not learn anyone's password.

Instead we store a "hash" — a scrambled, one-way fingerprint of the password.
You can turn a password INTO a hash, but you cannot turn a hash BACK into the
password. At login we hash what the user typed and check it matches the stored
hash.

We use Argon2id, the current recommended algorithm. It is deliberately slow and
memory-hungry, which makes mass password-guessing attacks impractical.
"""

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

# One shared hasher, using the library's safe defaults.
_hasher = PasswordHasher()


def hash_password(plain: str) -> str:
    """Turn a plain password into a storable Argon2 hash."""
    return _hasher.hash(plain)


def verify_password(stored_hash: str, plain: str) -> bool:
    """Does `plain` match the stored hash? Returns True/False, never raises.

    Used at login time (next step). We return False on any problem rather than
    letting an exception escape.
    """
    try:
        _hasher.verify(stored_hash, plain)
        return True
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False
