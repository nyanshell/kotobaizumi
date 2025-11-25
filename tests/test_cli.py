"""Tests for CLI user management functionality."""

from io import StringIO
from unittest.mock import patch

from app.cli import (
    change_password,
    create_user,
    delete_user,
    list_users,
    reset_user_progress,
    show_user_stats,
)


class TestCreateUser:
    """Test cases for create_user function."""

    @patch("app.cli.getpass.getpass")
    @patch("app.cli.UserManager.create_user")
    def test_create_user_success_with_password_prompt(self, mock_create, mock_getpass):
        """Test successful user creation with password prompt."""
        mock_getpass.side_effect = ["password123", "password123"]  # Confirm match
        mock_create.return_value = 1

        result = create_user("testuser")

        assert result is True
        mock_create.assert_called_once_with("testuser", "password123")

    @patch("app.cli.getpass.getpass")
    def test_create_user_password_mismatch(self, mock_getpass):
        """Test user creation with password mismatch."""
        mock_getpass.side_effect = ["password123", "different456"]

        result = create_user("testuser")

        assert result is False

    @patch("app.cli.UserManager.create_user")
    def test_create_user_success_with_provided_password(self, mock_create):
        """Test successful user creation with provided password."""
        mock_create.return_value = 1

        result = create_user("testuser", "password123")

        assert result is True
        mock_create.assert_called_once_with("testuser", "password123")

    @patch("app.cli.UserManager.create_user")
    def test_create_user_failure(self, mock_create):
        """Test user creation failure."""
        mock_create.return_value = None

        result = create_user("testuser", "password123")

        assert result is False

    @patch("app.cli.UserManager.create_user")
    def test_create_user_exception(self, mock_create):
        """Test user creation with exception."""
        mock_create.side_effect = Exception("Database error")

        result = create_user("testuser", "password123")

        assert result is False


class TestListUsers:
    """Test cases for list_users function."""

    @patch("app.cli.get_connection")
    def test_list_users_empty(self, mock_get_connection):
        """Test listing users when none exist."""
        mock_conn = mock_get_connection.return_value
        mock_conn.execute.return_value.fetchall.return_value = []

        with patch("sys.stdout", new=StringIO()) as fake_out:
            list_users()
            output = fake_out.getvalue()

        assert "No users found" in output

    @patch("app.cli.get_connection")
    def test_list_users_with_data(self, mock_get_connection):
        """Test listing users with existing data."""
        mock_conn = mock_get_connection.return_value
        mock_conn.execute.return_value.fetchall.return_value = [
            (1, "user1", "2023-01-01 10:00:00"),
            (2, "user2", "2023-01-02 11:00:00"),
        ]

        with patch("sys.stdout", new=StringIO()) as fake_out:
            list_users()
            output = fake_out.getvalue()

        assert "user1" in output
        assert "user2" in output
        assert "ID" in output  # Header


class TestDeleteUser:
    """Test cases for delete_user function."""

    @patch("app.cli.get_connection")
    @patch("builtins.input")
    def test_delete_user_success(self, mock_input, mock_get_connection):
        """Test successful user deletion."""
        mock_input.return_value = "yes"
        mock_conn = mock_get_connection.return_value

        # Mock user exists
        mock_conn.execute.side_effect = [
            # Get user info
            type("MockResult", (), {"fetchone": lambda self: (1, "testuser")})(),
            # Get sentence count
            type("MockResult", (), {"fetchone": lambda self: (5,)})(),
            # Delete operations (3 calls)
            None,
            None,
            None,
        ]

        result = delete_user("testuser")

        assert result is True

    @patch("app.cli.get_connection")
    def test_delete_user_not_found(self, mock_get_connection):
        """Test deleting non-existent user."""
        mock_conn = mock_get_connection.return_value
        mock_conn.execute.return_value.fetchone.return_value = None

        result = delete_user("nonexistent")

        assert result is False

    @patch("app.cli.get_connection")
    @patch("builtins.input")
    def test_delete_user_cancelled(self, mock_input, mock_get_connection):
        """Test user deletion cancellation."""
        mock_input.return_value = "no"
        mock_conn = mock_get_connection.return_value
        mock_conn.execute.side_effect = [
            type("MockResult", (), {"fetchone": lambda self: (1, "testuser")})(),
            type("MockResult", (), {"fetchone": lambda self: (0,)})(),
        ]

        result = delete_user("testuser")

        assert result is False

    @patch("app.cli.get_connection")
    @patch("builtins.input")
    def test_delete_user_exception(self, mock_input, mock_get_connection):
        """Test user deletion with exception."""
        mock_input.return_value = "yes"
        mock_conn = mock_get_connection.return_value
        mock_conn.execute.side_effect = [
            type("MockResult", (), {"fetchone": lambda self: (1, "testuser")})(),
            type("MockResult", (), {"fetchone": lambda self: (0,)})(),
            Exception("Database error"),
        ]

        result = delete_user("testuser")

        assert result is False


