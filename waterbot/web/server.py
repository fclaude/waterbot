"""Small authenticated web interface for WaterBot."""

import asyncio
import base64
import json
import logging
import threading
import time
from html import escape
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from .. import policy as policy_model
from .. import scheduler
from ..actions import ActionEngine
from ..agent.routing import try_direct_command
from ..config import (
    WEB_AUTH_PASSWORD,
    WEB_AUTH_TOKEN,
    WEB_AUTH_USERNAME,
    WEB_HOST,
    WEB_PORT,
    WEB_PUBLIC_SCHEDULES,
    get_schedules,
    is_openai_configured,
)
from ..observability import record_latency
from ..openai_integration import process_with_openai
from ..services import get_action_engine, get_agent_memory
from ..utils.command_parser import parse_command

logger = logging.getLogger("waterbot.web")


class WebInterfaceServer:
    """Threaded HTTP server exposing schedules and authenticated chat."""

    def __init__(
        self,
        host: str = WEB_HOST,
        port: int = WEB_PORT,
        username: str = WEB_AUTH_USERNAME,
        password: Optional[str] = WEB_AUTH_PASSWORD,
        token: Optional[str] = WEB_AUTH_TOKEN,
        public_schedules: bool = WEB_PUBLIC_SCHEDULES,
        action_engine: Optional[ActionEngine] = None,
    ) -> None:
        """Initialize the web interface."""
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.token = token
        self.public_schedules = public_schedules
        self.action_engine = action_engine or get_action_engine()
        self.httpd: Optional[ThreadingHTTPServer] = None
        self.thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Start the web server in a background thread."""
        if self.httpd:
            return

        handler_cls = self._handler_class()
        self.httpd = ThreadingHTTPServer((self.host, self.port), handler_cls)
        self.thread = threading.Thread(target=self.httpd.serve_forever, name="waterbot-web", daemon=True)
        self.thread.start()
        logger.info("Web interface listening on http://%s:%s", self.host, self.server_port)

    def stop(self) -> None:
        """Stop the web server."""
        if not self.httpd:
            return
        self.httpd.shutdown()
        self.httpd.server_close()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=5)
        self.httpd = None
        self.thread = None

    @property
    def server_port(self) -> int:
        """Return the bound server port."""
        if not self.httpd:
            return self.port
        return int(self.httpd.server_address[1])

    def _handler_class(self) -> type[BaseHTTPRequestHandler]:
        app = self

        class WaterBotWebHandler(BaseHTTPRequestHandler):
            server_version = "WaterBotWeb/1.0"

            def log_message(self, format_str: str, *args: Any) -> None:
                logger.debug("web %s", format_str, *args)

            def do_GET(self) -> None:
                path = urlparse(self.path).path
                if path in {"/", "/schedules"}:
                    if app.public_schedules or app.is_authenticated(self.headers.get("Authorization")):
                        self._send_html(app.render_schedule_page())
                    else:
                        self._send_auth_required()
                    return

                if path == "/healthz":
                    self._send_json(app.health_snapshot())
                    return

                if path == "/chat":
                    if not app.is_authenticated(self.headers.get("Authorization")):
                        self._send_auth_required()
                        return
                    self._send_html(app.render_chat_page())
                    return

                if path == "/api/schedules":
                    if app.public_schedules or app.is_authenticated(self.headers.get("Authorization")):
                        self._send_json(app.schedule_snapshot())
                    else:
                        self._send_auth_required()
                    return

                if path == "/waterbot.png":
                    self._send_logo()
                    return

                self._send_error(HTTPStatus.NOT_FOUND, "Not found")

            def do_POST(self) -> None:
                path = urlparse(self.path).path
                if path == "/api/chat":
                    if not app.is_authenticated(self.headers.get("Authorization")):
                        self._send_auth_required()
                        return
                    payload = self._read_json_body()
                    message = str(payload.get("message", "")).strip()
                    if not message:
                        self._send_error(HTTPStatus.BAD_REQUEST, "message is required")
                        return
                    response = app.chat(message)
                    self._send_json({"response": response})
                    return

                self._send_error(HTTPStatus.NOT_FOUND, "Not found")

            def _read_json_body(self) -> Dict[str, Any]:
                content_length = min(int(self.headers.get("Content-Length", "0")), 16_384)
                raw_body = self.rfile.read(content_length).decode("utf-8")
                if not raw_body:
                    return {}
                try:
                    payload = json.loads(raw_body)
                except json.JSONDecodeError:
                    return {}
                return payload if isinstance(payload, dict) else {}

            def _send_html(self, body: str) -> None:
                encoded = body.encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            def _send_json(self, payload: Dict[str, Any]) -> None:
                encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            def _send_logo(self) -> None:
                logo_path = Path(__file__).resolve().parents[2] / "waterbot.png"
                if not logo_path.exists():
                    self._send_error(HTTPStatus.NOT_FOUND, "Logo not found")
                    return
                data = logo_path.read_bytes()
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _send_auth_required(self) -> None:
                body = b"Authentication required"
                self.send_response(HTTPStatus.UNAUTHORIZED)
                self.send_header("WWW-Authenticate", 'Basic realm="WaterBot"')
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _send_error(self, status: HTTPStatus, message: str) -> None:
                encoded = json.dumps({"error": message}).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

        return WaterBotWebHandler

    def is_authenticated(self, authorization: Optional[str]) -> bool:
        """Return True when an Authorization header matches configured auth."""
        if not authorization:
            return False

        if self.token and authorization == f"Bearer {self.token}":
            return True

        if not self.password or not authorization.startswith("Basic "):
            return False

        try:
            decoded = base64.b64decode(authorization.split(" ", 1)[1]).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            return False
        username, separator, password = decoded.partition(":")
        return bool(separator) and username == self.username and password == self.password

    def health_snapshot(self) -> Dict[str, Any]:
        """Return a lightweight health payload for probes."""
        scheduler_running = False
        try:
            scheduler_running = bool(getattr(scheduler.get_scheduler(), "running", False))
        except Exception:  # nosec B110
            scheduler_running = False

        return {
            "status": "ok",
            "web": True,
            "scheduler_running": scheduler_running,
            "openai_configured": is_openai_configured(),
        }

    def schedule_snapshot(self) -> Dict[str, Any]:
        """Return current legacy and flexible schedule state."""
        try:
            policies = scheduler.get_policy_schedules()
        except policy_model.PolicyValidationError as exc:
            policies = []
            policy_error: Optional[str] = str(exc)
        else:
            policy_error = None

        try:
            policy_next_runs = scheduler.get_next_policy_runs()
        except policy_model.PolicyValidationError as exc:
            policy_next_runs = []
            policy_error = policy_error or str(exc)

        return {
            "legacy_schedules": get_schedules(),
            "legacy_next_runs": scheduler.get_next_runs(),
            "policy_schedules": policies,
            "policy_next_runs": policy_next_runs,
            "policy_error": policy_error,
        }

    def chat(self, message: str) -> str:
        """Process an authenticated web chat message."""
        reply_start = time.monotonic()
        path = "direct_command"
        try:
            direct = try_direct_command(
                message,
                action_engine=self.action_engine,
                channel_id="web",
                source="web",
                author_name="Web",
                memory=get_agent_memory(),
            )
            if direct is not None:
                return direct

            if is_openai_configured():
                path = "agent"
                return asyncio.run(process_with_openai(message, "web", author_name="Web"))

            path = "fallback_parser"
            command_type, params = parse_command(message.lower())
            return self._execute_fallback_command(command_type, params)
        finally:
            record_latency("web_reply", time.monotonic() - reply_start, path=path)

    def _execute_fallback_command(self, command_type: Optional[str], params: Dict[str, Any]) -> str:
        """Execute parser commands when OpenAI is not configured."""
        if command_type == "confirm":
            return self.action_engine.confirm(params["token"], channel_id="web").message
        if command_type == "cancel":
            return self.action_engine.cancel(params["token"], channel_id="web").message
        if command_type == "help":
            return (
                "Try status, schedules, cycles, schedule <device> <on|off> <HH:MM>, "
                "cycle <device> every <N> days at <HH:MM> for <minutes> minutes, "
                "why <device>, feedback <device> <note>, confirm <token>, or cancel <token>."
            )
        if command_type == "error":
            return str(params["message"])

        result = self.action_engine.execute_action(
            command_type or "help",
            params,
            source="web",
            channel_id="web",
            require_confirmation=False,
        )
        return result.message

    def render_schedule_page(self) -> str:
        """Render the public schedule dashboard."""
        snapshot = self.schedule_snapshot()
        legacy_html = _legacy_schedule_rows(snapshot["legacy_schedules"])
        policy_html = _policy_rows(snapshot["policy_schedules"])
        next_html = _next_run_rows(snapshot["legacy_next_runs"], snapshot["policy_next_runs"])
        policy_error = snapshot["policy_error"]
        error_html = f'<p class="notice error">{escape(policy_error)}</p>' if policy_error else ""
        return _page(
            "Schedules",
            f"""
            <section class="hero">
              <img src="/waterbot.png" alt="" class="logo">
              <div>
                <h1>WaterBot Schedules</h1>
                <p>Current daily schedules, flexible cycles, and upcoming runs.</p>
              </div>
              <a class="button" href="/chat">Open Chat</a>
            </section>
            {error_html}
            <section class="band">
              <div class="section-title">
                <h2>Daily Schedules</h2>
                <span>{len(snapshot["legacy_schedules"])} devices</span>
              </div>
              <table>
                <thead><tr><th>Device</th><th>Action</th><th>Times</th></tr></thead>
                <tbody>{legacy_html}</tbody>
              </table>
            </section>
            <section class="band">
              <div class="section-title">
                <h2>Flexible Cycles</h2>
                <span>{len(snapshot["policy_schedules"])} policies</span>
              </div>
              <table>
                <thead><tr><th>Policy</th><th>Device</th><th>Recurrence</th><th>Duration</th></tr></thead>
                <tbody>{policy_html}</tbody>
              </table>
            </section>
            <section class="band">
              <div class="section-title">
                <h2>Upcoming Runs</h2>
                <span>next scheduled actions</span>
              </div>
              <table>
                <thead><tr><th>Type</th><th>Device</th><th>Action</th><th>When</th></tr></thead>
                <tbody>{next_html}</tbody>
              </table>
            </section>
            """,
        )

    def render_chat_page(self) -> str:
        """Render the authenticated chat interface."""
        return _page(
            "Chat",
            """
            <section class="hero">
              <img src="/waterbot.png" alt="" class="logo">
              <div>
                <h1>WaterBot Chat</h1>
                <p>Change schedules, ask why a policy ran, or record watering feedback.</p>
              </div>
              <a class="button subtle" href="/">Schedules</a>
            </section>
            <section class="chat-shell">
              <div id="messages" class="messages" aria-live="polite"></div>
              <form id="chat-form" class="composer">
                <input id="message" name="message" autocomplete="off" placeholder="Ask WaterBot..." required>
                <button type="submit">Send</button>
              </form>
            </section>
            <script>
              const messages = document.getElementById("messages");
              const form = document.getElementById("chat-form");
              const input = document.getElementById("message");
              function escapeHtml(text) {
                const div = document.createElement("div");
                div.textContent = text;
                return div.innerHTML;
              }
              function renderMarkdown(text) {
                const lines = escapeHtml(text).split("\\n");
                let html = "";
                let inList = false;
                const inline = (s) => s
                  .replace(/`([^`]+)`/g, "<code>$1</code>")
                  .replace(/\\*\\*([^*]+)\\*\\*/g, "<strong>$1</strong>")
                  .replace(/(^|[^*])\\*([^*]+)\\*/g, "$1<em>$2</em>");
                for (const line of lines) {
                  const bullet = line.match(/^\\s*[-*]\\s+(.*)/);
                  if (bullet) {
                    if (!inList) { html += "<ul>"; inList = true; }
                    html += "<li>" + inline(bullet[1]) + "</li>";
                    continue;
                  }
                  if (inList) { html += "</ul>"; inList = false; }
                  if (line.trim() === "") { html += "<br>"; continue; }
                  html += "<p>" + inline(line) + "</p>";
                }
                if (inList) html += "</ul>";
                return html;
              }
              function add(role, text) {
                const item = document.createElement("div");
                item.className = "message " + role;
                if (role === "bot") {
                  item.innerHTML = renderMarkdown(text);
                } else {
                  item.textContent = text;
                }
                messages.appendChild(item);
                messages.scrollTop = messages.scrollHeight;
              }
              add("bot", "Connected. Authenticated chat is ready.");
              form.addEventListener("submit", async (event) => {
                event.preventDefault();
                const text = input.value.trim();
                if (!text) return;
                input.value = "";
                add("user", text);
                const response = await fetch("/api/chat", {
                  method: "POST",
                  headers: {"Content-Type": "application/json"},
                  body: JSON.stringify({message: text})
                });
                const payload = await response.json();
                add("bot", payload.response || payload.error || "No response");
              });
            </script>
            """,
        )


def _legacy_schedule_rows(schedules: Dict[str, Any]) -> str:
    if not schedules:
        return '<tr><td colspan="3" class="empty">No daily schedules configured</td></tr>'
    rows = []
    for device, actions in sorted(schedules.items()):
        entries = [(entry_time, action) for action, times in actions.items() for entry_time in times]
        for entry_time, action in sorted(entries):
            rows.append(
                "<tr>"
                f"<td>{escape(str(device))}</td>"
                f"<td><span class='pill'>{escape(str(action).upper())}</span></td>"
                f"<td>{escape(str(entry_time))}</td>"
                "</tr>"
            )
    return "".join(rows)


def _policy_rows(policies: list[Dict[str, Any]]) -> str:
    if not policies:
        return '<tr><td colspan="4" class="empty">No flexible cycles configured</td></tr>'
    rows = []
    for policy in policies:
        recurrence = policy.get("recurrence", {})
        duration = policy.get("duration", {})
        rec_text = _recurrence_text(recurrence)
        duration_text = (
            f"{duration.get('base_minutes', '?')} min "
            f"({duration.get('min_minutes', '?')}-{duration.get('max_minutes', '?')})"
        )
        rows.append(
            "<tr>"
            f"<td>{escape(str(policy.get('id', '')))}</td>"
            f"<td>{escape(str(policy.get('device', '')))}</td>"
            f"<td>{escape(rec_text)}</td>"
            f"<td>{escape(duration_text)}</td>"
            "</tr>"
        )
    return "".join(rows)


def _next_run_rows(legacy_runs: list[Dict[str, Any]], policy_runs: list[Dict[str, Any]]) -> str:
    rows = []
    for run in legacy_runs[:8]:
        rows.append(
            "<tr>"
            "<td>daily</td>"
            f"<td>{escape(str(run.get('device', '')))}</td>"
            f"<td>{escape(str(run.get('action', '')))}</td>"
            f"<td>{escape(str(run.get('next_run', run.get('time', ''))))}</td>"
            "</tr>"
        )
    for run in policy_runs[:8]:
        rows.append(
            "<tr>"
            "<td>flexible</td>"
            f"<td>{escape(str(run.get('device', '')))}</td>"
            f"<td>{escape(str(run.get('id', 'policy')))}</td>"
            f"<td>{escape(str(run.get('next_run', '')))}</td>"
            "</tr>"
        )
    if not rows:
        return '<tr><td colspan="4" class="empty">No upcoming runs available</td></tr>'
    return "".join(rows)


def _recurrence_text(recurrence: Dict[str, Any]) -> str:
    recurrence_type = recurrence.get("type", "unknown")
    if recurrence_type == "every_n_days":
        return f"Every {recurrence.get('every')} days at {recurrence.get('at')}"
    if recurrence_type == "daily":
        return f"Daily at {recurrence.get('at')}"
    if recurrence_type == "weekly":
        days = ", ".join(recurrence.get("days", []))
        return f"Weekly {days} at {recurrence.get('at')}"
    return str(recurrence_type)


def _page(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>WaterBot {escape(title)}</title>
  <style>
    :root {{
      color-scheme: light;
      --ink: #17201c;
      --muted: #5f6d66;
      --line: #d9e1dc;
      --field: #f5f8f6;
      --accent: #12685f;
      --accent-2: #9b5a1a;
      --surface: #ffffff;
      --soft: #eef5f1;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--ink);
      background: linear-gradient(180deg, #f7faf8 0, #edf4f0 100%);
    }}
    main {{ max-width: 1120px; margin: 0 auto; padding: 28px 18px 44px; }}
    .hero {{
      min-height: 148px;
      display: grid;
      grid-template-columns: 88px minmax(0, 1fr) auto;
      gap: 18px;
      align-items: center;
      border-bottom: 1px solid var(--line);
      margin-bottom: 22px;
    }}
    .logo {{ width: 76px; height: 76px; object-fit: contain; }}
    h1 {{ margin: 0; font-size: 2rem; line-height: 1.1; letter-spacing: 0; }}
    h2 {{ margin: 0; font-size: 1.05rem; letter-spacing: 0; }}
    p {{ margin: 8px 0 0; color: var(--muted); }}
    .button, button {{
      background: var(--accent);
      color: white;
      border: 0;
      border-radius: 6px;
      padding: 10px 14px;
      font-weight: 700;
      text-decoration: none;
      cursor: pointer;
      white-space: nowrap;
    }}
    .button.subtle {{ background: var(--ink); }}
    .band {{
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 8px;
      margin: 16px 0;
      overflow: hidden;
    }}
    .section-title {{
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: baseline;
      padding: 14px 16px;
      border-bottom: 1px solid var(--line);
      background: var(--soft);
    }}
    .section-title span {{ color: var(--muted); font-size: .9rem; }}
    table {{ width: 100%; border-collapse: collapse; table-layout: fixed; }}
    th, td {{ text-align: left; padding: 12px 16px; border-bottom: 1px solid var(--line); vertical-align: top; }}
    th {{ font-size: .78rem; text-transform: uppercase; color: var(--muted); }}
    td {{ overflow-wrap: anywhere; }}
    tr:last-child td {{ border-bottom: 0; }}
    .pill {{ display: inline-block; color: var(--accent); font-weight: 800; }}
    .empty {{ color: var(--muted); text-align: center; }}
    .notice {{ padding: 12px 14px; border-radius: 6px; background: #fff7ed; color: var(--accent-2); }}
    .chat-shell {{ min-height: 62vh; display: grid; grid-template-rows: 1fr auto; gap: 12px; }}
    .messages {{
      min-height: 360px;
      max-height: 62vh;
      overflow: auto;
      padding: 14px;
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 8px;
    }}
    .message {{
      width: fit-content;
      max-width: min(760px, 92%);
      margin: 8px 0;
      padding: 10px 12px;
      border-radius: 8px;
      overflow-wrap: anywhere;
      line-height: 1.4;
    }}
    .message.user {{ margin-left: auto; background: var(--accent); color: white; white-space: pre-wrap; }}
    .message.bot {{ background: var(--field); border: 1px solid var(--line); }}
    .message.bot p {{ margin: 0 0 8px; }}
    .message.bot p:last-child {{ margin-bottom: 0; }}
    .message.bot ul {{ margin: 0 0 8px; padding-left: 20px; }}
    .message.bot ul:last-child {{ margin-bottom: 0; }}
    .message.bot li {{ margin: 2px 0; }}
    .message.bot code {{
      background: rgba(0, 0, 0, 0.08);
      border-radius: 4px;
      padding: 1px 5px;
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 0.92em;
    }}
    .composer {{ display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 10px; }}
    input {{
      min-height: 44px;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 0 12px;
      font: inherit;
      background: white;
    }}
    @media (max-width: 700px) {{
      .hero {{ grid-template-columns: 60px minmax(0, 1fr); }}
      .hero .button {{ grid-column: 1 / -1; width: max-content; }}
      .logo {{ width: 54px; height: 54px; }}
      h1 {{ font-size: 1.55rem; }}
      table {{ table-layout: auto; }}
      th, td {{ padding: 10px; }}
      .composer {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <main>{body}</main>
</body>
</html>"""
