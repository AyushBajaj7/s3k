"""
Authentication and Cryptographic Verification Module
FlowSync / BuyOps AI - S3K Case Study 03
Implements:
1. PBKDF2-HMAC-SHA256 password hashing & verification
2. Signed JWT Token issuance and cryptographic validation (PyJWT)
3. Role and permission verification
"""

import hashlib
import hmac
import os
import secrets
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
import jwt
from fastapi import HTTPException, status, Header

def resolve_jwt_secret() -> str:
    """
    Enforces JWT secret key configuration via environment variable or .env file.
    Rejects predictable static defaults: if unconfigured, generates an ephemeral
    cryptographically strong 256-bit key for this process runtime.
    """
    secret = os.environ.get("JWT_SECRET_KEY")
    if secret:
        return secret

    # Check for .env file in root
    env_file = Path(__file__).resolve().parent.parent / ".env"
    if env_file.exists():
        try:
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("JWT_SECRET_KEY="):
                        val = line.split("=", 1)[1].strip().strip('"\'')
                        if val:
                            os.environ["JWT_SECRET_KEY"] = val
                            return val
        except Exception:
            pass

    # Ephemeral secure entropy fallback (never a predictable static string)
    generated = secrets.token_hex(32)
    os.environ["JWT_SECRET_KEY"] = generated
    return generated

JWT_SECRET_KEY = resolve_jwt_secret()
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24

def hash_password(password: str, salt: Optional[str] = None) -> str:
    """Hashes a password using PBKDF2-HMAC-SHA256 with 100,000 iterations."""
    if not salt:
        salt = os.urandom(16).hex()
    pwd_hash = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        100000
    ).hex()
    return f"{salt}${pwd_hash}"

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plain password against stored salt$hash."""
    try:
        salt, stored_hash = hashed_password.split("$")
        computed_hash = hashlib.pbkdf2_hmac(
            'sha256',
            plain_password.encode('utf-8'),
            salt.encode('utf-8'),
            100000
        ).hex()
        return hmac.compare_digest(stored_hash, computed_hash)
    except Exception:
        return False

def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Encodes and cryptographically signs a JWT access token with claims."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(hours=JWT_EXPIRATION_HOURS))
    to_encode.update({"exp": expire, "iat": datetime.now(timezone.utc)})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return encoded_jwt

def decode_access_token(token: str) -> Dict[str, Any]:
    """Decodes, verifies signature, and validates expiration of a JWT token."""
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed: JWT Token has expired. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed: Invalid token signature or malformed payload.",
            headers={"WWW-Authenticate": "Bearer"},
        )
