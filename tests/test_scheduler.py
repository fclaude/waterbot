"""Tests for scheduler functionality."""

from unittest.mock import Mock, patch

from waterbot.scheduler import DeviceScheduler


class TestDeviceScheduler:
    """Test cases for DeviceScheduler."""

    def setup_method(self):
        """Set up test fixtures."""
        self.scheduler = DeviceScheduler()

    def teardown_method(self):
        """Clean up after each test."""
        if self.scheduler.running:
            self.scheduler.stop()

    @patch("waterbot.scheduler.ENABLE_SCHEDULING", True)
    @patch(
        "waterbot.scheduler.DEVICE_SCHEDULES",
        {
            "pump": {"on": ["08:00"], "off": ["20:00"]},
            "light": {"on": ["06:30"], "off": ["22:00"]},
        },
    )
    @patch("waterbot.scheduler.schedule")
    def test_setup_schedules(self, mock_schedule):
        """Test setting up schedules from configuration."""
        mock_job = Mock()
        mock_schedule.every.return_value.day.at.return_value.do.return_value = mock_job

        self.scheduler.setup_schedules()

        # Should have 4 scheduled jobs (2 devices x 2 actions each)
        assert len(self.scheduler.scheduled_jobs) == 4

        # Verify schedule.every().day.at().do() was called for each time
        assert mock_schedule.every.return_value.day.at.return_value.do.call_count == 4

    @patch("waterbot.scheduler.ENABLE_SCHEDULING", False)
    @patch("waterbot.scheduler.schedule")
    def test_setup_schedules_disabled(self, mock_schedule):
        """Test that schedules are not set up when scheduling is disabled."""
        self.scheduler.setup_schedules()

        assert len(self.scheduler.scheduled_jobs) == 0
        mock_schedule.clear.assert_called_once()

    @patch("waterbot.scheduler.gpio_handler")
    def test_schedule_device_action_on(self, mock_gpio):
        """Test scheduling a device 'on' action."""
        mock_gpio.turn_on.return_value = True

        with patch("waterbot.scheduler.schedule") as mock_schedule:
            mock_job = Mock()
            mock_schedule.every.return_value.day.at.return_value.do.return_value = (
                mock_job
            )

            self.scheduler._schedule_device_action("pump", "on", "08:00")

            # Verify job was created
            assert len(self.scheduler.scheduled_jobs) == 1
            job_info = self.scheduler.scheduled_jobs[0]
            assert job_info["device"] == "pump"
            assert job_info["action"] == "on"
            assert job_info["time"] == "08:00"

            # Simulate job execution
            scheduled_function = (
                mock_schedule.every.return_value.day.at.return_value.do.call_args[0][0]
            )
            scheduled_function()

            mock_gpio.turn_on.assert_called_once_with("pump")

    @patch("waterbot.scheduler.gpio_handler")
    def test_schedule_device_action_off(self, mock_gpio):
        """Test scheduling a device 'off' action."""
        mock_gpio.turn_off.return_value = True

        with patch("waterbot.scheduler.schedule") as mock_schedule:
            mock_job = Mock()
            mock_schedule.every.return_value.day.at.return_value.do.return_value = (
                mock_job
            )

            self.scheduler._schedule_device_action("pump", "off", "20:00")

            # Simulate job execution
            scheduled_function = (
                mock_schedule.every.return_value.day.at.return_value.do.call_args[0][0]
            )
            scheduled_function()

            mock_gpio.turn_off.assert_called_once_with("pump")

    @patch("waterbot.config.add_schedule")
    def test_add_schedule_success(self, mock_config_add):
        """Test adding a new schedule dynamically."""
        mock_config_add.return_value = True

        with patch.object(
            self.scheduler, "_schedule_device_action"
        ) as mock_schedule_action:
            success = self.scheduler.add_schedule("pump", "on", "09:00")

            assert success is True
            mock_config_add.assert_called_once_with("pump", "on", "09:00")
            mock_schedule_action.assert_called_once_with("pump", "on", "09:00")

    @patch("waterbot.config.add_schedule")
    def test_add_schedule_failure(self, mock_config_add):
        """Test adding a schedule that fails validation."""
        mock_config_add.return_value = False

        success = self.scheduler.add_schedule("invalid", "on", "09:00")

        assert success is False
        mock_config_add.assert_called_once_with("invalid", "on", "09:00")

    @patch("waterbot.config.remove_schedule")
    @patch("waterbot.scheduler.schedule")
    def test_remove_schedule_success(self, mock_schedule, mock_config_remove):
        """Test removing an existing schedule."""
        mock_config_remove.return_value = True

        # Set up a scheduled job
        mock_job = Mock()
        self.scheduler.scheduled_jobs.append(
            {"device": "pump", "action": "on", "time": "08:00", "job": mock_job}
        )

        success = self.scheduler.remove_schedule("pump", "on", "08:00")

        assert success is True
        assert len(self.scheduler.scheduled_jobs) == 0
        mock_schedule.cancel_job.assert_called_once_with(mock_job)
        mock_config_remove.assert_called_once_with("pump", "on", "08:00")

    @patch("waterbot.config.remove_schedule")
    def test_remove_schedule_not_found(self, mock_config_remove):
        """Test removing a schedule that doesn't exist."""
        mock_config_remove.return_value = False

        success = self.scheduler.remove_schedule("pump", "on", "08:00")

        assert success is False
        mock_config_remove.assert_called_once_with("pump", "on", "08:00")

    def test_get_next_runs(self):
        """Test getting next scheduled runs."""
        from datetime import datetime, timedelta

        # Create mock jobs with next_run times
        future_time = datetime.now() + timedelta(hours=1)
        mock_job1 = Mock()
        mock_job1.next_run = future_time
        mock_job2 = Mock()
        mock_job2.next_run = future_time + timedelta(hours=2)

        self.scheduler.scheduled_jobs = [
            {"device": "pump", "action": "on", "time": "08:00", "job": mock_job1},
            {"device": "light", "action": "off", "time": "22:00", "job": mock_job2},
        ]

        next_runs = self.scheduler.get_next_runs()

        assert len(next_runs) == 2
        assert next_runs[0]["device"] == "pump"  # Should be first (earlier time)
        assert next_runs[1]["device"] == "light"

    @patch("waterbot.scheduler.ENABLE_SCHEDULING", True)
    def test_start_scheduler(self):
        """Test starting the scheduler."""
        with patch.object(self.scheduler, "setup_schedules") as mock_setup:
            with patch("threading.Thread") as mock_thread:
                mock_thread_instance = Mock()
                mock_thread.return_value = mock_thread_instance

                self.scheduler.start()

                assert self.scheduler.running is True
                mock_setup.assert_called_once()
                mock_thread.assert_called_once()
                mock_thread_instance.start.assert_called_once()

    @patch("waterbot.scheduler.ENABLE_SCHEDULING", False)
    def test_start_scheduler_disabled(self):
        """Test starting scheduler when scheduling is disabled."""
        self.scheduler.start()

        assert self.scheduler.running is False

    def test_start_scheduler_already_running(self):
        """Test starting scheduler when already running."""
        self.scheduler.running = True

        with patch.object(self.scheduler, "setup_schedules") as mock_setup:
            self.scheduler.start()

            mock_setup.assert_not_called()

    @patch("waterbot.scheduler.schedule")
    def test_stop_scheduler(self, mock_schedule):
        """Test stopping the scheduler."""
        self.scheduler.running = True
        mock_thread = Mock()
        mock_thread.is_alive.return_value = True
        self.scheduler.scheduler_thread = mock_thread

        self.scheduler.stop()

        assert self.scheduler.running is False
        mock_thread.join.assert_called_once_with(timeout=5)
        mock_schedule.clear.assert_called_once()
        assert len(self.scheduler.scheduled_jobs) == 0

    def test_stop_scheduler_not_running(self):
        """Test stopping scheduler when not running."""
        self.scheduler.running = False

        with patch("waterbot.scheduler.schedule") as mock_schedule:
            self.scheduler.stop()

            mock_schedule.clear.assert_not_called()

    @patch("waterbot.scheduler.schedule")
    @patch("waterbot.scheduler.time.sleep")
    def test_run_scheduler_loop(self, mock_sleep, mock_schedule):
        """Test the scheduler loop execution."""
        self.scheduler.running = True

        # Mock sleep to only run once
        def stop_after_first_iteration(*args):
            self.scheduler.running = False

        mock_sleep.side_effect = stop_after_first_iteration

        self.scheduler._run_scheduler()

        mock_schedule.run_pending.assert_called_once()
        mock_sleep.assert_called_once_with(1)


