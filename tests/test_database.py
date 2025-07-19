"""Tests for database operations."""

import pytest

from app.database import SentenceManager, UserManager


class TestUserManager:
    """Test cases for UserManager class."""

    def test_create_user_success(self, db_connection):
        """Test successful user creation."""
        username = "newuser"
        password = "securepassword123"

        user_id = UserManager.create_user(username, password)

        assert user_id is not None
        assert isinstance(user_id, int)
        assert user_id > 0

    def test_create_user_duplicate_username(self, db_connection):
        """Test user creation with duplicate username fails."""
        username = "duplicateuser"
        password = "password123"

        # Create first user
        first_id = UserManager.create_user(username, password)
        assert first_id is not None

        # Try to create second user with same username
        second_id = UserManager.create_user(username, password)
        assert second_id is None

    def test_authenticate_user_valid_credentials(self, db_connection):
        """Test user authentication with valid credentials."""
        username = "authuser"
        password = "validpassword123"

        # Create user
        user_id = UserManager.create_user(username, password)
        assert user_id is not None

        # Authenticate
        user_data = UserManager.authenticate_user(username, password)

        assert user_data is not None
        assert user_data["id"] == user_id
        assert user_data["username"] == username

    def test_authenticate_user_invalid_password(self, db_connection):
        """Test user authentication with invalid password."""
        username = "authuser2"
        password = "correctpassword"
        wrong_password = "wrongpassword"

        # Create user
        UserManager.create_user(username, password)

        # Try to authenticate with wrong password
        user_data = UserManager.authenticate_user(username, wrong_password)

        assert user_data is None

    def test_authenticate_user_nonexistent(self, db_connection):
        """Test authentication for non-existent user."""
        user_data = UserManager.authenticate_user("nonexistent", "password")
        assert user_data is None

    def test_get_user_by_id_exists(self, db_connection):
        """Test getting user by ID when user exists."""
        username = "getuser"
        password = "password123"

        user_id = UserManager.create_user(username, password)
        user_data = UserManager.get_user_by_id(user_id)

        assert user_data is not None
        assert user_data["id"] == user_id
        assert user_data["username"] == username

    def test_get_user_by_id_not_exists(self, db_connection):
        """Test getting user by ID when user doesn't exist."""
        user_data = UserManager.get_user_by_id(99999)
        assert user_data is None


