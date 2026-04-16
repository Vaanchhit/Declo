from http.server import BaseHTTPRequestHandler

from api._lib.auth import require_user
from api._lib.gemini import parse_trackers_with_gemini
from api._lib.http import method_not_allowed, read_json_body, send_empty, send_error, send_json
from api._lib.store import get_workspace_state


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            token, user = require_user(self.headers.get("Authorization"))
            body = read_json_body(self)
            current_trackers = body.get("trackers") if isinstance(body.get("trackers"), list) else None
            if current_trackers is None:
                current_trackers = get_workspace_state(token, user["id"]).get("trackers", [])
            trackers = parse_trackers_with_gemini(body.get("input", ""), current_trackers)
            send_json(
                self,
                200,
                {
                    "trackers": trackers,
                    "meta": {
                        "source": "gemini",
                        "model": "server-configured",
                    },
                },
            )
        except Exception as exc:
            send_error(self, exc)

    def do_OPTIONS(self):
        send_empty(self)

    def do_GET(self):
        method_not_allowed(self, "POST")

