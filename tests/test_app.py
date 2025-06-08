"""Tests for Flask application routes and functionality."""

import json
from unittest.mock import patch


class TestAuthenticationRoutes:
    """Test cases for authentication-related routes."""

    def test_login_page_get(self, client):
        """Test GET request to login page."""
        response = client.get("/login")

        assert response.status_code == 200
        assert b"Login" in response.data

    def test_login_post_valid_credentials(
        self, client, sample_user_data: dict[str, str]
    ):
        """Test POST to login with valid credentials."""
        from app.database import UserManager

        # Create user first
        UserManager.create_user(
            sample_user_data["username"], sample_user_data["password"]
        )

        response = client.post("/login", data=sample_user_data)

        assert response.status_code == 302  # Redirect after successful login
        assert response.location.endswith("/")

    def test_login_post_invalid_credentials(self, client):
        """Test POST to login with invalid credentials."""
        response = client.post(
            "/login", data={"username": "nonexistent", "password": "wrongpassword"}
        )

        assert response.status_code == 200  # Stay on login page
        assert b"Invalid username or password" in response.data

    def test_logout(self, client, authenticated_user):
        """Test user logout."""
        response = client.get("/logout")

        assert response.status_code == 302  # Redirect to login
        assert response.location.endswith("/login")

    def test_protected_route_requires_auth(self, client):
        """Test that protected routes require authentication."""
        response = client.get("/")

        assert response.status_code == 302  # Redirect to login
        assert "login" in response.location


class TestMainRoutes:
    """Test cases for main application routes."""

    def test_index_page_authenticated(self, client, authenticated_user):
        """Test index page for authenticated user."""
        response = client.get("/")

        assert response.status_code == 200
        assert "言葉の泉".encode() in response.data

    def test_index_with_sort_parameter(self, client, authenticated_user):
        """Test index page with sort parameter."""
        response = client.get("/?sort=random&count=2")

        assert response.status_code == 200

    def test_generate_page_get(self, client, authenticated_user):
        """Test GET request to generate page."""
        response = client.get("/generate")

        assert response.status_code == 200
        assert b"Generate New Sentence" in response.data

    @patch("app.utils.generate_sentence_content")
    def test_generate_page_post_valid(self, mock_generate, client, authenticated_user):
        """Test POST to generate page with valid text."""
        mock_generate.return_value = {
            "ja_text": "テスト文章",
            "en_text": "Test sentence",
            "cn_text": "测试句子",
            "reading": "テストぶんしょう",
            "explain": "Test explanation",
            "wav_data": [],
        }

        response = client.post("/generate", data={"text": "テスト{{文章}}"})

        assert response.status_code == 200
        assert b"Review and Confirm" in response.data

    def test_generate_page_post_empty_text(self, client, authenticated_user):
        """Test POST to generate page with empty text."""
        response = client.post("/generate", data={"text": ""})

        assert response.status_code == 302  # Redirect back to generate
        # Check for flash message in follow-up request
        response = client.get("/generate")
        assert b"Please enter some text" in response.data

    @patch("app.utils.generate_sentence_content")
    def test_generate_page_post_error(self, mock_generate, client, authenticated_user):
        """Test POST to generate page with generation error."""
        mock_generate.side_effect = Exception("Generation failed")

        response = client.post("/generate", data={"text": "テスト"})

        assert response.status_code == 302  # Redirect back to generate

    @patch("app.app.save_generated_sentence")
    def test_confirm_save_sentence(self, mock_save, client, authenticated_user):
        """Test confirming and saving a sentence."""
        mock_save.return_value = {"hash": "test_hash", "ja_text": "テスト"}

        with client.session_transaction() as sess:
            sess["pending_sentence"] = {
                "ja_text": "テスト",
                "en_text": "Test",
                "cn_text": "测试",
                "reading": "テスト",
                "explain": "Explanation",
                "wav_data": [],
            }

        response = client.post(
            "/confirm",
            data={
                "action": "save",
                "ja_text": "テスト修正",
                "en_text": "Modified test",
                "cn_text": "修改测试",
                "reading": "テストしゅうせい",
                "explain": "Modified explanation",
            },
        )

        assert response.status_code == 200  # Show saved sentence page
        assert b"Sentence Saved Successfully" in response.data  # Success message shown
        mock_save.assert_called_once()

    def test_confirm_cancel(self, client, authenticated_user):
        """Test canceling sentence confirmation."""
        with client.session_transaction() as sess:
            sess["pending_sentence"] = {"ja_text": "テスト"}

        response = client.post("/confirm", data={"action": "cancel"})

        assert response.status_code == 302  # Redirect to generate

    def test_confirm_no_pending_sentence(self, client, authenticated_user):
        """Test confirm with no pending sentence."""
        response = client.post("/confirm", data={"action": "save"})

        assert response.status_code == 302  # Redirect to generate

    @patch("app.database.SentenceManager.update_review")
    def test_review_sentence_success(self, mock_update, client, authenticated_user):
        """Test successful sentence review."""
        mock_update.return_value = True

        response = client.post("/review/1/4")

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["result"] == "success"

    @patch("app.database.SentenceManager.update_review")
    def test_review_sentence_failure(self, mock_update, client, authenticated_user):
        """Test failed sentence review."""
        mock_update.return_value = False

        response = client.post("/review/1/4")

        assert response.status_code == 400
        data = json.loads(response.data)
        assert data["result"] == "error"

    @patch("app.utils.remove_sentence")
    def test_delete_sentence_success(self, mock_remove, client, authenticated_user):
        """Test successful sentence deletion."""
        mock_remove.return_value = True

        response = client.delete("/delete/test_hash")

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["result"] == "done!"

    @patch("app.utils.remove_sentence")
    def test_delete_sentence_failure(self, mock_remove, client, authenticated_user):
        """Test failed sentence deletion."""
        mock_remove.return_value = False

        response = client.delete("/delete/test_hash")

        assert response.status_code == 400
        data = json.loads(response.data)
        assert data["result"] == "error"


