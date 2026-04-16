from http.server import BaseHTTPRequestHandler

from api._lib.auth import require_user
from api._lib.http import method_not_allowed, read_json_body, send_empty, send_error, send_json
from api._lib.store import get_workspace_state, save_workspace_state


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            token, user = require_user(self.headers.get("Authorization"))
            state = get_workspace_state(token, user["id"])
            send_json(self, 200, state)
        except Exception as exc:
            send_error(self, exc)

    def do_POST(self):
        try:
            token, user = require_user(self.headers.get("Authorization"))
            state = save_workspace_state(token, user["id"], read_json_body(self))
            send_json(self, 200, {"success": True, **state})
        except Exception as exc:
            send_error(self, exc)

    def do_OPTIONS(self):
        send_empty(self)

    def do_DELETE(self):
        method_not_allowed(self, "GET, POST")

