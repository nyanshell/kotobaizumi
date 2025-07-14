"""Tests for database schema and sentence management with grammar features."""

import pytest

from app.database import SentenceManager, UserManager


class TestDatabaseSchema:
    """Test cases for database schema creation and validation."""

    def test_sentences_table_schema(self, db_connection):
        """Test that sentences table has correct schema including new fields."""
        # Get table schema
        result = db_connection.execute("DESCRIBE sentences").fetchall()
        columns = {row[0]: row[1] for row in result}
        
        # Verify all required columns exist
        required_columns = {
            'id': 'INTEGER',
            'user_id': 'INTEGER', 
            'hash': 'VARCHAR',
            'ja_text': 'VARCHAR',
            'en_text': 'VARCHAR',
            'cn_text': 'VARCHAR',
            'reading': 'VARCHAR',
            'explanation': 'VARCHAR',
            'rendered_text': 'VARCHAR',
            'grammar': 'VARCHAR',
            'created_at': 'TIMESTAMP',
            'last_reviewed': 'TIMESTAMP',
            'review_count': 'INTEGER',
            'ease_factor': 'DOUBLE',
            'interval_days': 'INTEGER',
            'next_review': 'TIMESTAMP',
            'last_played': 'TIMESTAMP',
            'play_count': 'INTEGER'
        }
        
        for col_name, col_type in required_columns.items():
            assert col_name in columns, f"Column {col_name} missing from sentences table"
            assert col_type in columns[col_name], f"Column {col_name} has wrong type: {columns[col_name]}"

    def test_save_sentence_with_grammar_fields(self, db_connection):
        """Test saving sentence with grammar and rendered_text fields."""
        # First create a user
        user_created = UserManager.create_user("testuser", "password123")
        assert user_created

        user = UserManager.authenticate_user("testuser", "password123")
        assert user is not None
        user_id = user["id"]

        # Test data
        hash_val = "test_hash_123"
        ja_text = "新学年を迎えるにあたって、計画を立てました。"
        en_text = "We made new plans when welcoming the new school year."
        cn_text = "迎接新学年时，我们制定了新计划。"
        reading = "しんがくねんをむかえるにあたって、けいかくをたてました。"
        explanation = "Grammar explanation here"
        rendered_text = "新学年を迎える{{にあたって}}、計画を立てました。"
        grammar = "にあたって"

        # Save sentence
        success = SentenceManager.save_sentence(
            user_id, hash_val, ja_text, en_text, cn_text, 
            reading, explanation, rendered_text, grammar
        )
        assert success

        # Verify sentence was saved with all fields
        sentence = SentenceManager.get_sentence_by_hash(user_id, hash_val)
        assert sentence is not None
        assert sentence["ja_text"] == ja_text
        assert sentence["rendered_text"] == rendered_text
        assert sentence["grammar"] == grammar

    def test_save_sentence_without_grammar(self, db_connection):
        """Test saving sentence without grammar pattern."""
        # First create a user
        user_created = UserManager.create_user("testuser2", "password123")
        assert user_created

        user = UserManager.authenticate_user("testuser2", "password123")
        assert user is not None
        user_id = user["id"]

        # Test data without grammar
        hash_val = "test_hash_456"
        ja_text = "普通の文章です。"
        en_text = "This is a normal sentence."
        cn_text = "这是一个普通的句子。"
        reading = "ふつうのぶんしょうです。"
        explanation = "No grammar explanation"
        rendered_text = "普通の文章です。"  # Same as ja_text
        grammar = None

        # Save sentence
        success = SentenceManager.save_sentence(
            user_id, hash_val, ja_text, en_text, cn_text,
            reading, explanation, rendered_text, grammar
        )
        assert success

        # Verify sentence was saved
        sentence = SentenceManager.get_sentence_by_hash(user_id, hash_val)
        assert sentence is not None
        assert sentence["ja_text"] == ja_text
        assert sentence["rendered_text"] == rendered_text
        assert sentence["grammar"] is None

    def test_get_sentences_includes_new_fields(self, db_connection):
        """Test that sentence retrieval includes rendered_text and grammar fields."""
        # First create a user
        user_created = UserManager.create_user("testuser3", "password123")
        assert user_created

        user = UserManager.authenticate_user("testuser3", "password123")
        assert user is not None
        user_id = user["id"]

        # Save a sentence with grammar
        hash_val = "test_hash_789"
        rendered_text = "テスト{{文章}}です。"
        grammar = "文章"
        
        SentenceManager.save_sentence(
            user_id, hash_val, "テスト文章です。", "Test sentence.", "测试句子。",
            "テストぶんしょうです。", "Test explanation", rendered_text, grammar
        )

        # Test different retrieval methods
        sentences = SentenceManager.get_sentences_for_review(user_id, limit=10)
        assert len(sentences) > 0
        sentence = sentences[0]
        assert "rendered_text" in sentence
        assert "grammar" in sentence
        assert sentence["rendered_text"] == rendered_text
        assert sentence["grammar"] == grammar

        # Test random sentences
        random_sentences = SentenceManager.get_random_sentences(user_id, limit=1)
        assert len(random_sentences) > 0
        sentence = random_sentences[0]
        assert "rendered_text" in sentence
        assert "grammar" in sentence

        # Test all sentences
        all_sentences = SentenceManager.get_all_sentences(user_id, limit=10)
        assert len(all_sentences) > 0
        sentence = all_sentences[0]
        assert "rendered_text" in sentence
        assert "grammar" in sentence