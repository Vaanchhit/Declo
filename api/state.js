import { requireUser } from "./_lib/auth.js";
import { getWorkspaceState, saveWorkspaceState } from "./_lib/store.js";

export default async function handler(req, res) {
  try {
    const { token, user } = await requireUser(req);
    
    if (req.method === "GET") {
      const state = await getWorkspaceState(token, user.id);
      return res.status(200).json(state);
    }
    
    if (req.method === "POST") {
      const state = await saveWorkspaceState(token, user.id, req.body || {});
      return res.status(200).json({ success: true, ...state });
    }
    
    res.status(405).json({ error: "Method not allowed" });
  } catch (err) {
    res.status(err.status || 500).json({ error: err.message });
  }
}