class TestSentenceManager:
    """Test cases for SentenceManager class."""

    @pytest.fixture
    def test_user(self, app) -> int:
        """Create a test user and return user ID."""
        return UserManager.create_user("testuser", "password123")

    def test_save_sentence_success(self, test_user: int):
        """Test successful sentence saving."""
        result = SentenceManager.save_sentence(
            user_id=test_user,
            hash_val="test_hash_1",
            ja_text="これはテストです。",
            en_text="This is a test.",
            cn_text="这是一个测试。",
            reading="これはテストです。",
            explanation="Test explanation.",
            rendered_text="これは{{テスト}}です。",
            grammar="テスト",
        )

        assert result is True

    def test_save_sentence_duplicate_hash(self, test_user: int):
        """Test saving sentence with duplicate hash fails."""
        hash_val = "duplicate_hash"

        # Save first sentence
        result1 = SentenceManager.save_sentence(
            user_id=test_user,
            hash_val=hash_val,
            ja_text="First sentence",
            en_text="First English",
            cn_text="First Chinese",
            reading="First reading",
            explanation="First explanation",
            rendered_text="First {{sentence}}",
            grammar="sentence",
        )
        assert result1 is True

        # Try to save second sentence with same hash
        result2 = SentenceManager.save_sentence(
            user_id=test_user,
            hash_val=hash_val,
            ja_text="Second sentence",
            en_text="Second English",
            cn_text="Second Chinese",
            reading="Second reading",
            explanation="Second explanation",
            rendered_text="Second {{sentence}}",
            grammar="sentence",
        )
        assert result2 is False

    def test_get_sentences_for_review(self, test_user: int):
        """Test getting sentences due for review."""
        # Save a sentence
        SentenceManager.save_sentence(
            user_id=test_user,
            hash_val="review_test_hash",
            ja_text="レビューテスト",
            en_text="Review test",
            cn_text="复习测试",
            reading="レビューテスト",
            explanation="Review explanation",
            rendered_text="レビュー{{テスト}}",
            grammar="テスト",
        )

        sentences = SentenceManager.get_sentences_for_review(test_user, limit=10)

        assert len(sentences) >= 1
        assert all("id" in s for s in sentences)
        assert all("ja_text" in s for s in sentences)

    def test_get_random_sentences(self, test_user: int):
        """Test getting random sentences."""
        # Save multiple sentences
        for i in range(3):
            SentenceManager.save_sentence(
                user_id=test_user,
                hash_val=f"random_hash_{i}",
                ja_text=f"ランダムテスト{i}",
                en_text=f"Random test {i}",
                cn_text=f"随机测试{i}",
                reading=f"ランダムテスト{i}",
                explanation=f"Random explanation {i}",
                rendered_text=f"ランダム{{テスト}}{i}",
                grammar="テスト",
            )

        sentences = SentenceManager.get_random_sentences(test_user, limit=2)

        assert len(sentences) <= 2
        assert all("id" in s for s in sentences)

    def test_delete_sentence_success(self, test_user: int):
        """Test successful sentence deletion."""
        hash_val = "delete_test_hash"

        # Save sentence
        SentenceManager.save_sentence(
            user_id=test_user,
            hash_val=hash_val,
            ja_text="削除テスト",
            en_text="Delete test",
            cn_text="删除测试",
            reading="削除テスト",
            explanation="Delete explanation",
            rendered_text="削除{{テスト}}",
            grammar="テスト",
        )

        # Delete sentence
        result = SentenceManager.delete_sentence(test_user, hash_val)
        assert result is True

        # Verify deletion
        sentence = SentenceManager.get_sentence_by_hash(test_user, hash_val)
        assert sentence is None

    def test_delete_sentence_nonexistent(self, test_user: int):
        """Test deletion of non-existent sentence."""
        result = SentenceManager.delete_sentence(test_user, "nonexistent_hash")
        assert result is True  # DuckDB DELETE succeeds even if no rows affected

    def test_get_sentence_by_hash_exists(self, test_user: int):
        """Test getting sentence by hash when it exists."""
        hash_val = "get_by_hash_test"

        SentenceManager.save_sentence(
            user_id=test_user,
            hash_val=hash_val,
            ja_text="ハッシュテスト",
            en_text="Hash test",
            cn_text="哈希测试",
            reading="ハッシュテスト",
            explanation="Hash explanation",
            rendered_text="ハッシュ{{テスト}}",
            grammar="テスト",
        )

        sentence = SentenceManager.get_sentence_by_hash(test_user, hash_val)

        assert sentence is not None
        assert sentence["hash"] == hash_val
        assert sentence["ja_text"] == "ハッシュテスト"

    def test_get_sentence_by_hash_not_exists(self, test_user: int):
        """Test getting sentence by hash when it doesn't exist."""
        sentence = SentenceManager.get_sentence_by_hash(test_user, "nonexistent")
        assert sentence is None

    def test_user_isolation(self, app):
        """Test that users can only access their own sentences."""
        # Create two users
        user1 = UserManager.create_user("user1", "password1")
        user2 = UserManager.create_user("user2", "password2")

        # User1 saves a sentence
        SentenceManager.save_sentence(
            user_id=user1,
            hash_val="isolation_test",
            ja_text="分離テスト",
            en_text="Isolation test",
            cn_text="隔离测试",
            reading="分離テスト",
            explanation="Isolation explanation",
            rendered_text="分離{{テスト}}",
            grammar="テスト",
        )

        # User2 should not see user1's sentence
        sentence = SentenceManager.get_sentence_by_hash(user2, "isolation_test")
        assert sentence is None

        # User1 should see their own sentence
        sentence = SentenceManager.get_sentence_by_hash(user1, "isolation_test")
        assert sentence is not None