class TestSchedulerModuleFunctions:
    """Test module-level scheduler functions."""

    def teardown_method(self):
        """Clean up global scheduler."""
        from waterbot.scheduler import _scheduler

        if _scheduler and _scheduler.running:
            _scheduler.stop()

    def test_get_scheduler_singleton(self):
        """Test that get_scheduler returns the same instance."""
        from waterbot.scheduler import get_scheduler

        scheduler1 = get_scheduler()
        scheduler2 = get_scheduler()

        assert scheduler1 is scheduler2

    @patch("waterbot.scheduler.ENABLE_SCHEDULING", True)
    def test_start_stop_scheduler_functions(self):
        """Test module-level start and stop functions."""
        from waterbot.scheduler import get_scheduler, start_scheduler, stop_scheduler

        with patch.object(get_scheduler(), "start") as mock_start:
            with patch.object(get_scheduler(), "stop") as mock_stop:
                start_scheduler()
                mock_start.assert_called_once()

                stop_scheduler()
                mock_stop.assert_called_once()

    def test_add_remove_schedule_functions(self):
        """Test module-level add and remove schedule functions."""
        from waterbot.scheduler import add_schedule, get_scheduler, remove_schedule

        with patch.object(get_scheduler(), "add_schedule") as mock_add:
            with patch.object(get_scheduler(), "remove_schedule") as mock_remove:
                add_schedule("pump", "on", "08:00")
                mock_add.assert_called_once_with("pump", "on", "08:00")

                remove_schedule("pump", "on", "08:00")
                mock_remove.assert_called_once_with("pump", "on", "08:00")

    def test_get_next_runs_function(self):
        """Test module-level get_next_runs function."""
        from waterbot.scheduler import get_next_runs, get_scheduler

        with patch.object(get_scheduler(), "get_next_runs") as mock_get_next:
            mock_get_next.return_value = []

            result = get_next_runs()

            mock_get_next.assert_called_once()
            assert result == []