class TestChangePassword:
    """Test cases for change_password function."""

    @patch("app.cli.getpass.getpass")
    @patch("app.cli.get_connection")
    def test_change_password_success(self, mock_get_connection, mock_getpass):
        """Test successful password change."""
        mock_getpass.side_effect = ["newpass123", "newpass123"]
        mock_conn = mock_get_connection.return_value
        mock_conn.execute.return_value.fetchone.return_value = (1,)

        result = change_password("testuser")

        assert result is True

    @patch("app.cli.getpass.getpass")
    def test_change_password_mismatch(self, mock_getpass):
        """Test password change with mismatch."""
        mock_getpass.side_effect = ["newpass123", "different456"]

        result = change_password("testuser")

        assert result is False

    @patch("app.cli.get_connection")
    def test_change_password_user_not_found(self, mock_get_connection):
        """Test password change for non-existent user."""
        mock_conn = mock_get_connection.return_value
        mock_conn.execute.return_value.fetchone.return_value = None

        result = change_password("nonexistent", "newpass123")

        assert result is False

    @patch("app.cli.get_connection")
    def test_change_password_with_provided_password(self, mock_get_connection):
        """Test password change with provided password."""
        mock_conn = mock_get_connection.return_value
        mock_conn.execute.return_value.fetchone.return_value = (1,)

        result = change_password("testuser", "newpass123")

        assert result is True


class TestShowUserStats:
    """Test cases for show_user_stats function."""

    @patch("app.cli.get_connection")
    def test_show_user_stats_success(self, mock_get_connection):
        """Test showing user statistics."""
        mock_conn = mock_get_connection.return_value
        mock_conn.execute.side_effect = [
            # Get user info
            # Get user info
            type(
                "MockResult",
                (),
                {"fetchone": lambda self: (1, "testuser", "2023-01-01 10:00:00")},
            )(),
            # Total sentences
            type("MockResult", (), {"fetchone": lambda self: (10,)})(),
            # Reviewed sentences
            type("MockResult", (), {"fetchone": lambda self: (7,)})(),
            # Due for review
            type("MockResult", (), {"fetchone": lambda self: (3,)})(),
            # Total reviews
            type("MockResult", (), {"fetchone": lambda self: (25,)})(),
            # Average ease
            type("MockResult", (), {"fetchone": lambda self: (2.8,)})(),
        ]

        with patch("sys.stdout", new=StringIO()) as fake_out:
            result = show_user_stats("testuser")
            output = fake_out.getvalue()

        assert result is not False  # Function doesn't return False on success
        assert "testuser" in output
        assert "Total sentences: 10" in output
        assert "Average ease factor: 2.80" in output

    @patch("app.cli.get_connection")
    def test_show_user_stats_user_not_found(self, mock_get_connection):
        """Test showing stats for non-existent user."""
        mock_conn = mock_get_connection.return_value
        mock_conn.execute.return_value.fetchone.return_value = None

        result = show_user_stats("nonexistent")

        assert result is False

    @patch("app.cli.get_connection")
    def test_show_user_stats_no_reviews(self, mock_get_connection):
        """Test showing stats for user with no reviews."""
        mock_conn = mock_get_connection.return_value
        mock_conn.execute.side_effect = [
            # User info and other stats...
            # User info and other stats...
            type(
                "MockResult",
                (),
                {"fetchone": lambda self: (1, "testuser", "2023-01-01 10:00:00")},
            )(),
            type("MockResult", (), {"fetchone": lambda self: (5,)})(),
            type("MockResult", (), {"fetchone": lambda self: (0,)})(),
            type("MockResult", (), {"fetchone": lambda self: (5,)})(),
            type("MockResult", (), {"fetchone": lambda self: (0,)})(),
            # No average ease (None)
            type("MockResult", (), {"fetchone": lambda self: (None,)})(),
        ]

        with patch("sys.stdout", new=StringIO()) as fake_out:
            show_user_stats("testuser")
            output = fake_out.getvalue()

        assert "Average ease factor: N/A" in output


