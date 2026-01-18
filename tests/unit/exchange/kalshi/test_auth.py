"""Tests for Kalshi authentication."""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from market_maker.exchange.kalshi.auth import (
    KALSHI_API_BASE,
    KALSHI_DEMO_API_BASE,
    AuthenticationError,
    KalshiAuth,
    KalshiCredentials,
)


def generate_test_key() -> tuple[str, rsa.RSAPrivateKey]:
    """Generate a test RSA key pair and return path to PEM file."""
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )

    # Write to temp file
    with tempfile.NamedTemporaryFile(mode="wb", suffix=".pem", delete=False) as f:
        f.write(pem)
        return f.name, private_key


class TestKalshiCredentials:
    """Tests for KalshiCredentials."""

    def test_production_base_url(self) -> None:
        """Production credentials should use production URL."""
        key_path, _ = generate_test_key()
        try:
            creds = KalshiCredentials(
                api_key="test_key",
                private_key_path=key_path,
                demo=False,
            )
            assert creds.base_url == KALSHI_API_BASE
        finally:
            Path(key_path).unlink()

    def test_demo_base_url(self) -> None:
        """Demo credentials should use demo URL."""
        key_path, _ = generate_test_key()
        try:
            creds = KalshiCredentials(
                api_key="test_key",
                private_key_path=key_path,
                demo=True,
            )
            assert creds.base_url == KALSHI_DEMO_API_BASE
        finally:
            Path(key_path).unlink()


class TestKalshiAuth:
    """Tests for KalshiAuth."""

    @pytest.fixture
    def key_path(self) -> str:
        """Create a test key file."""
        path, _ = generate_test_key()
        yield path
        Path(path).unlink()

    @pytest.fixture
    def credentials(self, key_path: str) -> KalshiCredentials:
        """Create test credentials."""
        return KalshiCredentials(
            api_key="test_api_key",
            private_key_path=key_path,
            demo=True,
        )

    @pytest.fixture
    def auth(self, credentials: KalshiCredentials) -> KalshiAuth:
        """Create auth manager with test credentials."""
        return KalshiAuth(credentials)

    def test_initial_state(self, auth: KalshiAuth) -> None:
        """Auth should be authenticated after loading key."""
        assert auth.is_authenticated()
        assert auth.api_key == "test_api_key"

    def test_is_demo(self, auth: KalshiAuth) -> None:
        """Should report demo mode correctly."""
        assert auth.is_demo is True

    def test_base_url(self, auth: KalshiAuth) -> None:
        """Should use correct base URL."""
        assert auth.base_url == KALSHI_DEMO_API_BASE

    def test_sign_request(self, auth: KalshiAuth) -> None:
        """Should sign requests correctly."""
        signature, timestamp = auth.sign_request("GET", "/trade-api/v2/markets")
        assert signature  # Non-empty signature
        assert timestamp > 0

    def test_get_auth_headers(self, auth: KalshiAuth) -> None:
        """Should return auth headers."""
        headers = auth.get_auth_headers("GET", "/trade-api/v2/markets")
        assert "KALSHI-ACCESS-KEY" in headers
        assert "KALSHI-ACCESS-SIGNATURE" in headers
        assert "KALSHI-ACCESS-TIMESTAMP" in headers
        assert headers["KALSHI-ACCESS-KEY"] == "test_api_key"

    @pytest.mark.asyncio
    async def test_ensure_authenticated(self, auth: KalshiAuth) -> None:
        """Should return API key when authenticated."""
        api_key = await auth.ensure_authenticated()
        assert api_key == "test_api_key"

    @pytest.mark.asyncio
    async def test_get_websocket_token_success(self, auth: KalshiAuth) -> None:
        """Should get WebSocket token successfully."""
        mock_response = AsyncMock()
        mock_response.json = lambda: {"token": "ws_token_123"}
        mock_response.raise_for_status = lambda: None

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.post = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            token = await auth.get_websocket_token()
            assert token == "ws_token_123"

    def test_missing_key_file(self) -> None:
        """Should raise error for missing key file."""
        creds = KalshiCredentials(
            api_key="test_key",
            private_key_path="/nonexistent/path.pem",
            demo=True,
        )
        with pytest.raises(FileNotFoundError):
            KalshiAuth(creds)
