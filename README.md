# Declo

Declo is a single-page tracker app deployed on Vercel with:

- static frontend in `index.html`
- Python serverless functions in `api/`
- Supabase for auth and persisted user state
- Gemini for prompt-to-tracker parsing

## Environment Variables

Set these in Vercel Project Settings and locally in `.env.local`:

- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`
- `GEMINI_API_KEY`
- `GEMINI_PRIMARY_MODEL` optional, defaults to `gemini-2.5-flash`
- `GEMINI_FALLBACK_MODEL` optional, defaults to `gemini-1.5-pro-latest`

Use `.env.example` as the starting template.

## Supabase Setup

1. Create a Supabase project.
2. Enable Email auth in Supabase Auth.
3. Run the SQL in `supabase/schema.sql`.
4. Copy the project URL and anon key into your environment variables.

## Local Development

1. Install dependencies:
   `python3 -m pip install -r requirements.txt`
2. Add a `.env.local`.
3. Run the local development server:
   `python3 tracker.py`
4. Open `http://127.0.0.1:5000/`

## Vercel Deployment

1. Import the repository into Vercel.
2. Add the environment variables listed above.
3. Deploy. Vercel will serve `index.html` at `/` and Python functions from `/api/*`.

## API Surface

- `GET /api/config`
- `POST /api/parse`
- `GET /api/state`
- `POST /api/state`
- `DELETE /api/account` deletes the user's stored Declo workspace data
