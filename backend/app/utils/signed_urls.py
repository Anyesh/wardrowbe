"""Signed URL utilities for secure image access."""

import hashlib
import hmac
import time

from app.config import get_settings

# Default expiry: 1 hour
DEFAULT_EXPIRY_SECONDS = 3600


def sign_image_url(path: str, expiry_seconds: int = DEFAULT_EXPIRY_SECONDS) -> str:
    """
    Generate a signed URL for an image path.

    Args:
        path: The image path (e.g., "user_id/filename.jpg")
        expiry_seconds: How long the URL is valid (default 1 hour)

    Returns:
        Signed URL with signature and expiry parameters
    """
    settings = get_settings()
    expires = int(time.time()) + expiry_seconds

    # Create signature: HMAC(secret, path + expires)
    message = f"{path}:{expires}"
    signature = hmac.new(
        settings.secret_key.encode(),
        message.encode(),
        hashlib.sha256
    ).hexdigest()[:32]  # Use first 32 chars for shorter URLs

    return f"/api/v1/images/{path}?expires={expires}&sig={signature}"


def verify_signature(path: str, expires: str, signature: str) -> bool:
    """
    Verify a signed URL signature.

    Args:
        path: The image path
        expires: Expiry timestamp as string
        signature: The provided signature

    Returns:
        True if signature is valid and not expired
    """
    settings = get_settings()

    # Check expiry
    try:
        expiry_time = int(expires)
        if time.time() > expiry_time:
            return False
    except (ValueError, TypeError):
        return False

    # Verify signature
    message = f"{path}:{expires}"
    expected_signature = hmac.new(
        settings.secret_key.encode(),
        message.encode(),
        hashlib.sha256
    ).hexdigest()[:32]

    return hmac.compare_digest(signature, expected_signature)
