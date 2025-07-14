#!/usr/bin/env python3
"""CLI tool for managing users in Kotobaizumi application."""

import argparse
import getpass
import logging
import sys

from app.database import UserManager, get_connection
from app.utils import logger



def create_user(username, password=None):
    """Create a new user"""
    if not password:
        password = getpass.getpass("Enter password: ")
        confirm_password = getpass.getpass("Confirm password: ")
        if password != confirm_password:
            logger.error("Passwords don't match during user creation")
            print("❌ Passwords don't match!")
            return False

    try:
        user_id = UserManager.create_user(username, password)
        if user_id:
            logger.info("User '%s' created successfully with ID: %s", username, user_id)
            print(f"✅ User '{username}' created successfully with ID: {user_id}")
            return True
        else:
            logger.warning(
                "Failed to create user '%s' (username may already exist)", username
            )
            print(f"❌ Failed to create user '{username}' (username may already exist)")
            return False
    except Exception as e:
        logger.error("Error creating user '%s': %s", username, e)
        print(f"❌ Error creating user '{username}': {e}")
        return False


def list_users():
    """List all users"""
    conn = get_connection()
    users = conn.execute(
        "SELECT id, username, created_at FROM users ORDER BY id"
    ).fetchall()
    conn.close()

    if not users:
        print("No users found.")
        return

    print("\nUsers:")
    print("-" * 60)
    print(f"{'ID':<5} {'Username':<20} {'Created':<20}")
    print("-" * 60)
    for user in users:
        print(f"{user[0]:<5} {user[1]:<20} {user[2]:<20}")


def delete_user(username):
    """Delete a user and all their sentences"""
    conn = get_connection()

    # Get user info
    user = conn.execute(
        "SELECT id, username FROM users WHERE username = ?", [username]
    ).fetchone()
    if not user:
        print(f"❌ User '{username}' not found")
        conn.close()
        return False

    user_id, username = user[0], user[1]

    # Get sentence count
    sentence_count = conn.execute(
        "SELECT COUNT(*) FROM sentences WHERE user_id = ?", [user_id]
    ).fetchone()[0]

    # Confirm deletion
    print(f"⚠️  This will delete user '{username}' and {sentence_count} sentences.")
    confirm = input("Are you sure? (yes/no): ").lower().strip()

    if confirm != "yes":
        print("❌ Deletion cancelled")
        conn.close()
        return False

    try:
        # Delete review history first (foreign key constraint)
        conn.execute(
            "DELETE FROM review_history WHERE sentence_id IN (SELECT id FROM sentences WHERE user_id = ?)",
            [user_id],
        )

        # Delete sentences
        conn.execute("DELETE FROM sentences WHERE user_id = ?", [user_id])

        # Delete user
        conn.execute("DELETE FROM users WHERE id = ?", [user_id])

        conn.close()
        print(f"✅ User '{username}' and all associated data deleted successfully")
        return True

    except Exception as e:
        logger.error("Error deleting user '%s': %s", username, e)
        print(f"❌ Error deleting user: {e}")
        conn.close()
        return False


def change_password(username, new_password=None):
    """Change user password"""
    if not new_password:
        new_password = getpass.getpass("Enter new password: ")
        confirm_password = getpass.getpass("Confirm new password: ")
        if new_password != confirm_password:
            print("❌ Passwords don't match!")
            return False

    conn = get_connection()
    user = conn.execute(
        "SELECT id FROM users WHERE username = ?", [username]
    ).fetchone()

    if not user:
        print(f"❌ User '{username}' not found")
        conn.close()
        return False

    try:
        import bcrypt

        password_hash = bcrypt.hashpw(
            new_password.encode("utf-8"), bcrypt.gensalt()
        ).decode("utf-8")
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE username = ?",
            [password_hash, username],
        )
        conn.close()
        print(f"✅ Password changed for user '{username}'")
        return True

    except Exception as e:
        logger.error("Error changing password for user '%s': %s", username, e)
        print(f"❌ Error changing password: {e}")
        conn.close()
        return False


