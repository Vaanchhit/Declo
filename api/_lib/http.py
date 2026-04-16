import json

from .runtime import ApiError, parse_json_bytes


def read_json_body(handler):
    content_length = int(handler.headers.get("content-length", "0") or "0")
    raw = handler.rfile.read(content_length) if content_length > 0 else b""
    return parse_json_bytes(raw)


def send_json(handler, status, payload):
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def send_empty(handler, status=204):
    handler.send_response(status)
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()


def send_error(handler, exc):
    if isinstance(exc, ApiError):
        send_json(
            handler,
            exc.status,
            {
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "retryable": exc.retryable,
                }
            },
        )
        return

    send_json(
        handler,
        500,
        {
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "Unexpected server error.",
                "retryable": False,
            }
        },
    )


def method_not_allowed(handler, allowed):
    send_json(
        handler,
        405,
        {
            "error": {
                "code": "METHOD_NOT_ALLOWED",
                "message": f"Use one of: {allowed}.",
                "retryable": False,
            }
        },
    )