class TestResetUserProgress:
    """Test cases for reset_user_progress function."""

    @patch("app.cli.get_connection")
    @patch("builtins.input")
    def test_reset_user_progress_success(self, mock_input, mock_get_connection):
        """Test successful user progress reset."""
        mock_input.return_value = "yes"
        mock_conn = mock_get_connection.return_value
        mock_conn.execute.side_effect = [
            # Get user
            type("MockResult", (), {"fetchone": lambda self: (1,)})(),
            # Update and delete operations
            None,
            None,
        ]

        result = reset_user_progress("testuser")

        assert result is True

    @patch("app.cli.get_connection")
    def test_reset_user_progress_user_not_found(self, mock_get_connection):
        """Test reset for non-existent user."""
        mock_conn = mock_get_connection.return_value
        mock_conn.execute.return_value.fetchone.return_value = None

        result = reset_user_progress("nonexistent")

        assert result is False

    @patch("app.cli.get_connection")
    @patch("builtins.input")
    def test_reset_user_progress_cancelled(self, mock_input, mock_get_connection):
        """Test user progress reset cancellation."""
        mock_input.return_value = "no"
        mock_conn = mock_get_connection.return_value
        mock_conn.execute.return_value.fetchone.return_value = (1,)

        result = reset_user_progress("testuser")

        assert result is False

    @patch("app.cli.get_connection")
    @patch("builtins.input")
    def test_reset_user_progress_exception(self, mock_input, mock_get_connection):
        """Test user progress reset with exception."""
        mock_input.return_value = "yes"
        mock_conn = mock_get_connection.return_value
        mock_conn.execute.side_effect = [
            type("MockResult", (), {"fetchone": lambda self: (1,)})(),
            Exception("Database error"),
        ]

        result = reset_user_progress("testuser")

        assert result is False


class TestCLIMain:
    """Test cases for CLI main function and argument parsing."""

    @patch("app.cli.create_user")
    @patch("sys.argv", ["cli.py", "create", "testuser"])
    def test_main_create_command(self, mock_create_user):
        """Test main function with create command."""
        from app.cli import main

        mock_create_user.return_value = True

        # Should not raise exception
        main()

        mock_create_user.assert_called_once_with("testuser", None)

    @patch("app.cli.list_users")
    @patch("sys.argv", ["cli.py", "list"])
    def test_main_list_command(self, mock_list_users):
        """Test main function with list command."""
        from app.cli import main

        main()

        mock_list_users.assert_called_once()

    @patch("sys.argv", ["cli.py"])
    def test_main_no_command(self):
        """Test main function with no command shows help."""
        from app.cli import main

        with patch("sys.stdout", new=StringIO()):
            # Should not raise exception, just show help
            main()

    @patch("app.cli.create_user")
    @patch("sys.argv", ["cli.py", "create", "testuser", "--password", "secret123"])
    def test_main_create_with_password(self, mock_create_user):
        """Test main function with create command and password."""
        from app.cli import main

        mock_create_user.return_value = True

        main()

        mock_create_user.assert_called_once_with("testuser", "secret123")

    @patch("app.cli.change_password")
    @patch("sys.argv", ["cli.py", "password", "testuser", "--new-password", "new123"])
    def test_main_password_command(self, mock_change_password):
        """Test main function with password command."""
        from app.cli import main

        mock_change_password.return_value = True

        main()

        mock_change_password.assert_called_once_with("testuser", "new123")

    @patch("sys.stderr", new_callable=StringIO)
    @patch("sys.exit")
    def test_main_keyboard_interrupt(self, mock_exit, mock_stderr):
        """Test main function handles KeyboardInterrupt."""
        from app.cli import main

        with patch("app.cli.create_user") as mock_create:
            mock_create.side_effect = KeyboardInterrupt()

            with patch("sys.argv", ["cli.py", "create", "testuser"]):
                main()

            mock_exit.assert_called_once_with(1)
