"""Kalshi authentication.

Handles API key + RSA private key authentication for Kalshi REST and WebSocket connections.
Kalshi uses HMAC-style signing with RSA keys.
"""

from __future__ import annotations

import base64
import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

logger = logging.getLogger(__name__)

# Kalshi API endpoints
KALSHI_API_BASE = "https://api.elections.kalshi.com/trade-api/v2"
KALSHI_DEMO_API_BASE = "https://demo-api.kalshi.co/trade-api/v2"


@dataclass
class KalshiCredentials:
    """Kalshi API credentials.

    Attributes:
        api_key: Kalshi API key (also called key_id)
        private_key_path: Path to RSA private key PEM file
        demo: Whether to use the demo environment
    """

    api_key: str
    private_key_path: str
    demo: bool = False

    @property
    def base_url(self) -> str:
        """Return the appropriate API base URL."""
        return KALSHI_DEMO_API_BASE if self.demo else KALSHI_API_BASE


class KalshiAuth:
    """Manages Kalshi API key authentication.

    Kalshi uses RSA key signing for authentication:
    1. Create a signature of: timestamp + method + path
    2. Sign with RSA private key using PSS padding
    3. Include signature in request headers
    """

    def __init__(self, credentials: KalshiCredentials) -> None:
        """Initialize with credentials.

        Args:
            credentials: Kalshi API credentials
        """
        self._credentials = credentials
        self._private_key: rsa.RSAPrivateKey | None = None
        self._load_private_key()

    def _load_private_key(self) -> None:
        """Load the RSA private key from PEM file."""
        key_path = Path(self._credentials.private_key_path)
        if not key_path.exists():
            raise FileNotFoundError(
                f"Private key file not found: {self._credentials.private_key_path}"
            )

        with open(key_path, "rb") as f:
            loaded_key = serialization.load_pem_private_key(
                f.read(),
                password=None,
            )

        if not isinstance(loaded_key, rsa.RSAPrivateKey):
            raise AuthenticationError("Private key must be RSA")

        self._private_key = loaded_key
        logger.info("Loaded Kalshi private key")

    @property
    def base_url(self) -> str:
        """Return the API base URL."""
        return self._credentials.base_url

    @property
    def is_demo(self) -> bool:
        """Return True if using demo environment."""
        return self._credentials.demo

    @property
    def api_key(self) -> str:
        """Return the API key."""
        return self._credentials.api_key

    def is_authenticated(self) -> bool:
        """Return True if we have a valid key loaded."""
        return self._private_key is not None

    async def ensure_authenticated(self) -> str:
        """Ensure we have valid credentials.

        Returns:
            The API key

        Raises:
            AuthenticationError: If private key not loaded
        """
        if not self.is_authenticated():
            raise AuthenticationError("Private key not loaded")
        return self._credentials.api_key

    def sign_request(
        self,
        method: str,
        path: str,
        timestamp: int | None = None,
    ) -> tuple[str, int]:
        """Sign a request for Kalshi API.

        Args:
            method: HTTP method (GET, POST, etc.)
            path: Request path (e.g., /trade-api/v2/portfolio/balance)
            timestamp: Unix timestamp in milliseconds (optional, uses current time)

        Returns:
            Tuple of (signature, timestamp)

        Raises:
            AuthenticationError: If signing fails
        """
        if self._private_key is None:
            raise AuthenticationError("Private key not loaded")

        if timestamp is None:
            timestamp = int(time.time() * 1000)

        # Message to sign: timestamp + method + path
        message = f"{timestamp}{method.upper()}{path}"
        message_bytes = message.encode("utf-8")

        # Sign with RSA-PSS
        signature = self._private_key.sign(
            message_bytes,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH,
            ),
            hashes.SHA256(),
        )

        # Base64 encode the signature
        signature_b64 = base64.b64encode(signature).decode("utf-8")

        return signature_b64, timestamp

    def get_auth_headers(
        self,
        method: str,
        path: str,
    ) -> dict[str, str]:
        """Get headers for authenticated requests.

        Args:
            method: HTTP method
            path: Request path

        Returns:
            Dict with authentication headers
        """
        signature, timestamp = self.sign_request(method, path)

        return {
            "KALSHI-ACCESS-KEY": self._credentials.api_key,
            "KALSHI-ACCESS-SIGNATURE": signature,
            "KALSHI-ACCESS-TIMESTAMP": str(timestamp),
        }

    @property
    def token(self) -> str | None:
        """Return token for WebSocket auth.

        For WebSocket, we need to get a token via REST API first.
        """
        # WebSocket uses a different auth flow - login to get token
        return None

    async def get_websocket_token(self) -> str:
        """Get a token for WebSocket authentication.

        Kalshi WebSocket requires a token obtained from the REST API.

        Returns:
            WebSocket authentication token

        Raises:
            AuthenticationError: If token retrieval fails
        """
        import httpx

        url = f"{self.base_url}/login"
        headers = self.get_auth_headers("POST", "/trade-api/v2/login")

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    url,
                    headers=headers,
                    timeout=30.0,
                )
                response.raise_for_status()
                data: dict[str, str] = response.json()
                token = data.get("token")
                if not token:
                    raise AuthenticationError("No token in login response")
                return str(token)
            except httpx.HTTPStatusError as e:
                logger.error(f"Failed to get WebSocket token: {e.response.status_code}")
                raise AuthenticationError(
                    f"Failed to get WebSocket token: {e.response.status_code}"
                ) from e


class AuthenticationError(Exception):
    """Raised when authentication fails."""

    pass
