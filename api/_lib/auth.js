import { requireEnv } from "./runtime.js";

export async function requireUser(req) {
  const authHeader = req.headers.authorization;
  if (!authHeader || !authHeader.toLowerCase().startsWith("bearer ")) {
    const err = new Error("Missing or invalid Authorization header.");
    err.status = 401;
    throw err;
  }
  
  const token = authHeader.split(" ")[1].trim();
  const supabaseUrl = requireEnv("SUPABASE_URL", "NEXT_PUBLIC_SUPABASE_URL");
  const anonKey = requireEnv("SUPABASE_ANON_KEY", "NEXT_PUBLIC_SUPABASE_ANON_KEY");

  const res = await fetch(`${supabaseUrl}/auth/v1/user`, {
    headers: {
      "apikey": anonKey,
      "Authorization": `Bearer ${token}`
    }
  });

  if (!res.ok) {
    const err = new Error("Unauthorized request.");
    err.status = 401;
    throw err;
  }

  return { token, user: await res.json() };
}