class TestTemplateRendering:
    """Test cases for template rendering and context."""

    def test_base_template_context(self, client, authenticated_user):
        """Test base template includes correct context."""
        response = client.get("/")

        assert response.status_code == 200
        assert b"testuser" in response.data  # Username should be visible
        assert b"Logout" in response.data

    def test_index_empty_sentences(self, client, authenticated_user):
        """Test index page with no sentences."""
        response = client.get("/")

        assert response.status_code == 200
        assert b"No sentences available" in response.data

    @patch("app.utils.get_phrases")
    def test_index_with_sentences(self, mock_get_phrases, client, authenticated_user):
        """Test index page with sentences."""
        mock_get_phrases.return_value = [
            {
                "id": 1,
                "hash": "test_hash",
                "ja_text": "テスト文章",
                "en_text": "Test sentence",
                "cn_text": "测试句子",
                "reading": "テストぶんしょう",
                "explain": "Test explanation",
            }
        ]

        with patch("app.utils.encode_audio_string") as mock_audio:
            mock_audio.return_value = "data:audio/wav;base64,fake_data"

            response = client.get("/")

            assert response.status_code == 200
            assert "テスト文章".encode() in response.data
            assert b"Test sentence" in response.data


class TestErrorHandling:
    """Test cases for error handling and edge cases."""

    def test_nonexistent_route(self, client):
        """Test request to non-existent route."""
        response = client.get("/nonexistent")

        assert response.status_code == 404

    def test_method_not_allowed(self, client, authenticated_user):
        """Test method not allowed error."""
        response = client.post("/")  # GET only route

        assert response.status_code == 405

    def test_invalid_review_parameters(self, client, authenticated_user):
        """Test review route with invalid parameters."""
        response = client.post("/review/invalid/invalid")

        assert response.status_code == 404  # Flask converts invalid int to 404


class TestSessionManagement:
    """Test cases for session management."""

    def test_session_persistence(self, client, sample_user_data: dict[str, str]):
        """Test that user session persists across requests."""
        from app.database import UserManager

        # Create and login user
        UserManager.create_user(
            sample_user_data["username"], sample_user_data["password"]
        )
        client.post("/login", data=sample_user_data)

        # Make multiple requests
        response1 = client.get("/")
        response2 = client.get("/generate")

        assert response1.status_code == 200
        assert response2.status_code == 200

    def test_session_cleanup_on_logout(self, client, authenticated_user):
        """Test session cleanup on logout."""
        # Add something to session
        with client.session_transaction() as sess:
            sess["test_data"] = "should_be_cleared"

        # Logout
        client.get("/logout")

        # Try to access protected route
        response = client.get("/")
        assert response.status_code == 302  # Should redirect to login
