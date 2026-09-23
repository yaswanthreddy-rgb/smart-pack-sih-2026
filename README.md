# Smart Pack — SIH Legal Metrology Compliance MVP

A deployable proof-of-concept for the packaged-commodity compliance problem statement:

**Image → PaddleOCR → Category detection → configurable LMPC checks → compliance score → human review flag → evidence → PDF report → inspection dashboard**

## What is included

- React + Vite frontend
- FastAPI backend
- PaddleOCR with English/Hindi/Tamil/Telugu options
- OpenCV preprocessing and OCR bounding-box evidence image
- Configurable declaration/rule checks
- Compliance score + LOW CONFIDENCE review path
- PostgreSQL in deployment; SQLite fallback for local development
- Inspection repository/history
- PDF compliance report
- Docker deployment
- Render Blueprint (`render.yaml`)
- Health endpoint
- JWT login endpoint and role field; demo mode keeps the hackathon demo frictionless

## Demo credentials

`inspector / Inspector@123`

The deployed demo defaults to `DEMO_MODE=true`, so the dashboard can be opened without a login. For a stricter deployment set `DEMO_MODE=false` and use the login endpoint from a custom login page or API client.

## Local Docker run

```bash
docker compose up --build
```

Open:

- http://localhost:8000
- http://localhost:8000/docs
- http://localhost:8000/health

## Local development without Docker

Backend:

```bash
cd backend
python -m venv .venv
# Windows PowerShell
.venv\\Scripts\\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

For local split frontend/backend development, create `frontend/.env`:

```env
VITE_API_URL=http://localhost:8000
```

## Render deployment — easiest single-URL deployment

This repository is intentionally structured as **one Docker web service + one PostgreSQL database**. The Docker image builds the React frontend and serves it from FastAPI, so you do not need a separate frontend host or CORS setup for the public demo.

1. Push this repository to GitHub.
2. In Render, create a **Blueprint** from the repository.
3. Render reads `render.yaml`.
4. Approve creation of:
   - `smart-pack-sih` web service
   - `smartpack-db` PostgreSQL database
5. Wait for the Docker build and deployment.
6. Open the generated `onrender.com` URL.
7. Test `/health` and then upload a real package image.

Render supports Docker services, managed PostgreSQL and Blueprint-based infrastructure. Free web services can be used for testing/demo purposes; free Postgres has a limited lifetime, so use a paid/persistent datastore for a longer-lived production system.

## Production hardening before a real enforcement deployment

This MVP is designed for a hackathon demonstration, not as a legal decision system. Before production use:

- Replace demo mode with mandatory authentication.
- Add proper role permissions for inspector/admin/auditor.
- Store images in durable object storage instead of the service filesystem.
- Add database migrations (Alembic).
- Add a versioned rule repository with effective dates.
- Validate every legal threshold against the current official rules/amendments.
- Add manual-review workflow and audit logs.
- Add rate limiting, antivirus/file validation and secure secret management.
- Add automated tests and CI/CD.

## Legal-rule design

The rule engine intentionally uses configurable checks and review flags rather than pretending OCR alone can make a legal determination. The Department of Consumer Affairs publishes the Legal Metrology (Packaged Commodities) Rules, 2011 and subsequent amendments; the application should be kept synchronized with the current applicable version.

Useful official sources:

- https://upload.indiacode.nic.in/showfile?actid=AC_CH_60_1205_00002_00002_1560405527490&filename=9_the_legal_metrology_%28package_commodities%29_rules%2C_2011.pdf&type=rule
- https://consumeraffairs.nic.in/legalmetrologyactsandrules/legal-metrology-packaged-commodities-amendment-rules-2023-2
- https://consumeraffairs.nic.in/latestnews/whats-new-0

## SIH demonstration script

1. Login/open dashboard.
2. Click **New Inspection**.
3. Select English/Hindi/Tamil/Telugu.
4. Capture or upload a packaged-product label.
5. Click **Analyze Product**.
6. Show OCR text and confidence.
7. Show extracted declarations.
8. Show PASS/REVIEW checks.
9. Show OCR bounding-box evidence.
10. Show compliance score.
11. Show low-confidence human-review path when declarations are missing.
12. Download the PDF report.
13. Open History and show the inspection repository.

## Important claim discipline

Do not present the output as a final legal verdict. Use the wording **"AI-assisted preliminary compliance assessment"** and **"requires human verification"** for uncertain results.
