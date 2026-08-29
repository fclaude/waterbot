"""Test cases for WaterBot Discord integration."""

from unittest.mock import AsyncMock, Mock, PropertyMock, patch

import pytest

from waterbot.discord.bot import WaterBot, get_bot_instance, set_bot_instance


class TestWaterBot:
    """Test cases for WaterBot Discord integration."""

    def setup_method(self):
        """Set up test fixtures."""
        self.config_token_patcher = patch("waterbot.discord.bot.DISCORD_BOT_TOKEN", "test_token")
        self.config_channel_patcher = patch("waterbot.discord.bot.DISCORD_CHANNEL_ID", "123456789")

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

        mock_user = Mock()
        mock_user.__str__ = Mock(return_value="TestBot#1234")

        self.bot.get_channel = Mock(return_value=mock_channel)
        mock_engine = Mock()
        mock_engine.execute_action.return_value = Mock(data={"ip_info": {}})

        with patch.object(type(self.bot), "user", new_callable=PropertyMock) as mock_user_prop:
            mock_user_prop.return_value = mock_user
            with patch.object(self.bot, "_get_action_engine", return_value=mock_engine):
                await self.bot.on_ready()

        assert self.bot.target_channel == mock_channel
        mock_channel.send.assert_called_once()
        call_args = mock_channel.send.call_args[0][0]
        assert "WaterBot is now online!" in call_args

    @pytest.mark.asyncio
    async def test_on_ready_channel_not_found(self):
        """Test on_ready event when channel is not found."""
        mock_user = Mock()
        mock_user.__str__ = Mock(return_value="TestBot#1234")

        self.bot.get_channel = Mock(return_value=None)

        with patch.object(type(self.bot), "user", new_callable=PropertyMock) as mock_user_prop:
            mock_user_prop.return_value = mock_user
            await self.bot.on_ready()

        assert self.bot.target_channel is None

    @pytest.mark.asyncio
    async def test_on_message_command(self):
        """Test handling an explicit status command without the LLM."""
        mock_message = Mock()
        mock_message.author = Mock()
        mock_message.author.id = 7
        mock_message.author.display_name = "Fran"
        mock_message.content = "status"
        mock_message.channel = Mock()
        mock_message.channel.id = 123456789
        mock_message.channel.send = AsyncMock()

        mock_user = Mock()
        mock_engine = Mock()
        mock_engine.execute_action.return_value = Mock(message="Test response", status="success")
        mock_memory = Mock()

        with patch.object(type(self.bot), "user", new_callable=PropertyMock) as mock_user_prop:
            mock_user_prop.return_value = mock_user
            with patch("waterbot.discord.bot.is_openai_configured", return_value=False):
                with patch.object(self.bot, "_get_action_engine", return_value=mock_engine):
                    with patch("waterbot.discord.bot.get_agent_memory", return_value=mock_memory):
                        await self.bot.on_message(mock_message)

        mock_engine.execute_action.assert_called_once()
        mock_message.channel.send.assert_called_once_with("Test response")

    @pytest.mark.asyncio
    async def test_on_message_ignore_bot(self):
        """Test ignoring messages from bot itself."""
        mock_message = Mock()
        mock_message.author = Mock()
        mock_message.content = "status"

        with patch.object(type(self.bot), "user", new_callable=PropertyMock) as mock_user_prop:
            mock_user_prop.return_value = mock_message.author
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
        mock_message.channel.id = 999999999

        mock_user = Mock()

        with patch.object(type(self.bot), "user", new_callable=PropertyMock) as mock_user_prop:
            mock_user_prop.return_value = mock_user
            with patch.object(self.bot, "_execute_command") as mock_execute:
                await self.bot.on_message(mock_message)

                mock_execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_start_bot_error(self):
        """Test start_bot with error."""
        with patch("waterbot.discord.bot.DISCORD_BOT_TOKEN", "test_token"):
            with patch.object(self.bot, "run") as mock_run:
                mock_run.side_effect = Exception("Connection error")

                with pytest.raises(Exception, match="Connection error"):
                    self.bot.start_bot()

    @pytest.mark.asyncio
    async def test_execute_command_status(self):
        """Test executing status command via ActionEngine."""
        mock_engine = Mock()
        mock_engine.execute_action.return_value = Mock(message="Device Status:\n- pump: ON")

        with patch.object(self.bot, "_get_action_engine", return_value=mock_engine):
            response = await self.bot._execute_command("status", {})

        assert response is not None
        assert "Device Status:" in response
        mock_engine.execute_action.assert_called_once_with(
            "status",
            {},
            source="discord_command",
            channel_id=None,
            require_confirmation=False,
        )

    @pytest.mark.asyncio
    async def test_execute_command_device_on(self):
        """Test executing device on command via ActionEngine."""
        mock_engine = Mock()
        mock_engine.execute_action.return_value = Mock(message="Device 'pump' turned ON")

        with patch.object(self.bot, "_get_action_engine", return_value=mock_engine):
            response = await self.bot._execute_command("device_on", {"device": "pump"})

        assert response is not None
        assert "Device 'pump' turned ON" in response
        mock_engine.execute_action.assert_called_once_with(
            "device_on",
            {"device": "pump"},
            source="discord_command",
            channel_id=None,
            require_confirmation=False,
        )

    @pytest.mark.asyncio
    async def test_execute_command_unknown(self):
        """Test executing unknown command."""
        mock_engine = Mock()
        mock_engine.execute_action.return_value = Mock(message="Unknown action: unknown")

        with patch.object(self.bot, "_get_action_engine", return_value=mock_engine):
            response = await self.bot._execute_command("unknown", {})

        assert response == "Unknown action: unknown"

    @pytest.mark.asyncio
    async def test_execute_command_help(self):
        """Test help command returns static help text."""
        response = await self.bot._execute_command("help", {})
        assert response is not None
        assert "Available commands:" in response

    @pytest.mark.asyncio
    async def test_execute_command_confirm(self):
        """Test executing a pending confirmation command."""
        mock_engine = Mock()
        mock_engine.confirm.return_value = Mock(message="Confirmed action")

        with patch.object(self.bot, "_get_action_engine", return_value=mock_engine):
            response = await self.bot._execute_command("confirm", {"token": "abc123"}, channel_id="123")

        assert response == "Confirmed action"
        mock_engine.confirm.assert_called_once_with("abc123", channel_id="123")

    @pytest.mark.asyncio
    async def test_execute_command_cancel(self):
        """Test cancelling a pending confirmation."""
        mock_engine = Mock()
        mock_engine.cancel.return_value = Mock(message="Cancelled")

        with patch.object(self.bot, "_get_action_engine", return_value=mock_engine):
            response = await self.bot._execute_command("cancel", {"token": "abc123"}, channel_id="123")

        assert response == "Cancelled"
        mock_engine.cancel.assert_called_once_with("abc123", channel_id="123")

    @pytest.mark.asyncio
    async def test_execute_command_why(self):
        """Test executing a policy decision explanation command."""
        mock_engine = Mock()
        mock_engine.execute_action.return_value = Mock(message="Recent policy decisions")

        with patch.object(self.bot, "_get_action_engine", return_value=mock_engine):
            response = await self.bot._execute_command("why", {"device": "pump"}, channel_id="123")

        assert response == "Recent policy decisions"
        mock_engine.execute_action.assert_called_once_with(
            "why",
            {"device": "pump"},
            source="discord_command",
            channel_id="123",
            require_confirmation=False,
        )

    @pytest.mark.asyncio
    async def test_execute_command_feedback(self):
        """Test executing a feedback command."""
        mock_engine = Mock()
        mock_engine.execute_action.return_value = Mock(message="Recorded feedback")

        with patch.object(self.bot, "_get_action_engine", return_value=mock_engine):
            response = await self.bot._execute_command(
                "feedback",
                {"device": "pump", "feedback": "too dry"},
                channel_id="123",
            )

        assert response == "Recorded feedback"
        mock_engine.execute_action.assert_called_once_with(
            "feedback",
            {"device": "pump", "feedback": "too dry"},
            source="discord_command",
            channel_id="123",
            require_confirmation=False,
        )

    @pytest.mark.asyncio
    async def test_execute_command_policy_add_every_n_days(self):
        """Test executing a flexible every-N-days cycle command."""
        mock_engine = Mock()
        mock_engine.execute_action.return_value = Mock(message="Added cycle: pump-every-3-days-0600")

        with patch.object(self.bot, "_get_action_engine", return_value=mock_engine):
            response = await self.bot._execute_command(
                "policy_add_every_n_days",
                {
                    "device": "pump",
                    "every": 3,
                    "at": "06:00",
                    "duration_minutes": 8.0,
                    "anchor_date": "2024-01-01",
                },
            )

        assert response is not None
        assert "Added cycle" in response
        mock_engine.execute_action.assert_called_once()

    def test_get_help_response(self):
        """Test get help response."""
        response = self.bot._get_help_response()

        assert "Available commands:" in response
        assert "status" in response
        assert "on <device>" in response
        assert "schedule" in response
        assert "permanent unless minutes given" in response

    def test_stop_bot(self):
        """Test stopping the bot."""
        with patch("waterbot.discord.bot.gpio_handler.cleanup") as mock_cleanup:
            self.bot.stop_bot()

            mock_cleanup.assert_called_once()

    def test_bot_instance_global(self):
        """Test global bot instance management."""
        test_bot = Mock()
        set_bot_instance(test_bot)

        result = get_bot_instance()
        assert result == test_bot

    @pytest.mark.asyncio
    async def test_on_message_openai_integration(self):
        """Test on_message with OpenAI integration enabled."""
        mock_message = Mock()
        mock_message.author = Mock()
        mock_message.author.id = 42
        mock_message.author.display_name = "Fran"
        mock_message.content = "What's the status?"
        mock_message.channel = Mock()
        mock_message.channel.id = 123456789
        mock_message.channel.send = AsyncMock()

        mock_user = Mock()

        with patch.object(type(self.bot), "user", new_callable=PropertyMock) as mock_user_prop:
            mock_user_prop.return_value = mock_user
            with patch("waterbot.discord.bot.is_openai_configured", return_value=True):
                with patch("waterbot.discord.bot.process_with_openai") as mock_openai:
                    mock_openai.return_value = "OpenAI response"

                    await self.bot.on_message(mock_message)

                    mock_openai.assert_called_once_with("What's the status?", "123456789", "42", "Fran")
                    mock_message.channel.send.assert_called_once_with("OpenAI response")

    @pytest.mark.asyncio
    async def test_on_message_openai_fallback(self):
        """Test OpenAI failure falls back to the command parser."""
        mock_message = Mock()
        mock_message.author = Mock()
        mock_message.content = "how wet is the garden"
        mock_message.channel = Mock()
        mock_message.channel.id = 123456789
        mock_message.channel.send = AsyncMock()

        mock_user = Mock()

        with patch.object(type(self.bot), "user", new_callable=PropertyMock) as mock_user_prop:
            mock_user_prop.return_value = mock_user
            with patch("waterbot.discord.bot.is_openai_configured", return_value=True):
                with patch(
                    "waterbot.discord.bot.process_with_openai",
                    side_effect=RuntimeError("api down"),
                ):
                    with patch.object(self.bot, "_execute_command", return_value="fallback") as mock_execute:
                        await self.bot.on_message(mock_message)

        mock_execute.assert_called_once()
        mock_message.channel.send.assert_called_once_with("fallback")

    def test_start_bot_no_token(self):
        """Test starting bot without token."""
        with patch("waterbot.discord.bot.DISCORD_BOT_TOKEN", None):
            with pytest.raises(ValueError, match="Discord bot token not configured"):
                self.bot.start_bot()
