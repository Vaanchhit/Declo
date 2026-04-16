from http.server import BaseHTTPRequestHandler

from api._lib.auth import require_user
from api._lib.http import method_not_allowed, send_empty, send_error, send_json
from api._lib.store import delete_workspace_state


class handler(BaseHTTPRequestHandler):
    def do_DELETE(self):
        try:
            token, user = require_user(self.headers.get("Authorization"))
            delete_workspace_state(token, user["id"])
            send_json(
                self,
                200,
                {
                    "success": True,
                    "message": "Workspace data deleted.",
                },
            )
        except Exception as exc:
            send_error(self, exc)

    def do_OPTIONS(self):
        send_empty(self)

    def do_GET(self):
        method_not_allowed(self, "DELETE")

