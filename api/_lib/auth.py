import json
import ssl
from urllib import error as urllib_error, request as urllib_request

from .runtime import ApiError, build_ssl_context, get_supabase_anon_key, get_supabase_url


def extract_bearer_token(auth_header):
    if not auth_header:
        raise ApiError("Missing Authorization header.", status=401, code="AUTH_MISSING")

    scheme, _, token = auth_header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise ApiError("Authorization header must be a Bearer token.", status=401, code="AUTH_INVALID")

    return token.strip()


def verify_access_token(token):
    request_url = f"{get_supabase_url()}/auth/v1/user"
    req = urllib_request.Request(
        request_url,
        headers={
            "apikey": get_supabase_anon_key(),
            "Authorization": f"Bearer {token}",
        },
        method="GET",
    )

    try:
        with urllib_request.urlopen(req, timeout=20, context=build_ssl_context()) as response:
            user = json.loads(response.read().decode("utf-8"))
    except urllib_error.HTTPError as exc:
        if exc.code in (401, 403):
            raise ApiError("Unauthorized request.", status=401, code="AUTH_INVALID") from exc
        details = exc.read().decode("utf-8", errors="ignore")
        raise ApiError(
            f"Supabase auth request failed ({exc.code}): {details or exc.reason}",
            status=502,
            code="AUTH_UPSTREAM_ERROR",
            retryable=exc.code >= 500,
        ) from exc
    except ssl.SSLCertVerificationError as exc:
        raise ApiError(
            "TLS verification failed while validating the Supabase session.",
            status=502,
            code="TLS_ERROR",
            retryable=True,
        ) from exc
    except urllib_error.URLError as exc:
        raise ApiError(
            f"Unable to reach Supabase Auth: {exc.reason}",
            status=502,
            code="AUTH_NETWORK_ERROR",
            retryable=True,
        ) from exc

    if not isinstance(user, dict) or not user.get("id"):
        raise ApiError("Supabase did not return a valid user.", status=401, code="AUTH_INVALID")

    return user


def require_user(auth_header):
    token = extract_bearer_token(auth_header)
    user = verify_access_token(token)
    return token, user

