import json
import os
import ssl
from pathlib import Path
from urllib import error, request as urllib_request

from flask import Flask, request, jsonify, send_from_directory

try:
    import certifi
except ImportError:
    certifi = None

app = Flask(__name__)
BASE_DIR = Path(__file__).resolve().parent
STORAGE_FILE = BASE_DIR / "storage.json"
ENV_FILES = [BASE_DIR / ".env", BASE_DIR / ".env.local"]
GEMINI_MODEL = "gemini-2.5-flash"


def load_env_files():
    for env_file in ENV_FILES:
        if not env_file.exists():
            continue
        for raw_line in env_file.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


load_env_files()


def load_storage():
    if not STORAGE_FILE.exists():
        return {}
    try:
        return json.loads(STORAGE_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_storage(storage):
    STORAGE_FILE.write_text(json.dumps(storage, indent=2), encoding="utf-8")


def empty_state():
    return {"trackers": [], "data": {}, "meta": {}}


def get_user_id():
    return request.headers.get("X-User-Id", "").strip()


def get_gemini_api_key():
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or ""


def build_ssl_context():
    if certifi is not None:
        return ssl.create_default_context(cafile=certifi.where())
    return ssl.create_default_context()


def build_parse_prompt(user_input, current_trackers):
    current_json = json.dumps(current_trackers, ensure_ascii=True, indent=2)
    return f"""
You convert habit-tracker instructions into the final tracker list for a productivity app.

Return only a JSON array. Do not include markdown, code fences, or explanations.

The array must represent the full final tracker list after applying the user's instruction to the current trackers.
If the user wants to add trackers, include them.
If the user wants to rename, modify, or remove trackers, update the array accordingly.
Preserve existing tracker ids when modifying an existing tracker.

Each tracker object should follow these rules:
- name: short string
- type: one of "binary", "numeric", "session"
- category: one of "study", "diet", "exercise", "habits", "none"
- frequency: "daily" or "weekly"
- logging_mode: "simple" for binary, "quantity" for numeric, "time" for session
- unit: short string, or empty string if none
- goal: number only when the user clearly asked for a target, otherwise omit it
- increments: array of 0 to 3 positive numbers
- primary_action: short verb phrase
- optional_actions: array of up to 3 short strings
- fields: array of field objects with shape {{ "name": string, "type": "number" | "boolean" | "time", "unit": string }}

Tracker guidance:
- binary trackers usually use fields like [{{"name":"done","type":"boolean","unit":""}}]
- numeric trackers usually use one number field
- session trackers usually use [{{"name":"duration","type":"time","unit":"minutes"}}]
- weekly trackers should still keep the same general shape

Current trackers:
{current_json}

User instruction:
{user_input}
""".strip()


def extract_candidate_text(response_payload):
    candidates = response_payload.get("candidates") or []
    if not candidates:
        prompt_feedback = response_payload.get("promptFeedback") or {}
        block_reason = prompt_feedback.get("blockReason")
        if block_reason:
            raise RuntimeError(f"Gemini blocked the prompt: {block_reason}")
        raise RuntimeError("Gemini returned no candidates.")

    parts = candidates[0].get("content", {}).get("parts", [])
    text_parts = [part.get("text", "") for part in parts if isinstance(part, dict)]
    text = "".join(text_parts).strip()
    if not text:
        raise RuntimeError("Gemini returned an empty response.")
    return text


def parse_json_array(text):
    parsed = json.loads(text)
    if not isinstance(parsed, list):
        raise RuntimeError("Gemini response was not a JSON array.")
    return [item for item in parsed if isinstance(item, dict)]


def parse_trackers_with_gemini(user_input, current_trackers):
    api_key = get_gemini_api_key()
    if not api_key:
        raise RuntimeError("Missing Gemini API key. Set GEMINI_API_KEY or GOOGLE_API_KEY.")

    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": build_parse_prompt(user_input, current_trackers),
                    }
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.2,
            "response_mime_type": "application/json",
            "response_schema": {
                "type": "ARRAY",
                "items": {
                    "type": "OBJECT",
                    "properties": {
                        "id": {"type": "STRING"},
                        "name": {"type": "STRING"},
                        "type": {"type": "STRING"},
                        "mode": {"type": "STRING"},
                        "category": {"type": "STRING"},
                        "logging_mode": {"type": "STRING"},
                        "unit": {"type": "STRING"},
                        "goal": {"type": "NUMBER"},
                        "frequency": {"type": "STRING"},
                        "increments": {
                            "type": "ARRAY",
                            "items": {"type": "NUMBER"},
                        },
                        "primary_action": {"type": "STRING"},
                        "optional_actions": {
                            "type": "ARRAY",
                            "items": {"type": "STRING"},
                        },
                        "fields": {
                            "type": "ARRAY",
                            "items": {
                                "type": "OBJECT",
                                "properties": {
                                    "name": {"type": "STRING"},
                                    "type": {"type": "STRING"},
                                    "unit": {"type": "STRING"},
                                },
                            },
                        },
                    },
                },
            },
        },
    }

    req = urllib_request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        },
        method="POST",
    )

    try:
        ssl_context = build_ssl_context()
        with urllib_request.urlopen(req, timeout=45, context=ssl_context) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Gemini API error ({exc.code}): {details or exc.reason}") from exc
    except ssl.SSLCertVerificationError as exc:
        raise RuntimeError(
            "TLS certificate verification failed while connecting to Gemini. "
            "Your Python trust store is misconfigured. Install/update CA certificates "
            "or install certifi and retry."
        ) from exc
    except error.URLError as exc:
        if isinstance(exc.reason, ssl.SSLCertVerificationError):
            raise RuntimeError(
                "TLS certificate verification failed while connecting to Gemini. "
                "Your Python trust store is misconfigured. Install/update CA certificates "
                "or install certifi and retry."
            ) from exc
        raise RuntimeError(f"Gemini request failed: {exc.reason}") from exc

    text = extract_candidate_text(response_payload)
    return parse_json_array(text)


@app.route("/")
def serve_index():
    return send_from_directory(BASE_DIR, "index.html")


@app.route('/api/parse', methods=['POST'])
def parse_trackers():
    data = request.get_json(silent=True) or {}
    user_input = (data.get("input") or "").strip()
    current_trackers = data.get("trackers", [])

    if not user_input:
        return jsonify({"error": "Missing prompt input."}), 400

    try:
        trackers = parse_trackers_with_gemini(user_input, current_trackers)
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 502

    return jsonify({"trackers": trackers}), 200

@app.route('/api/state', methods=['GET', 'POST'])
def handle_state():
    user_id = get_user_id()
    if not user_id:
        if request.method == 'GET':
            return jsonify(empty_state()), 200
        return jsonify({"error": "Missing X-User-Id header"}), 400

    storage = load_storage()
    if request.method == 'GET':
        return jsonify(storage.get(user_id, empty_state())), 200

    incoming_state = request.get_json(silent=True) or {}
    storage[user_id] = {
        "trackers": incoming_state.get("trackers", []),
        "data": incoming_state.get("data", {}),
        "meta": incoming_state.get("meta", {}),
    }
    save_storage(storage)
    return jsonify({"success": True}), 200


@app.route('/api/account', methods=['DELETE'])
def delete_account():
    user_id = get_user_id()
    if not user_id:
        return jsonify({"success": True}), 200

    storage = load_storage()
    if user_id in storage:
        storage.pop(user_id, None)
        save_storage(storage)
    return jsonify({"success": True}), 200

if __name__ == '__main__':
    app.run(port=5000, debug=True)
