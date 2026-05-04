npm i -g vercelimport { requireUser } from "./_lib/auth.js";
import { deleteWorkspaceState } from "./_lib/store.js";

export default async function handler(req, res) {
  if (req.method !== "DELETE") return res.status(405).json({ error: "Method not allowed" });

  try {
    const { token, user } = await requireUser(req);
    await deleteWorkspaceState(token, user.id);
    res.status(200).json({ success: true, message: "Workspace data deleted." });
  } catch (err) {
    res.status(err.status || 500).json({ error: err.message });
  }
}