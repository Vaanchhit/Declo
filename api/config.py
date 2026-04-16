from http.server import BaseHTTPRequestHandler

from api._lib.http import method_not_allowed, send_empty, send_error, send_json
from api._lib.runtime import get_public_config


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            send_json(self, 200, get_public_config())
        except Exception as exc:
            send_error(self, exc)

    def do_OPTIONS(self):
        send_empty(self)

    def do_POST(self):
        method_not_allowed(self, "GET")

