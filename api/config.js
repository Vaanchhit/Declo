import { getEnv } from "./_lib/runtime.js";

export default function handler(req, res) {
  if (req.method !== "GET") return res.status(405).json({ error: "Method not allowed" });

  const supabaseUrl = getEnv("SUPABASE_URL", "NEXT_PUBLIC_SUPABASE_URL");
  const supabaseAnonKey = getEnv("SUPABASE_ANON_KEY", "NEXT_PUBLIC_SUPABASE_ANON_KEY");

  res.status(200).json({
    supabaseUrl,
    supabaseAnonKey,
    configured: !!(supabaseUrl && supabaseAnonKey),
  });
}