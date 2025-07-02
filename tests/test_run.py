"""Tests for run.py."""

import os
import sys
import tempfile
from unittest.mock import MagicMock, patch

# Add the root directory to the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import run  # noqa: E402


class TestRunModule:
    """Test cases for the run module."""

    def test_check_env_file_exists(self):
        """Test check_env_file when .env file exists."""
        with patch("os.path.exists", return_value=True):
            result = run.check_env_file()
            assert result is True

    def test_check_env_file_creates_template(self):
        """Test check_env_file creates template when .env doesn't exist."""
        with tempfile.TemporaryDirectory():
            with patch("os.path.exists", return_value=False), patch("builtins.open", create=True) as mock_open:
                mock_file = MagicMock()
                mock_open.return_value.__enter__.return_value = mock_file

                result = run.check_env_file()

                assert result is False
                mock_open.assert_called_once_with(".env", "w")
                mock_file.write.assert_called_once()
                # Check that the template content is written
                written_content = mock_file.write.call_args[0][0]
                assert "SIGNAL_PHONE_NUMBER" in written_content
                assert "OPERATION_MODE=emulation" in written_content

    def test_main_no_env_file(self):
        """Test main function when .env file doesn't exist."""
        test_args = ["run.py"]
        with patch("sys.argv", test_args), patch("run.check_env_file", return_value=False):
            result = run.main()
            assert result == 1

    def test_main_emulation_mode(self):
        """Test main function with emulation flag."""
        test_args = ["run.py", "--emulation"]
        with (
            patch("sys.argv", test_args),
            patch("run.check_env_file", return_value=True),
            patch("waterbot.bot.main") as mock_bot_main,
        ):

            result = run.main()

            assert result == 0
            assert os.environ.get("OPERATION_MODE") == "emulation"
            mock_bot_main.assert_called_once()

    def test_main_test_mode(self):
        """Test main function with test flag."""
        test_args = ["run.py", "--test"]
        with (
            patch("sys.argv", test_args),
            patch("run.check_env_file", return_value=True),
            patch("builtins.__import__") as mock_import,
            patch("run.argparse.ArgumentParser") as mock_parser,
        ):
            # Mock the ArgumentParser to avoid locale issues
            mock_parser_instance = MagicMock()
            mock_parser.return_value = mock_parser_instance
            mock_parser_instance.parse_args.return_value = MagicMock(emulation=False, test=True)

            result = run.main()

            assert result == 0
            # Check that __import__ was called with 'test_emulation' (ignoring other "
            # "args)
            call_args = mock_import.call_args_list
            assert len(call_args) > 0
            assert call_args[0][0][0] == "test_emulation"

    def test_main_normal_operation(self):
        """Test main function normal operation."""
        test_args = ["run.py"]
        with (
            patch("sys.argv", test_args),
            patch("run.check_env_file", return_value=True),
            patch("waterbot.bot.main") as mock_bot_main,
        ):

            result = run.main()

            assert result == 0
            mock_bot_main.assert_called_once()

    def test_main_import_error(self):
        """Test main function with import error."""
        test_args = ["run.py"]
        with (
            patch("sys.argv", test_args),
            patch("run.check_env_file", return_value=True),
            patch("waterbot.bot.main", side_effect=ImportError("Module not found")),
        ):

            result = run.main()

            assert result == 1

    def test_main_exception_handling(self):
        """Test main function exception handling."""
        test_args = ["run.py"]
        with (
            patch("sys.argv", test_args),
            patch("run.check_env_file", return_value=True),
            patch("waterbot.bot.main", side_effect=Exception("Test error")),
        ):

            result = run.main()

            assert result == 1

    def test_main_with_args_parsing(self):
        """Test argument parsing in main function."""
        test_args = ["run.py", "--emulation", "--test"]
        with (
            patch("sys.argv", test_args),
            patch("run.check_env_file", return_value=True),
            patch("builtins.__import__") as mock_import,
            patch("run.argparse.ArgumentParser") as mock_parser,
        ):
            # Mock the ArgumentParser to avoid locale issues
            mock_parser_instance = MagicMock()
            mock_parser.return_value = mock_parser_instance
            mock_parser_instance.parse_args.return_value = MagicMock(emulation=True, test=True)

            result = run.main()

            assert result == 0
            assert os.environ.get("OPERATION_MODE") == "emulation"
            # Check that __import__ was called with 'test_emulation' (ignoring other "
            # "args)
            call_args = mock_import.call_args_list
            assert len(call_args) > 0
            assert call_args[0][0][0] == "test_emulation"
