import os
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

from api._lib.auth import require_user
from api._lib.gemini import parse_trackers_with_gemini
from api._lib.runtime import ApiError, get_public_config
from api._lib.store import delete_workspace_state, get_workspace_state, save_workspace_state


BASE_DIR = Path(__file__).resolve().parent
app = Flask(__name__)


@app.errorhandler(ApiError)
def handle_api_error(exc):
    response = jsonify(
        {
            "error": {
                "code": exc.code,
                "message": exc.message,
                "retryable": exc.retryable,
            }
        }
    )
    response.status_code = exc.status
    return response


@app.errorhandler(Exception)
def handle_unexpected_error(_exc):
    response = jsonify(
        {
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "Unexpected server error.",
                "retryable": False,
            }
        }
    )
    response.status_code = 500
    return response


@app.route("/")
def serve_index():
    return send_from_directory(BASE_DIR, "index.html")


@app.route("/api/config", methods=["GET"])
def config_route():
    return jsonify(get_public_config())


@app.route("/api/parse", methods=["POST"])
def parse_route():
    token, user = require_user(request.headers.get("Authorization"))
    body = request.get_json(silent=True) or {}
    current_trackers = body.get("trackers") if isinstance(body.get("trackers"), list) else None
    if current_trackers is None:
        current_trackers = get_workspace_state(token, user["id"]).get("trackers", [])
    parsed = parse_trackers_with_gemini(body.get("input", ""), current_trackers)
    return jsonify(
        {
            "trackers": parsed["trackers"],
            "meta": {
                "source": "gemini",
                "model": parsed["model"],
                "fallback_used": parsed["fallback_used"],
            },
        }
    )


@app.route("/api/state", methods=["GET", "POST"])
def state_route():
    token, user = require_user(request.headers.get("Authorization"))
    if request.method == "GET":
        return jsonify(get_workspace_state(token, user["id"]))

    state = save_workspace_state(token, user["id"], request.get_json(silent=True) or {})
    return jsonify({"success": True, **state})


@app.route("/api/account", methods=["DELETE"])
def account_route():
    token, user = require_user(request.headers.get("Authorization"))
    delete_workspace_state(token, user["id"])
    return jsonify({"success": True, "message": "Workspace data deleted."})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "5000")), debug=True)
