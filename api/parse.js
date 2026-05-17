import { requireUser } from "./_lib/auth.js";
import { parseTrackersWithGemini } from "./_lib/gemini.js";
import { getWorkspaceState } from "./_lib/store.js";
import { ratelimit } from "./_lib/ratelimit.js";

export default async function handler(req, res) {
  if (req.method !== "POST") return res.status(405).json({ error: "Method not allowed" });

  try {
    const ip =
      req.headers["x-forwarded-for"] ||
      req.connection?.remoteAddress ||
      "anonymous";

    const { success } = await ratelimit.limit(ip);

    if (!success) {
      return res.status(429).json({
        error: "Too many requests. Please try again later.",
      });
    }

    const { token, user } = await requireUser(req);
    let { input = "", trackers } = req.body || {};

    if (!Array.isArray(trackers)) {
      const state = await getWorkspaceState(token, user.id);
      trackers = state.trackers || [];
    }

    res.status(200).json(await parseTrackersWithGemini(input, trackers));
  } catch (err) {
    res.status(err.status || 500).json({ error: err.message });
  }
}