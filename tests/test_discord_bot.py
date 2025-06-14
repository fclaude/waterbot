"""Test cases for WaterBot Discord integration."""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from waterbot.discord.bot import WaterBot


class TestWaterBot:
    """Test cases for WaterBot Discord integration."""

    def setup_method(self):
        """Set up test fixtures."""
        # Patch the config values
        self.config_token_patcher = patch(
            "waterbot.discord.bot.DISCORD_BOT_TOKEN", "test_token"
        )
        self.config_channel_patcher = patch(
            "waterbot.discord.bot.DISCORD_CHANNEL_ID", "123456789"
        )

        self.config_token_patcher.start()
        self.config_channel_patcher.start()

        self.bot = WaterBot()

    def teardown_method(self):
        """Clean up test fixtures."""
        self.config_token_patcher.stop()
        self.config_channel_patcher.stop()

    def test_bot_initialization(self):
        """Test bot initialization."""
        assert self.bot.channel_id == 123456789
        assert self.bot.target_channel is None

    @pytest.mark.asyncio
    async def test_on_ready(self):
        """Test on_ready event."""
        mock_channel = Mock()
        mock_channel.name = "test-channel"
        mock_channel.send = AsyncMock()

        self.bot.get_channel = Mock(return_value=mock_channel)
        self.bot.user = Mock()
        self.bot.user.__str__ = Mock(return_value="TestBot#1234")

        await self.bot.on_ready()

        assert self.bot.target_channel == mock_channel
        mock_channel.send.assert_called_once()
        call_args = mock_channel.send.call_args[0][0]
        assert "WaterBot is now online!" in call_args

    @pytest.mark.asyncio
    async def test_on_message_command(self):
        """Test handling command message."""
        mock_message = Mock()
        mock_message.author = Mock()
        mock_message.content = "status"
        mock_message.channel = Mock()
        mock_message.channel.id = 123456789
        mock_message.channel.send = AsyncMock()

        # Mock the bot user
        self.bot.user = Mock()

        with patch.object(self.bot, "_execute_command") as mock_execute:
            mock_execute.return_value = "Test response"

            await self.bot.on_message(mock_message)

            mock_execute.assert_called_once()
            mock_message.channel.send.assert_called_once_with("Test response")

    @pytest.mark.asyncio
    async def test_on_message_ignore_bot(self):
        """Test ignoring messages from bot itself."""
        mock_message = Mock()
        mock_message.author = Mock()
        mock_message.content = "status"

        # Set bot user to be the message author
        self.bot.user = mock_message.author

        with patch.object(self.bot, "_execute_command") as mock_execute:
            await self.bot.on_message(mock_message)

            mock_execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_on_message_wrong_channel(self):
        """Test ignoring messages from wrong channel."""
        mock_message = Mock()
        mock_message.author = Mock()
        mock_message.content = "status"
        mock_message.channel = Mock()
        mock_message.channel.id = 999999999  # Different channel ID

        # Mock the bot user
        self.bot.user = Mock()

        with patch.object(self.bot, "_execute_command") as mock_execute:
            await self.bot.on_message(mock_message)

            mock_execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_status_command(self):
        """Test status command."""
        mock_ctx = Mock()
        mock_ctx.send = AsyncMock()

        with patch.object(self.bot, "_get_status_response") as mock_status:
            mock_status.return_value = "Status response"

            await self.bot.status_command(mock_ctx)

            mock_ctx.send.assert_called_once_with("Status response")

    @pytest.mark.asyncio
    async def test_schedules_command(self):
        """Test schedules command."""
        mock_ctx = Mock()
        mock_ctx.send = AsyncMock()

        with patch.object(self.bot, "_get_schedules_response") as mock_schedules:
            mock_schedules.return_value = "Schedules response"

            await self.bot.schedules_command(mock_ctx)

            mock_ctx.send.assert_called_once_with("Schedules response")

    @pytest.mark.asyncio
    async def test_on_command_device(self):
        """Test on command for specific device."""
        mock_ctx = Mock()
        mock_ctx.send = AsyncMock()

        with patch("waterbot.discord.bot.gpio_handler.turn_on") as mock_turn_on:
            mock_turn_on.return_value = True

            await self.bot.on_command(mock_ctx, "pump", None)

            mock_turn_on.assert_called_once_with("pump", None)
            mock_ctx.send.assert_called_once()
            call_args = mock_ctx.send.call_args[0][0]
            assert "Device 'pump' turned ON" in call_args

    @pytest.mark.asyncio
    async def test_on_command_all(self):
        """Test on command for all devices."""
        mock_ctx = Mock()
        mock_ctx.send = AsyncMock()

        with patch("waterbot.discord.bot.gpio_handler.turn_all_on") as mock_turn_all_on:
            await self.bot.on_command(mock_ctx, "all", None)

            mock_turn_all_on.assert_called_once()
            mock_ctx.send.assert_called_once_with("All devices turned ON")

    @pytest.mark.asyncio
    async def test_off_command_device(self):
        """Test off command for specific device."""
        mock_ctx = Mock()
        mock_ctx.send = AsyncMock()

        with patch("waterbot.discord.bot.gpio_handler.turn_off") as mock_turn_off:
            mock_turn_off.return_value = True

            await self.bot.off_command(mock_ctx, "light", 3600)

            mock_turn_off.assert_called_once_with("light", 3600)
            mock_ctx.send.assert_called_once()
            call_args = mock_ctx.send.call_args[0][0]
            assert "Device 'light' turned OFF for 3600 seconds" in call_args

    @pytest.mark.asyncio
    async def test_schedule_command(self):
        """Test schedule command."""
        mock_ctx = Mock()
        mock_ctx.send = AsyncMock()

        with patch("waterbot.discord.bot.scheduler.add_schedule") as mock_add_schedule:
            mock_add_schedule.return_value = True

            await self.bot.schedule_command(mock_ctx, "pump", "on", "08:00")

            mock_add_schedule.assert_called_once_with("pump", "on", "08:00")
            mock_ctx.send.assert_called_once()
            call_args = mock_ctx.send.call_args[0][0]
            assert "Added schedule: pump on at 08:00" in call_args

    @pytest.mark.asyncio
    async def test_unschedule_command(self):
        """Test unschedule command."""
        mock_ctx = Mock()
        mock_ctx.send = AsyncMock()

        with patch(
            "waterbot.discord.bot.scheduler.remove_schedule"
        ) as mock_remove_schedule:
            mock_remove_schedule.return_value = True

            await self.bot.unschedule_command(mock_ctx, "pump", "on", "08:00")

            mock_remove_schedule.assert_called_once_with("pump", "on", "08:00")
            mock_ctx.send.assert_called_once()
            call_args = mock_ctx.send.call_args[0][0]
            assert "Removed schedule: pump on at 08:00" in call_args

    @pytest.mark.asyncio
    async def test_help_command(self):
        """Test help command."""
        mock_ctx = Mock()
        mock_ctx.send = AsyncMock()

        await self.bot.help_command(mock_ctx)

        mock_ctx.send.assert_called_once()
        call_args = mock_ctx.send.call_args[0][0]
        assert "Available commands:" in call_args
        assert "!status" in call_args

    @pytest.mark.asyncio
    async def test_execute_command_status(self):
        """Test executing status command."""
        with patch("waterbot.discord.bot.gpio_handler.get_status") as mock_get_status:
            mock_get_status.return_value = {"pump": True, "light": False}

            response = await self.bot._execute_command("status", {})

            assert response is not None
            assert "Device Status:" in response
            assert "pump: ON" in response
            assert "light: OFF" in response

    @pytest.mark.asyncio
    async def test_execute_command_device_on(self):
        """Test executing device on command."""
        with patch("waterbot.discord.bot.gpio_handler.turn_on") as mock_turn_on:
            mock_turn_on.return_value = True

            response = await self.bot._execute_command(
                "device_on", {"device": "pump", "timeout": None}
            )

            assert response is not None
            assert "Device 'pump' turned ON" in response
            mock_turn_on.assert_called_once_with("pump", None)

    @pytest.mark.asyncio
    async def test_execute_command_unknown(self):
        """Test executing unknown command."""
        response = await self.bot._execute_command("unknown", {})

        assert response is not None
        assert "Unknown command" in response
        assert "!help" in response

    def test_get_help_response(self):
        """Test get help response."""
        response = self.bot._get_help_response()

        assert "Available commands:" in response
        assert "!status" in response
        assert "!on <device>" in response
        assert "!schedule" in response

    def test_get_status_response(self):
        """Test get status response."""
        with patch("waterbot.discord.bot.gpio_handler.get_status") as mock_get_status:
            mock_get_status.return_value = {"pump": True, "light": False}

            response = self.bot._get_status_response()

            assert "Device Status:" in response
            assert "pump: ON" in response
            assert "light: OFF" in response

    def test_get_status_response_empty(self):
        """Test get status response with no devices."""
        with patch("waterbot.discord.bot.gpio_handler.get_status") as mock_get_status:
            mock_get_status.return_value = {}

            response = self.bot._get_status_response()

            assert response == "No devices configured"

    def test_get_schedules_response(self):
        """Test get schedules response."""
        mock_schedules = {"pump": {"on": ["08:00"], "off": ["20:00"]}}
        mock_next_runs = [
            {
                "device": "pump",
                "action": "on",
                "time": "08:00",
                "next_run": "2024-01-01 08:00:00",
            }
        ]

        with patch("waterbot.discord.bot.get_schedules") as mock_get_schedules:
            with patch(
                "waterbot.discord.bot.scheduler.get_next_runs"
            ) as mock_get_next_runs:
                mock_get_schedules.return_value = mock_schedules
                mock_get_next_runs.return_value = mock_next_runs

                response = self.bot._get_schedules_response()

                assert "Device Schedules:" in response
                assert "PUMP:" in response
                assert "ON at 08:00" in response
                assert "OFF at 20:00" in response
                assert "Next scheduled runs:" in response

    def test_get_schedules_response_empty(self):
        """Test get schedules response with no schedules."""
        with patch("waterbot.discord.bot.get_schedules") as mock_get_schedules:
            mock_get_schedules.return_value = {}

            response = self.bot._get_schedules_response()

            assert response == "No schedules configured"

    def test_stop_bot(self):
        """Test stopping the bot."""
        with patch("waterbot.discord.bot.gpio_handler.cleanup") as mock_cleanup:
            self.bot.stop_bot()

            mock_cleanup.assert_called_once()
