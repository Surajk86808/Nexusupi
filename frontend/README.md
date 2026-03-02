# Frontend (Standalone)

This folder contains a simple standalone frontend for the NexusAPI backend.

## Run

1. Start the API backend on `http://localhost:8000`.
2. Serve this folder with any static file server.

PowerShell example:

```powershell
cd frontend
python -m http.server 5500
```

Open: `http://localhost:5500`

## Usage

1. Click `Sign in with Google` to authenticate via backend OAuth.
2. Token is stored automatically after successful callback.
3. You can also paste a bearer token manually.
4. Use buttons for:
   - `GET /me`
   - `GET /credits/balance`
   - `POST /api/analyse`
   - `POST /api/summarise`
   - `GET /api/jobs/{job_id}`

If your API is on a different host/port, update the API Base URL field.

## Required backend OAuth env vars

Set these in backend `.env`:

```bash
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REDIRECT_URI=http://localhost:8000/auth/callback
FRONTEND_OAUTH_SUCCESS_URL=http://localhost:5500
CORS_ORIGINS=http://localhost:5500,http://127.0.0.1:5500
```
