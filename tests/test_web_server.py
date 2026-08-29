"""Tests for the WaterBot web interface."""

import base64
import io
import json
from unittest.mock import MagicMock, patch

from waterbot.actions import ActionResult
from waterbot.policy import PolicyValidationError
from waterbot.web.server import WebInterfaceServer, _recurrence_text

_TEST_PASSWORD = "test-pass"  # pragma: allowlist secret
_TEST_TOKEN = "test-token"  # pragma: allowlist secret
_WRONG_PASSWORD = "wrong"  # pragma: allowlist secret


def _auth_header(username: str = "admin", password: str = _TEST_PASSWORD) -> str:
    token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


def _request(server: WebInterfaceServer, method: str, path: str, body=None, headers=None):
    handler_cls = server._handler_class()
    handler = object.__new__(handler_cls)
    payload = json.dumps(body).encode("utf-8") if body is not None else b""
    request_headers = dict(headers or {})
    if payload:
        request_headers["Content-Type"] = "application/json"
        request_headers["Content-Length"] = str(len(payload))
    handler.path = path
    handler.headers = request_headers
    handler.rfile = io.BytesIO(payload)
    handler.wfile = io.BytesIO()
    response_headers = []

    def send_response(status):
        handler._status = int(status)

    def send_header(name, value):
        response_headers.append((name, value))

    handler.send_response = send_response
    handler.send_header = send_header
    handler.end_headers = lambda: None

    getattr(handler, f"do_{method}")()
    return handler._status, response_headers, handler.wfile.getvalue()


def test_public_schedule_page_and_api_render_schedules():
    """Public schedule pages should render legacy and flexible schedules."""
    engine = MagicMock()
    server = WebInterfaceServer(
        host="127.0.0.1",
        port=0,
        password=_TEST_PASSWORD,
        public_schedules=True,
        action_engine=engine,
    )
    policy = {
        "id": "pump-cycle",
        "device": "pump",
        "recurrence": {"type": "every_n_days", "every": 3, "at": "06:00"},
        "duration": {"base_minutes": 8, "min_minutes": 4, "max_minutes": 12},
    }

    with (
        patch("waterbot.web.server.get_schedules", return_value={"pump": {"on": ["06:00"], "off": ["06:10"]}}),
        patch(
            "waterbot.web.server.scheduler.get_next_runs",
            return_value=[{"device": "pump", "action": "on", "next_run": "tomorrow"}],
        ),
        patch("waterbot.web.server.scheduler.get_policy_schedules", return_value=[policy]),
        patch(
            "waterbot.web.server.scheduler.get_next_policy_runs",
            return_value=[{"id": "pump-cycle", "device": "pump", "next_run": "2026-07-07 06:00"}],
        ),
    ):
        status, _, data = _request(server, "GET", "/")
        assert status == 200
        html = data.decode("utf-8")
        assert "WaterBot Schedules" in html
        assert "pump-cycle" in html
        assert "ON" in html

        status, _, data = _request(server, "GET", "/api/schedules")
        assert status == 200
        payload = json.loads(data)
        assert payload["legacy_schedules"]["pump"]["on"] == ["06:00"]
        assert payload["policy_schedules"][0]["id"] == "pump-cycle"


def test_private_schedule_page_requires_authentication():
    """Private schedule mode should require HTTP authentication."""
    server = WebInterfaceServer(
        host="127.0.0.1",
        port=0,
        password=_TEST_PASSWORD,
        public_schedules=False,
        action_engine=MagicMock(),
    )
    with (
        patch("waterbot.web.server.get_schedules", return_value={}),
        patch("waterbot.web.server.scheduler.get_next_runs", return_value=[]),
        patch("waterbot.web.server.scheduler.get_policy_schedules", return_value=[]),
        patch("waterbot.web.server.scheduler.get_next_policy_runs", return_value=[]),
    ):
        status, headers, data = _request(server, "GET", "/")
        assert status == 401
        assert b"Authentication required" in data
        assert any(name == "WWW-Authenticate" for name, _ in headers)

        status, _, data = _request(server, "GET", "/", headers={"Authorization": _auth_header()})
        assert status == 200
        assert b"WaterBot Schedules" in data


