# JobPilot

AI-powered job search workspace for bilingual early-career job seekers.

## What is included

- FastAPI backend scaffold with thin API routes, service layer, repository layer, and reusable importer utilities.
- PostgreSQL persistence through SQLAlchemy models and Alembic migrations.
- Excel importer that detects sheets, detects header rows, maps Chinese/English column aliases, validates rows, normalizes job types/dates, deduplicates with a source hash, and persists jobs.
- Next.js frontend scaffold with locale-based English and Simplified Chinese routing through `next-intl`.
- Minimal JobPilot UI using a white/off-white workspace, simple bordered cards, restrained status colours, and real module screens for the requested MVP workflow.

## Run locally

Install dependencies first:

```bash
npm install
cd backend
/Users/jilu/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m pip install -e .
```

Start the local PostgreSQL database used by this MVP:

```bash
test -d .postgres-data || /opt/miniconda3/bin/initdb -D .postgres-data
/opt/miniconda3/bin/pg_ctl -D .postgres-data -l .postgres-data/server.log -o "-p 54329 -k .postgres-data" start
/opt/miniconda3/bin/createdb -h 127.0.0.1 -p 54329 jobhunter
```

Run migrations:

```bash
cd backend
DATABASE_URL=postgresql+psycopg://127.0.0.1:54329/jobhunter \
  /Users/jilu/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m alembic upgrade head
```

Seed the coherent demo candidate, resume, experiences, jobs, shared applications, and Tencent interview questions:

```bash
cd backend
DATABASE_URL=postgresql+psycopg://127.0.0.1:54329/jobhunter \
PYTHONPATH=/Users/jilu/Desktop/JobHunter/backend \
  /Users/jilu/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m app.scripts.seed_demo_applications
```

Start the backend:

```bash
cd backend
DATABASE_URL=postgresql+psycopg://127.0.0.1:54329/jobhunter \
FRONTEND_ORIGIN=http://127.0.0.1:3001 \
  /Users/jilu/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Start the frontend:

```bash
npm --prefix frontend run dev -- --hostname 127.0.0.1 --port 3001
```

Open `http://127.0.0.1:3001/en/dashboard`.

## Import flow

The import screen defaults to one bundled sample workbook path:

`/Users/jilu/Desktop/JobHunter/sample-data/互联派名企校招2.xlsx`

The original folder name in the repository was `smaple-data`; `sample-data` is a local symlink so commands and UI can use the intended path. The importer itself does not depend on that folder name.

The main real-data flow is:

Excel file -> `POST /api/v1/jobs/import` preview -> `POST /api/v1/jobs/import` confirm -> PostgreSQL `jobs` and `job_imports` -> `GET /api/v1/jobs` -> frontend Jobs page.
