import mimetypes
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from api._lib.auth import require_user
from api._lib.gemini import parse_trackers_with_gemini
from api._lib.http import method_not_allowed, read_json_body, send_empty, send_error, send_json
from api._lib.runtime import get_public_config
from api._lib.store import delete_workspace_state, get_workspace_state, save_workspace_state


BASE_DIR = Path(__file__).resolve().parent


class DecloHandler(BaseHTTPRequestHandler):
    server_version = "DecloDevServer/1.0"

    def do_GET(self):
        self._handle_request("GET")

    def do_POST(self):
        self._handle_request("POST")

    def do_DELETE(self):
        self._handle_request("DELETE")

    def do_OPTIONS(self):
        send_empty(self)

    def log_message(self, format, *args):
        return

    def _handle_request(self, method):
        path = urlparse(self.path).path

        if path.startswith("/api/"):
            self._handle_api(path, method)
            return

        if method != "GET":
            method_not_allowed(self, "GET")
            return

        self._serve_static(path)

    def _handle_api(self, path, method):
        try:
            if path == "/api/config":
                if method != "GET":
                    method_not_allowed(self, "GET")
                    return
                send_json(self, 200, get_public_config())
                return

            if path == "/api/parse":
                if method != "POST":
                    method_not_allowed(self, "POST")
                    return
                token, user = require_user(self.headers.get("Authorization"))
                body = read_json_body(self)
                current_trackers = body.get("trackers") if isinstance(body.get("trackers"), list) else None
                if current_trackers is None:
                    current_trackers = get_workspace_state(token, user["id"]).get("trackers", [])
                parsed = parse_trackers_with_gemini(body.get("input", ""), current_trackers)
                send_json(
                    self,
                    200,
                    {
                        "trackers": parsed["trackers"],
                        "meta": {
                            "source": "gemini",
                            "model": parsed["model"],
                            "fallback_used": parsed["fallback_used"],
                        },
                    },
                )
                return

            if path == "/api/state":
                token, user = require_user(self.headers.get("Authorization"))
                if method == "GET":
                    send_json(self, 200, get_workspace_state(token, user["id"]))
                    return
                if method == "POST":
                    state = save_workspace_state(token, user["id"], read_json_body(self))
                    send_json(self, 200, {"success": True, **state})
                    return
                method_not_allowed(self, "GET, POST")
                return

            if path == "/api/account":
                if method != "DELETE":
                    method_not_allowed(self, "DELETE")
                    return
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
                return

            send_json(
                self,
                404,
                {
                    "error": {
                        "code": "NOT_FOUND",
                        "message": "Route not found.",
                        "retryable": False,
                    }
                },
            )
        except Exception as exc:
            send_error(self, exc)

    def _serve_static(self, path):
        requested = "index.html" if path in {"", "/"} else path.lstrip("/")
        file_path = (BASE_DIR / requested).resolve()

        if not str(file_path).startswith(str(BASE_DIR)) or not file_path.is_file():
            send_json(
                self,
                404,
                {
                    "error": {
                        "code": "NOT_FOUND",
                        "message": "File not found.",
                        "retryable": False,
                    }
                },
            )
            return

        body = file_path.read_bytes()
        content_type, _ = mimetypes.guess_type(str(file_path))
        self.send_response(200)
        self.send_header("Content-Type", content_type or "application/octet-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def run():
    host = "127.0.0.1"
    port = int(os.environ.get("PORT", "5000"))
    server = ThreadingHTTPServer((host, port), DecloHandler)
    print(f"Declo dev server running at http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    run()