def test_chat_page_and_api_require_auth_and_route_commands():
    """Authenticated chat should use the shared action engine when OpenAI is disabled."""
    engine = MagicMock()
    engine.execute_action.return_value = ActionResult("success", "Device Status:\n- pump: ON")
    server = WebInterfaceServer(
        host="127.0.0.1",
        port=0,
        password=_TEST_PASSWORD,
        public_schedules=True,
        action_engine=engine,
    )

    with patch("waterbot.web.server.is_openai_configured", return_value=False):
        status, _, _ = _request(server, "GET", "/chat")
        assert status == 401

        status, _, data = _request(server, "GET", "/chat", headers={"Authorization": _auth_header()})
        assert status == 200
        assert b"WaterBot Chat" in data

        status, _, data = _request(
            server,
            "POST",
            "/api/chat",
            body={"message": "status"},
            headers={"Authorization": _auth_header()},
        )
        assert status == 200
        assert json.loads(data)["response"] == "Device Status:\n- pump: ON"
        engine.execute_action.assert_called_once_with(
            "status",
            {},
            source="web",
            channel_id="web",
            require_confirmation=False,
        )

        status, _, data = _request(
            server,
            "POST",
            "/api/chat",
            body={"message": ""},
            headers={"Authorization": _auth_header()},
        )
        assert status == 400
        assert json.loads(data)["error"] == "message is required"


def test_chat_confirm_cancel_help_error_and_bearer_auth():
    """Fallback chat should cover confirmation, cancellation, help, parser errors, and bearer auth."""
    engine = MagicMock()
    engine.confirm.return_value = ActionResult("success", "Confirmed")
    engine.cancel.return_value = ActionResult("cancelled", "Cancelled")
    server = WebInterfaceServer(
        host="127.0.0.1",
        port=0,
        password=_TEST_PASSWORD,
        token=_TEST_TOKEN,
        action_engine=engine,
    )

    assert server.is_authenticated(f"Bearer {_TEST_TOKEN}") is True
    assert server.is_authenticated(_auth_header()) is True
    assert server.is_authenticated(_auth_header(password=_WRONG_PASSWORD)) is False
    assert server.is_authenticated("Basic not-base64") is False

    with patch("waterbot.web.server.get_agent_memory", return_value=MagicMock()):
        with patch("waterbot.web.server.is_openai_configured", return_value=False):
            assert server.chat("confirm abc123") == "Confirmed"
            engine.confirm.assert_called_once_with("abc123", channel_id="web")
            assert server.chat("cancel abc123") == "Cancelled"
            engine.cancel.assert_called_once_with("abc123", channel_id="web")
            assert "Try status" in server.chat("nonsense")

            with patch("waterbot.web.server.parse_command", return_value=("error", {"message": "bad command"})):
                assert server.chat("bad") == "bad command"


def test_chat_uses_openai_when_configured():
    """OpenAI-enabled chat should delegate to the agent integration."""
    server = WebInterfaceServer(
        host="127.0.0.1",
        port=0,
        password=_TEST_PASSWORD,
        action_engine=MagicMock(),
    )

    async def fake_process(message, channel_id, author_id=None, author_name=None):
        return f"{channel_id}:{author_name}:{message}"

    with (
        patch("waterbot.web.server.is_openai_configured", return_value=True),
        patch("waterbot.web.server.process_with_openai", side_effect=fake_process),
    ):
        assert server.chat("hello") == "web:Web:hello"


