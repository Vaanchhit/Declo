import { requireEnv } from "./runtime.js";

function getHeaders(token) {
  return {
    "apikey": requireEnv("SUPABASE_ANON_KEY", "NEXT_PUBLIC_SUPABASE_ANON_KEY"),
    "Authorization": `Bearer ${token}`,
    "Content-Type": "application/json"
  };
}

function getUrl() {
  return requireEnv("SUPABASE_URL", "NEXT_PUBLIC_SUPABASE_URL");
}

function normalizeState(state) {
  return {
    trackers: Array.isArray(state?.trackers) ? state.trackers : [],
    data: typeof state?.data === "object" && state.data !== null ? state.data : {},
    meta: typeof state?.meta === "object" && state.meta !== null ? state.meta : {},
  };
}

export async function getWorkspaceState(token, userId) {
  const url = `${getUrl()}/rest/v1/workspaces?select=trackers,data,meta&user_id=eq.${encodeURIComponent(userId)}&limit=1`;
  const res = await fetch(url, { headers: getHeaders(token) });
  
  if (!res.ok) {
    const err = new Error("Failed to fetch workspace state");
    err.status = res.status;
    throw err;
  }
  
  const rows = await res.json();
  return normalizeState(rows[0]);
}

export async function saveWorkspaceState(token, userId, state) {
  const url = `${getUrl()}/rest/v1/workspaces?on_conflict=user_id`;
  const payload = { user_id: userId, ...normalizeState(state) };
  
  const res = await fetch(url, {
    method: "POST",
    headers: { ...getHeaders(token), "Prefer": "resolution=merge-duplicates,return=representation" },
    body: JSON.stringify(payload)
  });
  
  if (!res.ok) {
    const err = new Error("Failed to save workspace state");
    err.status = res.status;
    throw err;
  }
  
  const rows = await res.json();
  return normalizeState(rows[0] || payload);
}

export async function deleteWorkspaceState(token, userId) {
  const url = `${getUrl()}/rest/v1/workspaces?user_id=eq.${encodeURIComponent(userId)}`;
  const res = await fetch(url, { method: "DELETE", headers: { ...getHeaders(token), "Prefer": "return=minimal" } });
  
  if (!res.ok) {
    const err = new Error("Failed to delete workspace data");
    err.status = res.status;
    throw err;
  }
}