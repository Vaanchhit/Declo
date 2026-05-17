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

function buildGeminiError(message, status = 502) {
  const err = new Error(message);
  err.status = status;
  return err;
}

function extractCandidateText(data) {
  const candidates = Array.isArray(data?.candidates) ? data.candidates : [];
  if (!candidates.length) {
    const blockReason = data?.promptFeedback?.blockReason;
    if (blockReason) {
      throw buildGeminiError(`Gemini blocked the prompt: ${blockReason}`, 422);
    }
    throw buildGeminiError("Gemini returned no candidates");
  }

  const parts = Array.isArray(candidates[0]?.content?.parts) ? candidates[0].content.parts : [];
  const text = parts
    .map((part) => (typeof part?.text === "string" ? part.text : ""))
    .join("")
    .trim();

  if (!text) throw buildGeminiError("Gemini returned an empty response");
  return text;
}

function stripCodeFences(text) {
  return String(text || "")
    .trim()
    .replace(/^```(?:json)?\s*/i, "")
    .replace(/\s*```$/, "")
    .trim();
}

function extractBalancedJsonSnippet(text, openChar, closeChar) {
  const start = text.indexOf(openChar);
  if (start === -1) return "";

  let depth = 0;
  let inString = false;
  let escaped = false;

  for (let index = start; index < text.length; index += 1) {
    const char = text[index];

    if (inString) {
      if (escaped) {
        escaped = false;
      } else if (char === "\\") {
        escaped = true;
      } else if (char === "\"") {
        inString = false;
      }
      continue;
    }

    if (char === "\"") {
      inString = true;
      continue;
    }

    if (char === openChar) depth += 1;
    if (char === closeChar) {
      depth -= 1;
      if (depth === 0) return text.slice(start, index + 1);
    }
  }

  return "";
}

function looksLikeTrackerObject(value) {
  return !!value && typeof value === "object" && !Array.isArray(value) && (
    typeof value.name === "string" ||
    typeof value.type === "string" ||
    Array.isArray(value.fields) ||
    typeof value.frequency === "string"
  );
}

function coerceTrackerArray(value, currentTrackerCount = 0) {
  if (Array.isArray(value)) {
    return value.filter((tracker) => tracker && typeof tracker === "object" && !Array.isArray(tracker));
  }

  if (!value || typeof value !== "object") return null;

  if (Array.isArray(value.trackers)) {
    return value.trackers.filter((tracker) => tracker && typeof tracker === "object" && !Array.isArray(tracker));
  }

  for (const key of ["result", "data", "items", "output"]) {
    if (Array.isArray(value[key])) {
      return value[key].filter((tracker) => tracker && typeof tracker === "object" && !Array.isArray(tracker));
    }
  }

  if (currentTrackerCount === 0 && looksLikeTrackerObject(value)) {
    return [value];
  }

  return null;
}

function summarizeGeminiText(text) {
  return String(text || "")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 220);
}

function parseTrackersFromText(text, currentTrackerCount = 0) {
  const cleaned = stripCodeFences(text);
  const candidates = [cleaned];
  const arraySnippet = extractBalancedJsonSnippet(cleaned, "[", "]");
  const objectSnippet = extractBalancedJsonSnippet(cleaned, "{", "}");

  if (arraySnippet && arraySnippet !== cleaned) candidates.push(arraySnippet);
  if (objectSnippet && objectSnippet !== cleaned && objectSnippet !== arraySnippet) candidates.push(objectSnippet);

  for (const candidate of candidates) {
    if (!candidate) continue;
    try {
      let parsed = JSON.parse(candidate);
      if (typeof parsed === "string") {
        parsed = JSON.parse(parsed);
      }
      const trackers = coerceTrackerArray(parsed, currentTrackerCount);
      if (trackers) return trackers;
    } catch {
      // Try the next candidate shape.
    }
  }

  throw buildGeminiError(`Gemini did not return valid JSON array. Received: ${summarizeGeminiText(cleaned)}`);
}

async function requestGemini(payload, modelName, currentTrackerCount = 0) {
  const apiKey = requireEnv("GEMINI_API_KEY", "GOOGLE_API_KEY");
  const url = `https://generativelanguage.googleapis.com/v1beta/models/${modelName}:generateContent`;

  const res = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json", "x-goog-api-key": apiKey }, body: JSON.stringify(payload) });
  const data = await res.json();
  
  if (!res.ok) {
    throw buildGeminiError(data.error?.message || "Gemini API error");
  }

  const text = extractCandidateText(data);
  return parseTrackersFromText(text, currentTrackerCount);
}

export async function parseTrackersWithGemini(userInput, currentTrackers) {
  if (!userInput || !userInput.trim()) {
    const err = new Error("Missing prompt input.");
    err.status = 400;
    throw err;
  }

  const safeTrackers = Array.isArray(currentTrackers) ? currentTrackers : [];
  const payload = { contents: [{ parts: [{ text: buildParsePrompt(userInput.trim(), safeTrackers) }] }], generationConfig: { temperature: 0.2, responseMimeType: "application/json", responseSchema: buildResponseSchema(), maxOutputTokens: 700 } };
  const primaryModel = getEnv("GEMINI_PRIMARY_MODEL", "GEMINI_MODEL") || "gemini-2.5-flash";
  const fallbackModel = getEnv("GEMINI_FALLBACK_MODEL") || "gemini-2.0-flash";
  
  try {
    const trackers = await requestGemini(payload, primaryModel, safeTrackers.length);
    return { trackers, model: primaryModel, fallback_used: false };
  } catch (err) {
    if (!fallbackModel || primaryModel === fallbackModel || err.status !== 502) {
      throw err;
    }
    const trackers = await requestGemini(payload, fallbackModel, safeTrackers.length);
    return { trackers, model: fallbackModel, fallback_used: true };
  }
}
