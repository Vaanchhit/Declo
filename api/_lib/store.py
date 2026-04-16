import json
import ssl
from urllib import error as urllib_error, parse as urllib_parse, request as urllib_request

from .runtime import ApiError, build_ssl_context, get_supabase_anon_key, get_supabase_url


def empty_state():
    return {"trackers": [], "data": {}, "meta": {}}


def normalize_state_payload(payload):
    payload = payload if isinstance(payload, dict) else {}
    trackers = payload.get("trackers")
    data = payload.get("data")
    meta = payload.get("meta")
    return {
        "trackers": trackers if isinstance(trackers, list) else [],
        "data": data if isinstance(data, dict) else {},
        "meta": meta if isinstance(meta, dict) else {},
    }


def _supabase_rest_request(path, token, method="GET", body=None, extra_headers=None):
    url = f"{get_supabase_url()}/rest/v1{path}"
    headers = {
        "apikey": get_supabase_anon_key(),
        "Authorization": f"Bearer {token}",
    }
    if body is not None:
        headers["Content-Type"] = "application/json"
    if extra_headers:
        headers.update(extra_headers)

    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib_request.Request(url, data=data, headers=headers, method=method)

    try:
        with urllib_request.urlopen(req, timeout=20, context=build_ssl_context()) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else None
    except urllib_error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="ignore")
        if exc.code in (401, 403):
            raise ApiError("Unauthorized database request.", status=401, code="AUTH_INVALID") from exc
        raise ApiError(
            f"Supabase data request failed ({exc.code}): {details or exc.reason}",
            status=502,
            code="DB_UPSTREAM_ERROR",
            retryable=exc.code >= 500,
        ) from exc
    except ssl.SSLCertVerificationError as exc:
        raise ApiError(
            "TLS verification failed while connecting to Supabase.",
            status=502,
            code="TLS_ERROR",
            retryable=True,
        ) from exc
    except urllib_error.URLError as exc:
        raise ApiError(
            f"Unable to reach Supabase data API: {exc.reason}",
            status=502,
            code="DB_NETWORK_ERROR",
            retryable=True,
        ) from exc


def get_workspace_state(token, user_id):
    quoted_user_id = urllib_parse.quote(user_id, safe="-")
    rows = _supabase_rest_request(
        f"/workspaces?select=trackers,data,meta&user_id=eq.{quoted_user_id}&limit=1",
        token=token,
        method="GET",
    )
    if not rows:
        return empty_state()
    row = rows[0] if isinstance(rows, list) else rows
    return normalize_state_payload(row)


def save_workspace_state(token, user_id, state):
    normalized = normalize_state_payload(state)
    rows = _supabase_rest_request(
        "/workspaces?on_conflict=user_id",
        token=token,
        method="POST",
        body={
            "user_id": user_id,
            "trackers": normalized["trackers"],
            "data": normalized["data"],
            "meta": normalized["meta"],
        },
        extra_headers={"Prefer": "resolution=merge-duplicates,return=representation"},
    )
    if isinstance(rows, list) and rows:
        return normalize_state_payload(rows[0])
    return normalized


def delete_workspace_state(token, user_id):
    quoted_user_id = urllib_parse.quote(user_id, safe="-")
    _supabase_rest_request(
        f"/workspaces?user_id=eq.{quoted_user_id}",
        token=token,
        method="DELETE",
        extra_headers={"Prefer": "return=minimal"},
    )

