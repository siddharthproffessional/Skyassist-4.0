"""Authentication + role-based access control (backend-enforced).

DEMONSTRATION AUTHENTICATION: synthetic accounts with PBKDF2-hashed demo passwords. This is not
production identity verification — a real deployment should plug in the airport's identity provider
(e.g. OIDC/SAML) behind the same `authenticate()` / `Principal` interface.
"""
import hashlib
import hmac
import os
from dataclasses import dataclass
from typing import Optional

from db import query_one, tx, utcnow

PBKDF2_ITERATIONS = int(os.getenv("SKYASSIST_PBKDF2_ITERATIONS", "120000"))

PASSENGER, COORDINATOR = "PASSENGER", "COORDINATOR"


class AuthError(Exception):
    pass


class PermissionDenied(Exception):
    pass


@dataclass(frozen=True)
class Principal:
    username: str
    role: str
    display_name: str
    booking_ref: Optional[str] = None


def hash_password(password: str, salt: Optional[str] = None):
    salt = salt or os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), PBKDF2_ITERATIONS).hex()
    return digest, salt


def authenticate(username: str, password: str, expected_role: Optional[str] = None) -> Principal:
    username = (username or "").strip()
    row = query_one("SELECT * FROM users WHERE (username=? OR username=?) AND active=1",
                    (username, username.upper()))
    if not row:
        raise AuthError("Unknown account or wrong password.")
    digest, _ = hash_password(password or "", row["salt"])
    if not hmac.compare_digest(digest, row["password_hash"]):
        _audit(username, "LOGIN_FAILED")
        raise AuthError("Unknown account or wrong password.")
    if expected_role and row["role"] != expected_role:
        _audit(username, "LOGIN_WRONG_PORTAL", expected_role)
        raise AuthError(f"This account cannot sign in to the {expected_role.lower()} portal.")
    _audit(row["username"], "LOGIN", row["role"])
    return Principal(row["username"], row["role"], row["display_name"], row["booking_ref"])


def _audit(actor, action, detail=None):
    with tx() as con:
        con.execute("INSERT INTO audit_log(actor,action,detail,created_at) VALUES(?,?,?,?)",
                    (actor, action, detail, utcnow()))


# ------------------------------------------------------------------ permission checks (used by every service)
def require_role(principal: Optional[Principal], role: str):
    if principal is None or principal.role != role:
        raise PermissionDenied(f"This action requires the {role.lower()} role.")


def require_booking_access(principal: Optional[Principal], booking_ref: str):
    """Passengers may only read their own booking. Coordinators may read any booking."""
    if principal is None:
        raise PermissionDenied("Sign in required.")
    if principal.role == COORDINATOR:
        return
    if principal.role == PASSENGER and principal.booking_ref == booking_ref:
        return
    raise PermissionDenied("You can only view your own booking.")
