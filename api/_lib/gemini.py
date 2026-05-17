import json
import ssl
from urllib import error as urllib_error, request as urllib_request

from .runtime import (
    ApiError,
    build_ssl_context,
    get_gemini_api_key,
    get_gemini_fallback_model,
    get_gemini_primary_model,
)


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
- id: preserve the existing tracker id when updating an existing tracker, otherwise omit it
- name: short string
- type: one of "binary", "numeric", "session"
- category: one of "study", "diet", "exercise", "habits", "none"
- frequency: "daily" or "weekly"
- logging_mode: "simple" for binary, "quantity" for numeric, "time" for session
- unit: short string, empty string, or null
- goal: number or null
- increments: array of 0 to 3 positive numbers
- primary_action: short verb phrase
- optional_actions: array of up to 3 short strings
- fields: array of field objects with shape {{ "name": string, "type": "number" | "boolean" | "time", "unit": string | null }}

Tracker guidance:
- binary trackers usually use fields like [{{"name":"done","type":"boolean","unit":null}}]
- numeric trackers usually use one number field
- session trackers usually use [{{"name":"duration","type":"time","unit":"minutes"}}]
- weekly trackers should still keep the same general shape

Current trackers:
{current_json}

User instruction:
{user_input}
""".strip()


def build_response_schema():
    return {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "name": {"type": "string"},
                "type": {"type": "string"},
                "mode": {"type": "string"},
                "category": {"type": "string"},
                "logging_mode": {"type": "string"},
                "unit": {"type": ["string", "null"]},
                "goal": {"type": ["number", "null"]},
                "frequency": {"type": "string"},
                "increments": {
                    "type": "array",
                    "items": {"type": "number"},
                },
                "primary_action": {"type": "string"},
                "optional_actions": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "fields": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "type": {"type": "string"},
                            "unit": {"type": ["string", "null"]},
                        },
                        "required": ["name", "type", "unit"],
                    },
                },
            },
            "required": [
                "name",
                "type",
                "category",
                "logging_mode",
                "frequency",
                "increments",
                "primary_action",
                "optional_actions",
                "fields",
            ],
        },
    }


def strip_code_fences(text):
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else ""
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    return cleaned.strip()


def extract_balanced_json_snippet(text, open_char, close_char):
    start = text.find(open_char)
    if start == -1:
        return ""

    depth = 0
    in_string = False
    escaped = False

    for index in range(start, len(text)):
        char = text[index]

        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
            continue

        if char == open_char:
            depth += 1
        elif char == close_char:
            depth -= 1
            if depth == 0:
                return text[start : index + 1]

    return ""


def looks_like_tracker_object(value):
    return isinstance(value, dict) and any(
        isinstance(value.get(key), expected_type)
        for key, expected_type in (
            ("name", str),
            ("type", str),
            ("fields", list),
            ("frequency", str),
        )
    )


def coerce_tracker_array(value, current_tracker_count=0):
    if isinstance(value, list):
        return [tracker for tracker in value if isinstance(tracker, dict)]

    if not isinstance(value, dict):
        return None

    trackers = value.get("trackers")
    if isinstance(trackers, list):
        return [tracker for tracker in trackers if isinstance(tracker, dict)]

    for key in ("result", "data", "items", "output"):
        nested = value.get(key)
        if isinstance(nested, list):
            return [tracker for tracker in nested if isinstance(tracker, dict)]

    if current_tracker_count == 0 and looks_like_tracker_object(value):
        return [value]

    return None


def summarize_gemini_text(text):
    return " ".join(str(text or "").split())[:220]


def parse_trackers_text(text, current_tracker_count=0):
    cleaned = strip_code_fences(text)
    candidates = [cleaned]
    array_snippet = extract_balanced_json_snippet(cleaned, "[", "]")
    object_snippet = extract_balanced_json_snippet(cleaned, "{", "}")

    if array_snippet and array_snippet != cleaned:
        candidates.append(array_snippet)
    if object_snippet and object_snippet not in (cleaned, array_snippet):
        candidates.append(object_snippet)

    for candidate in candidates:
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, str):
                parsed = json.loads(parsed)
        except json.JSONDecodeError:
            continue

        trackers = coerce_tracker_array(parsed, current_tracker_count=current_tracker_count)
        if trackers is not None:
            return trackers

    raise ApiError(
        f"Gemini model did not return valid JSON array. Received: {summarize_gemini_text(cleaned)}",
        status=502,
        code="AI_INVALID_JSON",
        retryable=True,
    )


def extract_candidate_text(response_payload):
    candidates = response_payload.get("candidates") or []
    if not candidates:
        prompt_feedback = response_payload.get("promptFeedback") or {}
        block_reason = prompt_feedback.get("blockReason")
        if block_reason:
            raise ApiError(
                f"Gemini blocked the prompt: {block_reason}",
                status=422,
                code="AI_BLOCKED",
                retryable=False,
            )
        raise ApiError("Gemini returned no candidates.", status=502, code="AI_EMPTY", retryable=True)

    parts = candidates[0].get("content", {}).get("parts", [])
    text = "".join(part.get("text", "") for part in parts if isinstance(part, dict)).strip()
    if not text:
        raise ApiError("Gemini returned an empty response.", status=502, code="AI_EMPTY", retryable=True)
    return text


def build_payload(user_input, current_trackers):
    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": build_parse_prompt(
                            user_input=user_input.strip(),
                            current_trackers=current_trackers if isinstance(current_trackers, list) else [],
                        )
                    }
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json",
            "responseJsonSchema": build_response_schema(),
        },
    }
    return payload


def request_gemini(payload, model_name, current_tracker_count=0):
    req = urllib_request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": get_gemini_api_key(),
        },
        method="POST",
    )

    try:
        with urllib_request.urlopen(req, timeout=45, context=build_ssl_context()) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
    except urllib_error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="ignore")
        raise ApiError(
            f"Gemini API error from {model_name} ({exc.code}): {details or exc.reason}",
            status=502,
            code="AI_UPSTREAM_ERROR",
            retryable=exc.code >= 500,
        ) from exc
    except ssl.SSLCertVerificationError as exc:
        raise ApiError(
            f"TLS certificate verification failed while connecting to Gemini model {model_name}.",
            status=502,
            code="TLS_ERROR",
            retryable=True,
        ) from exc
    except urllib_error.URLError as exc:
        raise ApiError(
            f"Gemini request failed for {model_name}: {exc.reason}",
            status=502,
            code="AI_NETWORK_ERROR",
            retryable=True,
        ) from exc

    text = extract_candidate_text(response_payload)
    return parse_trackers_text(text, current_tracker_count=current_tracker_count)


def parse_trackers_with_gemini(user_input, current_trackers):
    if not user_input.strip():
        raise ApiError("Missing prompt input.", status=400, code="PROMPT_REQUIRED")

    safe_trackers = current_trackers if isinstance(current_trackers, list) else []
    payload = build_payload(user_input, safe_trackers)
    primary_model = get_gemini_primary_model()
    fallback_model = get_gemini_fallback_model()

    try:
        trackers = request_gemini(payload, primary_model, current_tracker_count=len(safe_trackers))
        return {
            "trackers": trackers,
            "model": primary_model,
            "fallback_used": False,
        }
    except ApiError as exc:
        if not exc.retryable or not fallback_model or fallback_model == primary_model:
            raise

    trackers = request_gemini(payload, fallback_model, current_tracker_count=len(safe_trackers))
    return {
        "trackers": trackers,
        "model": fallback_model,
        "fallback_used": True,
    }
