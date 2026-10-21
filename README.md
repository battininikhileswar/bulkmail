# AI Email Assistant

A reliable, light, and secure personalized email dispatch system with background reply watching and human-in-the-loop AI draft assistance.

---

## 1. Windows Setup & Installation

### Prerequisites
- Python 3.10+ (with pip)
- Node.js 18+ (with npm)

### Backend Setup
Open PowerShell in the project directory:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Frontend Setup
Open a separate PowerShell window:

```powershell
cd frontend
npm install
```

---

## 2. Google OAuth & Gmail API Setup

1. Open [Google Cloud Console](https://console.cloud.google.com/) and create or select a project.
2. Enable the **Gmail API** under *APIs & Services > Library*.
3. Configure the **OAuth Consent Screen** (*APIs & Services > OAuth consent screen*):
   - Choose **External** (for personal Gmail) or **Internal** (for Google Workspace).
   - Add scopes: `https://www.googleapis.com/auth/gmail.send`, `https://www.googleapis.com/auth/gmail.readonly`, `openid`, `email`, `profile`.
   - Add your test Google accounts under *Test users* if the publishing status is Testing.
4. Go to *APIs & Services > Credentials*, click **Create Credentials > OAuth client ID**.
5. Set Application type to **Web application**.
6. Under **Authorized redirect URIs**, add:
   - `http://localhost:8000/api/auth/callback`
7. Click **Create**, download the credentials JSON file, rename it to `credentials.json`, and place it in the `backend/` folder (`backend/credentials.json`).
8. Add a random `SESSION_SECRET` to your `backend/.env` file:
   ```env
   SESSION_SECRET="your_strong_random_secret_here"
   ```
9. When you open `http://localhost:5173`, click **Sign in with Google** to authenticate. Scopes granted will allow the assistant to send emails and read incoming replies on your behalf. Individual user tokens are securely stored in `backend/tokens/`.

---

## 3. Environment Variables (`.env`)

Create a `.env` file in the `backend/` folder (or copy from sample):

```env
# Email Dispatch Settings
EMAIL_PROVIDER=gmail              # 'gmail' or 'smtp'
SENDER_NAME="Event Coordinator"
TONE="friendly and professional"
PAUSE_SECONDS=5

# Safety & Mode
TEST_MODE=true                    # 'true' for test mode; 'false' for LIVE sending
TEST_EMAIL=test@example.com       # Address that receives all test outputs

# Daily Caps
GMAIL_DAILY_CAP=400
SMTP_DAILY_CAP=2000

# SMTP Configuration (if EMAIL_PROVIDER=smtp)
SMTP_HOST=
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
SMTP_USE_TLS=true

# AI Assistant Settings
ANTHROPIC_API_KEY=your_anthropic_api_key_here
AI_MODEL=claude-haiku-5-5
RESPONDER_MODEL=claude-sonnet-5-5

# Polling Interval
WATCHER_POLL_INTERVAL=10
```

---

## 4. Running the Servers

### Run Backend
```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m uvicorn main:app --app-dir . --reload --port 8000
```
Backend API runs locally at: `http://localhost:8000` (docs at `http://localhost:8000/docs`).

### Run Frontend
```powershell
cd frontend
npm run dev
```
Open your browser at: `http://localhost:5173`.

---

## 5. Test Mode vs. LIVE Mode

| Feature | Test Mode (`TEST_MODE=true`) | LIVE Mode (`TEST_MODE=false`) |
| :--- | :--- | :--- |
| **Top Bar Badge** | Amber `TEST MODE` | Red `LIVE MODE` |
| **Reply Sends** | Diverted strictly to `TEST_EMAIL` with `[TEST]` in subject | Sent directly to the actual contact's email address |
| **Daily Send Cap** | Does NOT count toward or increment daily send quotas | Increments daily provider count toward cap |
| **Campaign Test** | "Send Test" sends up to 3 samples to `TEST_EMAIL` | Real dispatches send to recipients sequentially |

---

## 6. Troubleshooting

- **Gmail authorization expired or revoked:**
  The top bar displays: `⚠️ Gmail needs to be reconnected` and automatically pauses all sending. Delete `backend/token.json` and restart the backend to authenticate again.
- **Interrupted / stranded contacts on restart:**
  Contacts in `sending` or drafts in `approved` during an unexpected shutdown are marked `Needs review` on the Dashboard and are never re-sent automatically.
- **Port 8000 or 5173 already in use:**
  Run `Get-NetTCPConnection -LocalPort 8000, 5173` in PowerShell to find the PID, or kill existing background processes.
- **Temporary delivery errors:**
  Temporary errors (network drop, 503, rate limit) automatically retry up to 3 times (30s, 2m, 10m). Permanent errors fail immediately with reasons recorded in the Activity log.