def test_policy_error_is_reported_in_schedule_snapshot():
    """Invalid flexible schedule config should be visible in the web snapshot."""
    server = WebInterfaceServer(
        host="127.0.0.1",
        port=0,
        password=_TEST_PASSWORD,
        action_engine=MagicMock(),
    )
    with (
        patch("waterbot.web.server.get_schedules", return_value={}),
        patch("waterbot.web.server.scheduler.get_next_runs", return_value=[]),
        patch("waterbot.web.server.scheduler.get_policy_schedules", side_effect=PolicyValidationError("bad policy")),
        patch("waterbot.web.server.scheduler.get_next_policy_runs", side_effect=PolicyValidationError("bad next run")),
    ):
        snapshot = server.schedule_snapshot()

    assert snapshot["policy_schedules"] == []
    assert snapshot["policy_next_runs"] == []
    assert snapshot["policy_error"] == "bad policy"


def test_server_start_stop_lifecycle_without_socket():
    """Server lifecycle should bind once and shut down cleanly."""
    server = WebInterfaceServer(host="127.0.0.1", port=8080, password=_TEST_PASSWORD, action_engine=MagicMock())
    httpd = MagicMock()
    httpd.server_address = ("127.0.0.1", 9080)
    thread = MagicMock()
    thread.is_alive.return_value = True

    with (
        patch("waterbot.web.server.ThreadingHTTPServer", return_value=httpd) as mock_httpd_cls,
        patch("waterbot.web.server.threading.Thread", return_value=thread) as mock_thread_cls,
    ):
        server.start()
        server.start()

        mock_httpd_cls.assert_called_once()
        mock_thread_cls.assert_called_once()
        thread.start.assert_called_once()
        assert server.server_port == 9080

        server.stop()

    httpd.shutdown.assert_called_once()
    httpd.server_close.assert_called_once()
    thread.join.assert_called_once_with(timeout=5)
    assert server.server_port == 8080


def test_handler_error_routes_logo_and_invalid_json():
    """Handler error paths should return clear status codes without sockets."""
    server = WebInterfaceServer(
        host="127.0.0.1",
        port=0,
        password=_TEST_PASSWORD,
        public_schedules=False,
        action_engine=MagicMock(),
    )

    status, _, data = _request(server, "GET", "/missing")
    assert status == 404
    assert json.loads(data)["error"] == "Not found"

    with patch("waterbot.web.server.Path.exists", return_value=False):
        status, _, data = _request(server, "GET", "/waterbot.png")
    assert status == 404
    assert json.loads(data)["error"] == "Logo not found"

    status, _, data = _request(server, "POST", "/api/chat", body={"message": "status"})
    assert status == 401
    assert b"Authentication required" in data

    status, _, data = _request(server, "POST", "/missing", headers={"Authorization": _auth_header()})
    assert status == 404
    assert json.loads(data)["error"] == "Not found"

    status, _, data = _request(
        server,
        "POST",
        "/api/chat",
        body="not-a-dict",
        headers={"Authorization": _auth_header()},
    )
    assert status == 400
    assert json.loads(data)["error"] == "message is required"


def test_auth_without_password_and_recurrence_text_variants():
    """Auth and recurrence helpers should cover non-default branches."""
    server = WebInterfaceServer(password=None, action_engine=MagicMock())
    assert server.is_authenticated(_auth_header()) is False
    assert server.is_authenticated(None) is False

    assert _recurrence_text({"type": "daily", "at": "06:00"}) == "Daily at 06:00"
    assert _recurrence_text({"type": "weekly", "days": ["mon", "wed"], "at": "07:00"}) == "Weekly mon, wed at 07:00"
    assert _recurrence_text({"type": "custom"}) == "custom"


def test_healthz_endpoint():
    """Health endpoint should be public and report basic runtime state."""
    server = WebInterfaceServer(password=_TEST_PASSWORD, public_schedules=False, action_engine=MagicMock())
    with patch("waterbot.web.server.scheduler.get_scheduler") as mock_get_scheduler:
        mock_get_scheduler.return_value = MagicMock(running=True)
        status, headers, data = _request(server, "GET", "/healthz")

    assert status == 200
    assert ("Content-Type", "application/json") in headers
    payload = json.loads(data)
    assert payload["status"] == "ok"
    assert payload["web"] is True
    assert payload["scheduler_running"] is True
