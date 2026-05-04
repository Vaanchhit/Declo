# Declo

Build your own tracking system — from a single prompt.

---

## What is Declo?

Most habit trackers force you into pre-built templates.

Declo does the opposite.

Instead of choosing from fixed formats, you describe what you want to track — and Declo builds a complete, structured tracking system for you.

---

## Why Declo?

Traditional trackers:
- Same structure for everyone  
- Limited flexibility  
- Hard to adapt as needs evolve  

Declo:
- Fully customizable from natural language  
- Supports multiple tracker types (binary, numeric, timed)  
- Evolves with your needs  

You don’t adjust to the tracker.  
The tracker adjusts to you.

---

## How it works

1. Describe what you want to track  
   > "I want to track workouts, reading, and deep work"

2. Declo generates your system  
   - Workout → binary / weekly goal  
   - Reading → pages per day  
   - Deep work → timed sessions  

3. Start tracking immediately  

---

## Features

- Prompt-based system generation  
- Multiple tracker types:
  - Binary (yes/no)
  - Numeric (quantitative)
  - Timed sessions  
- Flexible structure (not fixed templates)  
- Clean, minimal interface  
- Persistent state storage  

---

## Tech Stack

- Frontend: HTML, CSS, JavaScript  
- Backend: Vercel Serverless Functions (Node.js)  
- Local dev server: Vercel CLI (`vercel dev`)  
- AI: Gemini 2.5 Flash (Primary), Gemini 2.0 Flash (Fallback)  
- Database: Supabase  

---

## Local Setup

```bash
git clone https://github.com/Vaanchhit/Declo.git
cd Declo
npm i -g vercel
vercel dev
```

This starts a lightweight local server on `http://127.0.0.1:5000` that mirrors the Vercel deployment route shape:

- `/` serves `index.html`
- `/api/config`
- `/api/parse`
- `/api/state`
- `/api/account`
