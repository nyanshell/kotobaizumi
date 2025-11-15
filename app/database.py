import os
from pathlib import Path

import bcrypt
import duckdb

from .settings import logger

# Default to ./data directory relative to the project root
DEFAULT_DATA_FOLDER = Path(__file__).parent.parent / "data"
DATA_FOLDER = Path(os.getenv("DATA_FOLDER", DEFAULT_DATA_FOLDER))
DB_PATH = DATA_FOLDER / "kotobaizumi.db"


def get_connection() -> duckdb.DuckDBPyConnection:
    """Get a connection to the DuckDB database."""
    # Ensure data directory exists
    DATA_FOLDER.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(DB_PATH))


def init_database() -> None:
    """Initialize the database with required tables and sequences."""
    conn = get_connection()

    # Users table
    conn.execute("""
        CREATE SEQUENCE IF NOT EXISTS users_id_seq;
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY DEFAULT nextval('users_id_seq'),
            username VARCHAR UNIQUE NOT NULL,
            password_hash VARCHAR NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # Create sentence table
    conn.execute("""
        CREATE SEQUENCE IF NOT EXISTS sentences_id_seq;
        CREATE TABLE IF NOT EXISTS sentences (
            id INTEGER PRIMARY KEY DEFAULT nextval('sentences_id_seq'),
            user_id INTEGER NOT NULL,
            hash VARCHAR UNIQUE NOT NULL,
            ja_text VARCHAR NOT NULL,
            en_text VARCHAR NOT NULL,
            cn_text VARCHAR NOT NULL,
            reading VARCHAR NOT NULL,
            explanation VARCHAR NOT NULL,
            rendered_text VARCHAR,
            grammar VARCHAR,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_reviewed TIMESTAMP,
            review_count INTEGER DEFAULT 0,
            ease_factor DOUBLE DEFAULT 2.5,
            interval_days INTEGER DEFAULT 1,
            next_review TIMESTAMP,
            last_played TIMESTAMP,
            play_count INTEGER DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
    """)

    # Review history for analytics
    conn.execute("""
        CREATE SEQUENCE IF NOT EXISTS review_history_id_seq;
        CREATE TABLE IF NOT EXISTS review_history (
            id INTEGER PRIMARY KEY DEFAULT nextval('review_history_id_seq'),
            sentence_id INTEGER NOT NULL,
            reviewed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            quality INTEGER NOT NULL,
            FOREIGN KEY (sentence_id) REFERENCES sentences(id)
        );
    """)

    # Grammar audio play tracking
    conn.execute("""
        CREATE SEQUENCE IF NOT EXISTS grammar_plays_id_seq;
        CREATE TABLE IF NOT EXISTS grammar_plays (
            id INTEGER PRIMARY KEY DEFAULT nextval('grammar_plays_id_seq'),
            sentence_id INTEGER NOT NULL,
            voice_name VARCHAR NOT NULL,
            play_count INTEGER DEFAULT 1,
            last_played TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (sentence_id) REFERENCES sentences(id),
            UNIQUE(sentence_id, voice_name)
        );
    """)

    conn.close()


class UserManager:
    """Manages user-related database operations."""

    @staticmethod
    def create_user(username: str, password: str) -> int | None:
        """Create a new user with hashed password."""
        conn = get_connection()
        try:
            password_hash = bcrypt.hashpw(
                password.encode("utf-8"), bcrypt.gensalt()
            ).decode("utf-8")
            result = conn.execute(
                "INSERT INTO users (username, password_hash) VALUES (?, ?) RETURNING id",
                [username, password_hash],
            ).fetchone()
            conn.close()
            return result[0] if result else None
        except Exception:
            conn.close()
            return None

    @staticmethod
    def authenticate_user(username: str, password: str) -> dict[str, str | int] | None:
        """Authenticate user with username and password."""
        conn = get_connection()
        user = conn.execute(
            "SELECT id, username, password_hash FROM users WHERE username = ?",
            [username],
        ).fetchone()
        conn.close()

        if user and bcrypt.checkpw(password.encode("utf-8"), user[2].encode("utf-8")):
            return {"id": user[0], "username": user[1]}
        return None

    @staticmethod
    def get_user_by_id(user_id: int) -> dict[str, str | int] | None:
        """Get user information by ID."""
        conn = get_connection()
        user = conn.execute(
            "SELECT id, username FROM users WHERE id = ?", [user_id]
        ).fetchone()
        conn.close()

        if user:
            return {"id": user[0], "username": user[1]}
        return None


class SentenceManager:
    """Manages sentence-related database operations."""

    @staticmethod
    def save_sentence(
        user_id: int,
        hash_val: str,
        ja_text: str,
        en_text: str,
        cn_text: str,
        reading: str,
        explanation: str,
        rendered_text: str,
        grammar: str,
    ) -> bool:
        """Save a new sentence for a user."""
        conn = get_connection()
        try:
            # Calculate initial next review (1 day from now)
            conn.execute(
                """
                INSERT INTO sentences
                (user_id, hash, ja_text, en_text, cn_text, reading, explanation, next_review, rendered_text, grammar)
                VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP + INTERVAL 1 DAY, ?, ?)
            """,
                [
                    user_id,
                    hash_val,
                    ja_text,
                    en_text,
                    cn_text,
                    reading,
                    explanation,
                    rendered_text,
                    grammar,
                ],
            )

            conn.close()
            return True
        except Exception:
            conn.close()
            return False

    @staticmethod
    def get_sentences_for_review(
        user_id: int, limit: int = 10, offset: int = 0
    ) -> list[dict[str, str | int | float]]:
        """Get sentences due for review for a user. If no sentences are due, return all sentences."""
        conn = get_connection()

        # First try to get sentences due for review
        sentences = conn.execute(
            """
            SELECT id, hash, ja_text, en_text, cn_text, reading, explanation,
                   review_count, ease_factor, interval_days, next_review, last_played, play_count, rendered_text, grammar
            FROM sentences
            WHERE user_id = ? AND (next_review IS NULL OR next_review <= CURRENT_TIMESTAMP)
            ORDER BY next_review ASC, created_at ASC
            LIMIT ? OFFSET ?
        """,
            [user_id, limit, offset],
        ).fetchall()

        # If no sentences are due for review, get all sentences
        if not sentences:
            sentences = conn.execute(
                """
                SELECT id, hash, ja_text, en_text, cn_text, reading, explanation,
                       review_count, ease_factor, interval_days, next_review, last_played, play_count, rendered_text, grammar
                FROM sentences
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
            """,
                [user_id, limit, offset],
            ).fetchall()

        conn.close()

        return [
            {
                "id": s[0],
                "hash": s[1],
                "ja_text": s[2],
                "en_text": s[3],
                "cn_text": s[4],
                "reading": s[5],
                "explanation": s[6],
                "review_count": s[7],
                "ease_factor": s[8],
                "interval_days": s[9],
                "next_review": s[10],
                "last_played": s[11],
                "play_count": s[12],
                "rendered_text": s[13],
                "grammar": s[14],
            }
            for s in sentences
        ]

    @staticmethod
    def get_random_sentences(
        user_id: int, limit: int = 1, offset: int = 0
    ) -> list[dict[str, str | int]]:
        conn = get_connection()

        sentences = conn.execute(
            """
            SELECT id, hash, ja_text, en_text, cn_text, reading, explanation, last_played, play_count, rendered_text, grammar
            FROM sentences
            WHERE user_id = ?
            ORDER BY RANDOM()
            LIMIT ? OFFSET ?
        """,
            [user_id, limit, offset],
        ).fetchall()

        conn.close()

        return [
            {
                "id": s[0],
                "hash": s[1],
                "ja_text": s[2],
                "en_text": s[3],
                "cn_text": s[4],
                "reading": s[5],
                "explanation": s[6],
                "last_played": s[7],
                "play_count": s[8],
                "rendered_text": s[9],
                "grammar": s[10],
            }
            for s in sentences
        ]

    @staticmethod
    def get_all_sentences(
        user_id: int, limit: int = 50, offset: int = 0
    ) -> list[dict[str, str | int]]:
        """Get all sentences for a user ordered by creation date."""
        conn = get_connection()

        sentences = conn.execute(
            """
            SELECT id, hash, ja_text, en_text, cn_text, reading, explanation, last_played, play_count, rendered_text, grammar
            FROM sentences
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """,
            [user_id, limit, offset],
        ).fetchall()

        conn.close()

        return [
            {
                "id": s[0],
                "hash": s[1],
                "ja_text": s[2],
                "en_text": s[3],
                "cn_text": s[4],
                "reading": s[5],
                "explanation": s[6],
                "last_played": s[7],
                "play_count": s[8],
                "rendered_text": s[9],
                "grammar": s[10],
            }
            for s in sentences
        ]

    @staticmethod
    def delete_sentence(user_id: int, sentence_hash: str) -> bool:
        conn = get_connection()
        try:
            conn.execute(
                "DELETE FROM sentences WHERE user_id = ? AND hash = ?",
                [user_id, sentence_hash],
            )
            conn.close()
            return True
        except Exception:
            conn.close()
            return False

    @staticmethod
    def get_sentence_by_hash(
        user_id: int, sentence_hash: str
    ) -> dict[str, str | int] | None:
        conn = get_connection()
        sentence = conn.execute(
            """
            SELECT id, hash, ja_text, en_text, cn_text, reading, explanation, last_played, play_count, rendered_text, grammar
            FROM sentences
            WHERE user_id = ? AND hash = ?
        """,
            [user_id, sentence_hash],
        ).fetchone()

        conn.close()

        if sentence:
            return {
                "id": sentence[0],
                "hash": sentence[1],
                "ja_text": sentence[2],
                "en_text": sentence[3],
                "cn_text": sentence[4],
                "reading": sentence[5],
                "explanation": sentence[6],
                "last_played": sentence[7],
                "play_count": sentence[8],
                "rendered_text": sentence[9],
                "grammar": sentence[10],
            }
        return None

    @staticmethod
    def track_audio_play(sentence_id: int, voice_name: str) -> bool:
        """Track when a grammar audio is played"""
        conn = get_connection()
        try:
            # Use INSERT OR REPLACE to update play count and last played time
            conn.execute(
                """
                INSERT INTO grammar_plays (sentence_id, voice_name, play_count, last_played)
                VALUES (?, ?, 1, CURRENT_TIMESTAMP)
                ON CONFLICT (sentence_id, voice_name)
                DO UPDATE SET
                    play_count = play_count + 1,
                    last_played = CURRENT_TIMESTAMP
            """,
                [sentence_id, voice_name],
            )
            conn.close()
            return True
        except Exception as e:
            logger.error(f"Error tracking audio play: {e}")
            conn.close()
            return False

    @staticmethod
    def get_grammar_play_stats(sentence_id: int) -> dict[str, dict]:
        """Get play statistics for a sentence"""
        conn = get_connection()
        stats = conn.execute(
            """
            SELECT voice_name, play_count, last_played
            FROM grammar_plays
            WHERE sentence_id = ?
        """,
            [sentence_id],
        ).fetchall()
        conn.close()

        return {
            stat[0]: {"play_count": stat[1], "last_played": stat[2]} for stat in stats
        }

    @staticmethod
    def track_sentence_play(sentence_id: int) -> bool:
        """Track when any audio from a sentence is played"""
        conn = get_connection()
        try:
            conn.execute(
                """
                UPDATE sentences
                SET play_count = COALESCE(play_count, 0) + 1,
                    last_played = CURRENT_TIMESTAMP
                WHERE id = ?
            """,
                [sentence_id],
            )
            conn.close()
            return True
        except Exception as e:
            logger.error(f"Error tracking sentence play: {e}")
            conn.close()
            return False


# Initialize database on import
init_database()