def show_user_stats(username):
    """Show user statistics"""
    conn = get_connection()

    user = conn.execute(
        "SELECT id, username, created_at FROM users WHERE username = ?", [username]
    ).fetchone()
    if not user:
        print(f"❌ User '{username}' not found")
        conn.close()
        return False

    user_id, username, created_at = user[0], user[1], user[2]

    # Get sentence statistics
    total_sentences = conn.execute(
        "SELECT COUNT(*) FROM sentences WHERE user_id = ?", [user_id]
    ).fetchone()[0]

    reviewed_sentences = conn.execute(
        "SELECT COUNT(*) FROM sentences WHERE user_id = ? AND review_count > 0",
        [user_id],
    ).fetchone()[0]

    # Get sentences due for review
    due_for_review = conn.execute(
        "SELECT COUNT(*) FROM sentences WHERE user_id = ? AND (next_review IS NULL OR next_review <= CURRENT_TIMESTAMP)",
        [user_id],
    ).fetchone()[0]

    # Get total reviews
    total_reviews = conn.execute(
        """SELECT COUNT(*) FROM review_history rh
           JOIN sentences s ON rh.sentence_id = s.id
           WHERE s.user_id = ?""",
        [user_id],
    ).fetchone()[0]

    # Get average ease factor
    avg_ease = conn.execute(
        "SELECT AVG(ease_factor) FROM sentences WHERE user_id = ? AND review_count > 0",
        [user_id],
    ).fetchone()[0]

    conn.close()

    print(f"\nUser Statistics for '{username}':")
    print("-" * 40)
    print(f"Created: {created_at}")
    print(f"Total sentences: {total_sentences}")
    print(f"Reviewed sentences: {reviewed_sentences}")
    print(f"Due for review: {due_for_review}")
    print(f"Total reviews: {total_reviews}")
    if avg_ease:
        print(f"Average ease factor: {avg_ease:.2f}")
    else:
        print("Average ease factor: N/A (no reviews yet)")


def reset_user_progress(username):
    """Reset all review progress for a user"""
    conn = get_connection()

    user = conn.execute(
        "SELECT id FROM users WHERE username = ?", [username]
    ).fetchone()
    if not user:
        print(f"❌ User '{username}' not found")
        conn.close()
        return False

    user_id = user[0]

    # Confirm reset
    print(f"⚠️  This will reset all review progress for user '{username}'.")
    confirm = input("Are you sure? (yes/no): ").lower().strip()

    if confirm != "yes":
        print("❌ Reset cancelled")
        conn.close()
        return False

    try:
        # Reset sentence progress
        conn.execute(
            """
            UPDATE sentences
            SET last_reviewed = NULL, review_count = 0, ease_factor = 2.5,
                interval_days = 1, next_review = CURRENT_TIMESTAMP + INTERVAL 1 DAY
            WHERE user_id = ?
        """,
            [user_id],
        )

        # Delete review history
        conn.execute(
            """
            DELETE FROM review_history
            WHERE sentence_id IN (SELECT id FROM sentences WHERE user_id = ?)
        """,
            [user_id],
        )

        conn.close()
        print(f"✅ Review progress reset for user '{username}'")
        return True

    except Exception as e:
        logger.error("Error resetting progress for user '%s': %s", username, e)
        print(f"❌ Error resetting progress: {e}")
        conn.close()
        return False


def main():
    parser = argparse.ArgumentParser(description="Kotobaizumi User Management CLI")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Create user
    create_parser = subparsers.add_parser("create", help="Create a new user")
    create_parser.add_argument("username", help="Username for the new user")
    create_parser.add_argument(
        "--password", help="Password (will prompt if not provided)"
    )

    # List users
    list_parser = subparsers.add_parser("list", help="List all users")

    # Delete user
    delete_parser = subparsers.add_parser(
        "delete", help="Delete a user and all their data"
    )
    delete_parser.add_argument("username", help="Username to delete")

    # Change password
    password_parser = subparsers.add_parser("password", help="Change user password")
    password_parser.add_argument("username", help="Username")
    password_parser.add_argument(
        "--new-password", help="New password (will prompt if not provided)"
    )

    # Show user stats
    stats_parser = subparsers.add_parser("stats", help="Show user statistics")
    stats_parser.add_argument("username", help="Username")

    # Reset progress
    reset_parser = subparsers.add_parser("reset", help="Reset user review progress")
    reset_parser.add_argument("username", help="Username")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    try:
        if args.command == "create":
            create_user(args.username, args.password)
        elif args.command == "list":
            list_users()
        elif args.command == "delete":
            delete_user(args.username)
        elif args.command == "password":
            change_password(args.username, args.new_password)
        elif args.command == "stats":
            show_user_stats(args.username)
        elif args.command == "reset":
            reset_user_progress(args.username)
    except KeyboardInterrupt:
        print("\n❌ Operation cancelled")
        sys.exit(1)
    except Exception as e:
        logger.error("CLI error: %s", e)
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
