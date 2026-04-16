import json
import os
import ssl
from pathlib import Path

try:
    import certifi
except ImportError:
    certifi = None


BASE_DIR = Path(__file__).resolve().parents[2]
ENV_FILES = [
    BASE_DIR / ".env",
    BASE_DIR / ".env.local",
    BASE_DIR / ".env.production",
]


class ApiError(Exception):
    def __init__(self, message, status=400, code="BAD_REQUEST", retryable=False):
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code
        self.retryable = retryable


def load_env_files():
    for env_file in ENV_FILES:
        if not env_file.exists():
            continue
        for raw_line in env_file.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env_files()


def env_or_empty(*names):
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return ""


def require_env(*names):
    value = env_or_empty(*names)
    if not value:
        joined = ", ".join(names)
        raise ApiError(
            f"Missing required environment variable. Set one of: {joined}.",
            status=500,
            code="SERVER_MISCONFIGURED",
        )
    return value


def get_supabase_url():
    return require_env("SUPABASE_URL", "NEXT_PUBLIC_SUPABASE_URL")


def get_supabase_anon_key():
    return require_env("SUPABASE_ANON_KEY", "NEXT_PUBLIC_SUPABASE_ANON_KEY")


def get_gemini_api_key():
    return require_env("GEMINI_API_KEY", "GOOGLE_API_KEY")


def get_gemini_model():
    return env_or_empty("GEMINI_MODEL") or "gemini-1.5-flash"


def get_public_config():
    supabase_url = env_or_empty("SUPABASE_URL", "NEXT_PUBLIC_SUPABASE_URL")
    supabase_anon_key = env_or_empty("SUPABASE_ANON_KEY", "NEXT_PUBLIC_SUPABASE_ANON_KEY")
    return {
        "supabaseUrl": supabase_url,
        "supabaseAnonKey": supabase_anon_key,
        "configured": bool(supabase_url and supabase_anon_key),
    }


def build_ssl_context():
    if certifi is not None:
        return ssl.create_default_context(cafile=certifi.where())
    return ssl.create_default_context()


def parse_json_bytes(raw_bytes):
    if not raw_bytes:
        return {}
    try:
        return json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ApiError("Request body must be valid JSON.", status=400, code="INVALID_JSON") from exc
