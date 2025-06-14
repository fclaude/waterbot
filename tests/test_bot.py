"""Test cases for the main bot entry point."""

import signal
import sys
from unittest.mock import Mock, patch

from waterbot import bot


class TestMainBot:
    """Test cases for the main bot functionality."""

    def test_handle_shutdown_without_bot(self):
        """Test shutdown handler without bot instance."""
        with patch.object(sys, "exit") as mock_exit:
            with patch("waterbot.bot.scheduler.stop_scheduler") as mock_stop:
                bot.handle_shutdown(signal.SIGINT, None)

                mock_stop.assert_called_once()
                mock_exit.assert_called_once_with(0)

    def test_handle_shutdown_with_bot(self):
        """Test shutdown handler with bot instance."""
        mock_bot = Mock()
        bot.handle_shutdown.bot = mock_bot  # type: ignore[attr-defined]

        with patch.object(sys, "exit") as mock_exit:
            with patch("waterbot.bot.scheduler.stop_scheduler") as mock_stop:
                bot.handle_shutdown(signal.SIGINT, None)

                mock_bot.stop_bot.assert_called_once()
                mock_stop.assert_called_once()
                mock_exit.assert_called_once_with(0)

    @patch("waterbot.bot.signal.signal")
    @patch("waterbot.bot.validate_config")
    @patch("waterbot.bot.scheduler.start_scheduler")
    @patch("waterbot.bot.WaterBot")
    @patch("waterbot.bot.ENABLE_SCHEDULING", True)
    def test_main_success_with_scheduling(
        self, mock_waterbot, mock_start_scheduler, mock_validate, mock_signal
    ):
        """Test successful main execution with scheduling enabled."""
        mock_bot_instance = Mock()
        mock_waterbot.return_value = mock_bot_instance

        bot.main()

        mock_validate.assert_called_once()
        mock_start_scheduler.assert_called_once()
        mock_waterbot.assert_called_once()
        mock_bot_instance.start_bot.assert_called_once()

    @patch("waterbot.bot.signal.signal")
    @patch("waterbot.bot.validate_config")
    @patch("waterbot.bot.scheduler.start_scheduler")
    @patch("waterbot.bot.WaterBot")
    @patch("waterbot.bot.ENABLE_SCHEDULING", False)
    def test_main_success_without_scheduling(
        self, mock_waterbot, mock_start_scheduler, mock_validate, mock_signal
    ):
        """Test successful main execution with scheduling disabled."""
        mock_bot_instance = Mock()
        mock_waterbot.return_value = mock_bot_instance

        bot.main()

        mock_validate.assert_called_once()
        mock_start_scheduler.assert_not_called()
        mock_waterbot.assert_called_once()
        mock_bot_instance.start_bot.assert_called_once()

    @patch("waterbot.bot.signal.signal")
    @patch("waterbot.bot.validate_config")
    @patch("waterbot.bot.WaterBot")
    @patch("waterbot.bot.scheduler.stop_scheduler")
    @patch("waterbot.bot.gpio_handler.cleanup")
    def test_main_keyboard_interrupt(
        self,
        mock_cleanup,
        mock_stop_scheduler,
        mock_waterbot,
        mock_validate,
        mock_signal,
    ):
        """Test main execution with keyboard interrupt."""
        mock_bot_instance = Mock()
        mock_waterbot.return_value = mock_bot_instance
        mock_bot_instance.start_bot.side_effect = KeyboardInterrupt()

        bot.main()

        mock_bot_instance.stop_bot.assert_called_once()
        mock_stop_scheduler.assert_called_once()
        mock_cleanup.assert_called_once()

    @patch("waterbot.bot.signal.signal")
    @patch("waterbot.bot.validate_config")
    @patch("waterbot.bot.WaterBot")
    @patch("waterbot.bot.scheduler.stop_scheduler")
    @patch("waterbot.bot.gpio_handler.cleanup")
    def test_main_exception(
        self,
        mock_cleanup,
        mock_stop_scheduler,
        mock_waterbot,
        mock_validate,
        mock_signal,
    ):
        """Test main execution with exception."""
        mock_bot_instance = Mock()
        mock_waterbot.return_value = mock_bot_instance
        mock_bot_instance.start_bot.side_effect = Exception("Test error")

        bot.main()

        mock_bot_instance.stop_bot.assert_called_once()
        mock_stop_scheduler.assert_called_once()
        mock_cleanup.assert_called_once()

    @patch("waterbot.bot.signal.signal")
    @patch("waterbot.bot.validate_config")
    @patch("waterbot.bot.scheduler.stop_scheduler")
    @patch("waterbot.bot.gpio_handler.cleanup")
    def test_main_validation_error(
        self, mock_cleanup, mock_stop_scheduler, mock_validate, mock_signal
    ):
        """Test main execution with config validation error."""
        mock_validate.side_effect = Exception("Config error")

        bot.main()

        mock_stop_scheduler.assert_called_once()
        mock_cleanup.assert_called_once()
