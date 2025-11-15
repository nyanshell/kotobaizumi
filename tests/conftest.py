"""Pytest configuration and fixtures for Kotobaizumi tests."""

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

# Set test environment before importing app modules
os.environ["DATA_FOLDER"] = tempfile.mkdtemp()
os.environ["LLM_PROVIDER"] = "openai"  # Use OpenAI for tests (existing mocks)
os.environ["TTS_PROVIDER"] = "azure"  # Use Azure for tests (existing mocks)
os.environ["OPENAI_API_KEY"] = "test-key"
os.environ["AZURE_SERVICE_TOKEN"] = "test-token"

from app.app import app as flask_app  # noqa: E402
from app.database import get_connection, init_database  # noqa: E402


@pytest.fixture
def app() -> Flask:
    """Create and configure a test Flask application."""
    flask_app.config.update(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret-key",
            "WTF_CSRF_ENABLED": False,
        }
    )

    # Initialize test database
    init_database()

    yield flask_app

    # Cleanup
    test_db_path = Path(os.environ["DATA_FOLDER"]) / "kotobaizumi.db"
    if test_db_path.exists():
        test_db_path.unlink()


@pytest.fixture
def client(app: Flask):
    """Create a test client for the Flask application."""
    return app.test_client()


@pytest.fixture
def db_connection():
    """Provide a database connection for testing."""
    conn = get_connection()
    yield conn
    conn.close()


@pytest.fixture
def mock_openai():
    """Mock OpenAI client for testing."""
    with patch("app.utils._openai_client") as mock_client:
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message = MagicMock()
        mock_response.choices[0].message.content = "Test translation response"
        mock_client.chat.completions.create.return_value = mock_response
        yield mock_client


@pytest.fixture
def mock_azure_speech():
    """Mock Azure Speech Services for testing."""
    with patch("app.utils.speechsdk") as mock_speechsdk:
        # Mock speech synthesis result
        mock_result = MagicMock()
        mock_result.reason = mock_speechsdk.ResultReason.SynthesizingAudioCompleted
        mock_result.audio_data = b"fake_audio_data"

        # Mock synthesizer
        mock_synthesizer = MagicMock()
        mock_synthesizer.speak_text_async.return_value.get.return_value = mock_result
        mock_synthesizer.speak_ssml_async.return_value.get.return_value = mock_result

        mock_speechsdk.SpeechSynthesizer.return_value = mock_synthesizer
        yield mock_speechsdk


@pytest.fixture
def sample_user_data() -> dict[str, str]:
    """Sample user data for testing."""
    return {"username": "testuser", "password": "testpassword123"}


@pytest.fixture
def sample_sentence_data() -> dict[str, str]:
    """Sample sentence data for testing."""
    return {
        "ja_text": "これはテストです。",
        "en_text": "This is a test.",
        "cn_text": "这是一个测试。",
        "reading": "これはテストです。",
        "explain": "Test explanation for grammar.",
        "hash": "test_hash_123",
    }


@pytest.fixture
def authenticated_user(client, sample_user_data: dict[str, str]):
    """Create and authenticate a test user."""
    from app.database import UserManager

    # Create user
    user_id = UserManager.create_user(
        sample_user_data["username"], sample_user_data["password"]
    )

    # Login
    client.post("/login", data=sample_user_data)

    return {"id": user_id, "username": sample_user_data["username"]}
