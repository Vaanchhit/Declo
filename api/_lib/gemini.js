import { getEnv, requireEnv } from "./runtime.js";

function buildParsePrompt(userInput, currentTrackers) {
  const currentJson = JSON.stringify(currentTrackers, null, 2);
  return `You convert habit-tracker instructions into the final tracker list for a productivity app.

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
- fields: array of field objects with shape { "name": string, "type": "number" | "boolean" | "time", "unit": string | null }

Tracker guidance:
- binary trackers usually use fields like [{"name":"done","type":"boolean","unit":null}]
- numeric trackers usually use one number field
- session trackers usually use [{"name":"duration","type":"time","unit":"minutes"}]
- weekly trackers should still keep the same general shape

Current trackers:
${currentJson}

User instruction:
${userInput}`.trim();
}

function buildResponseSchema() {
  return {
    type: "ARRAY",
    items: {
      type: "OBJECT",
      properties: {
        id: { type: "STRING" },
        name: { type: "STRING" },
        type: { type: "STRING" },
        mode: { type: "STRING" },
        category: { type: "STRING" },
        logging_mode: { type: "STRING" },
        unit: { type: "STRING", nullable: true },
        goal: { type: "NUMBER", nullable: true },
        frequency: { type: "STRING" },
        increments: { type: "ARRAY", items: { type: "NUMBER" } },
        primary_action: { type: "STRING" },
        optional_actions: { type: "ARRAY", items: { type: "STRING" } },
        fields: {
          type: "ARRAY",
          items: {
            type: "OBJECT",
            properties: {
              name: { type: "STRING" },
              type: { type: "STRING" },
              unit: { type: "STRING", nullable: true }
            },
            required: ["name", "type"]
          }
        }
      },
      required: ["name", "type", "category", "logging_mode", "frequency", "increments", "primary_action", "optional_actions", "fields"]
    }
  };
}

async function requestGemini(payload, modelName) {
  const apiKey = requireEnv("GEMINI_API_KEY", "GOOGLE_API_KEY");
  const url = `https://generativelanguage.googleapis.com/v1beta/models/${modelName}:generateContent`;

  const res = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json", "x-goog-api-key": apiKey }, body: JSON.stringify(payload) });
  const data = await res.json();
  
  if (!res.ok) {
    const err = new Error(data.error?.message || "Gemini API error");
    err.status = 502;
    throw err;
  }
  
  const text = data.candidates?.[0]?.content?.parts?.map(p => p.text).join("").trim();
  if (!text) throw new Error("Gemini returned an empty response");
  
  try {
    const trackers = JSON.parse(text);
    if (!Array.isArray(trackers)) throw new Error();
    return trackers.filter(t => typeof t === "object" && t !== null);
  } catch (e) {
    throw new Error("Gemini did not return valid JSON array");
  }
}

export async function parseTrackersWithGemini(userInput, currentTrackers) {
  if (!userInput || !userInput.trim()) {
    const err = new Error("Missing prompt input.");
    err.status = 400;
    throw err;
  }

  const payload = { contents: [{ parts: [{ text: buildParsePrompt(userInput.trim(), Array.isArray(currentTrackers) ? currentTrackers : []) }] }], generationConfig: { temperature: 0.2, responseMimeType: "application/json", responseSchema: buildResponseSchema() } };
  const primaryModel = getEnv("GEMINI_PRIMARY_MODEL", "GEMINI_MODEL") || "gemini-2.5-flash";
  
  const trackers = await requestGemini(payload, primaryModel);
  return { trackers, model: primaryModel, fallback_used: false };
}