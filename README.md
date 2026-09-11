# Job Hunter

Job Hunter is a bilingual, AI-assisted job-search workspace for Chinese university students and early-career candidates pursuing internships and graduate roles.

It brings a fragmented workflow into one private workspace: users maintain job-search information and resumes, build their own job pool, compare resumes with job descriptions, track applications, retrieve evidence from an Experience Library, prepare grounded interview answers, and record interview outcomes.

## Product flow

```text
Import or add Job
  → Discovery Match
  → Deep Resume Match
  → Add and track Application
  → Build Experience Library
  → Prepare Interview question
  → Retrieve relevant Experiences
  → Explicitly select evidence
  → Generate grounded answer and feedback
  → Record and review the actual interview
```

The primary navigation is Dashboard, Job Discovery, Applications, Resumes, Resume Match, Experience Library, Interviews, and Settings. Legacy `/profile` and `/analytics` URLs redirect to their current destinations.

## Key features

- Supabase email/password authentication, shared Demo Mode, persisted browser sessions, automatic token refresh, and per-user ownership enforcement.
- Job Search Information with target roles, locations, job types, education, skills, tools, languages, and an independent AI response-language preference.
- Private PDF/DOCX resume upload through Supabase Storage, text extraction, structured skills and education detection, multiple resumes, and default-resume selection.
- Excel/CSV job import with sheet and header detection, Chinese/English aliases, explicit column mapping, persisted 30-minute previews, row review, deterministic deduplication, and nullable job roles.
- Server-paginated Job Discovery with keyword search, Chinese campus-recruitment metadata, deterministic match components, semantic-only confidence handling, and persisted Discovery Match results.
- Deep Resume Match with deterministic component scoring, persisted embeddings, grounded AI explanations, language-aware analysis reuse, and explicit unavailable-component handling.
- Application tracking across `saved`, `applied`, `oa`, `interview`, `final_interview`, `offer`, `rejected`, and `withdrawn`.
- Structured Experience CRUD, optional STAR fields, confirmed AI organization, fingerprinted embeddings, and pgvector retrieval.
- Interview questions from user input, confirmed pasted research, AI generation, and actual interview history; explicit Experience selection before personalized answer generation; grounded feedback and interview review.

## Screenshots

Portfolio screenshots are not committed yet. Recommended captures:

1. Dashboard with operational counts, recent applications, and next actions.
2. Job Discovery with campus metadata and Potential Match presentation.
3. Deep Resume Match with deterministic scores and grounded evidence.
4. Experience retrieval recommendations with relevance labels.
5. Interview Prep with a selected question, selected Experience, and generated answer.
6. Interview Review with linked company and role context.

## Architecture

```text
Next.js frontend
  → FastAPI REST API (/api/v1)
    → service layer
      → repositories
        → Supabase PostgreSQL + pgvector
        → private Supabase Storage
      → centralized AI service
        → OpenAI API
```

The frontend is Next.js 15, TypeScript, React, Tailwind CSS, `next-intl`, and Lucide icons. The backend uses FastAPI, Pydantic, SQLAlchemy, Alembic, psycopg, PyJWT, OpenAI, pypdf, python-docx, openpyxl, and pgvector.

## AI architecture and cost controls

OpenAI is used from the backend only for structured resume extraction, Experience organization, embeddings, grounded match explanations, interview questions, answers, and feedback. Pydantic validates structured outputs. AI does not directly write arbitrary records: resume-derived profile changes and organized Experience data require user confirmation, and personalized interview answers require explicit selection of a retrieved Experience.

Deterministic code handles validation, source fingerprints, component scores, availability/confidence rules, and reranking signals. pgvector supports semantic Experience retrieval.

The application does not call OpenAI during ordinary page rendering. AI work requires an explicit user action. Resume, Job, and Experience embeddings are reused while fingerprints match. Discovery Match results are cached by user, resume, job, source fingerprints, and scoring version. Deep Resume Match analyses and interview answer/feedback output are persisted and reused while their source identities remain current.

## Local setup

Prerequisites are Node.js, npm, Python 3.12 or newer, a Supabase project, and an OpenAI API key for AI-triggering workflows.

```bash
git clone <repository-url>
cd JobHunter
npm install

cd backend
python -m venv .venv
.venv/bin/python -m pip install -e .
cp ../.env.example .env

cd ../frontend
cp .env.example .env.local
cd ..
```

Configure Supabase Auth for email/password access. Create a private Storage bucket named `resumes`, or set `SUPABASE_RESUME_BUCKET` to another private bucket. The backend secret key must remain server-side.

Apply migrations:

```bash
cd backend
.venv/bin/python -m alembic upgrade head
```

Start the backend and frontend in separate terminals:

```bash
cd backend
.venv/bin/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

```bash
cd frontend
npm run dev -- --hostname 127.0.0.1 --port 3001
```

Open `http://127.0.0.1:3001`. The root route defaults to Simplified Chinese; English is available under `/en`.

If Next.js development artifacts become stale:

```bash
cd frontend
rm -rf .next
npm run dev
```

## Environment variables

Backend variables belong in `backend/.env`:

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | PostgreSQL SQLAlchemy connection URL |
| `FRONTEND_ORIGIN` | Single-origin compatibility setting for local development |
| `FRONTEND_ORIGINS` | Comma-separated exact CORS origins; use this in production |
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_PUBLISHABLE_KEY` | Supabase publishable key used for Auth requests |
| `SUPABASE_SECRET_KEY` | Backend-only `sb_secret_...` key for Storage administration |
| `SUPABASE_RESUME_BUCKET` | Private resume bucket name |
| `SUPABASE_JWT_SECRET` | JWT verification secret for projects using symmetric signing |
| `SUPABASE_JWT_AUDIENCE` | Expected JWT audience, normally `authenticated` |
| `OPENAI_API_KEY` | Backend-only OpenAI key |
| `OPENAI_MODEL` | Structured generation model |
| `OPENAI_EMBEDDING_MODEL` | Embedding model |
| `OPENAI_EMBEDDING_DIMENSION` | Must match the database vector dimensions |
| `EMBEDDING_MAX_CHARACTERS` | Maximum text sent for an embedding |
| `RESUME_UPLOAD_MAX_BYTES` | Backend resume upload limit |
| `DEMO_USER_EMAIL` | Configured shared Demo Supabase account |
| `DEMO_USER_PASSWORD` | Backend-only Demo account password |

Browser-safe variables belong in `frontend/.env.local`:

| Variable | Purpose |
| --- | --- |
| `NEXT_PUBLIC_API_BASE_URL` | Public FastAPI base URL |
| `NEXT_PUBLIC_SUPABASE_URL` | Public Supabase project URL |
| `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` | Browser-safe Supabase publishable key |

Never expose `SUPABASE_SECRET_KEY`, `OPENAI_API_KEY`, `DATABASE_URL`, `SUPABASE_JWT_SECRET`, or `DEMO_USER_PASSWORD` through `NEXT_PUBLIC_*` variables.

## Demo Mode

Demo Mode signs into one shared, persisted Supabase user and follows the same API and ownership paths as normal accounts. Changes can be visible to other visitors, and Demo data may be reset periodically. Do not upload sensitive personal information.

The canonical seed includes Job Search Information, a default resume, jobs, applications across several stages, Experiences, interview questions, and interview review history. Entering Demo Mode itself does not call OpenAI.

Reset Demo data manually:

```bash
cd backend
.venv/bin/python -m app.scripts.reset_demo
```

The reset resolves only `DEMO_USER_EMAIL` through Supabase authentication, deletes rows owned by that resolved UUID, limits Storage deletion to that UUID prefix, and reseeds canonical records. It does not accept an arbitrary user ID.

## Testing

Backend:

```bash
cd backend
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -p no:cacheprovider
```

Frontend regression checks and production build:

```bash
cd frontend
node --test tests/*.test.mjs
npm run build
```

Automated tests mock external AI calls and do not spend OpenAI credits.

## Security model

- FastAPI verifies Supabase JWT signature, expiration, issuer/audience configuration, and the authenticated subject.
- User ownership comes from verified JWT claims, never a body-provided `user_id`.
- User-owned list/detail/update/delete queries are scoped by authenticated UUID and use the established cross-user 404 behavior.
- Resume files use a private Storage bucket and UUID-prefixed object paths.
- OpenAI, Supabase secret, Demo password, and database credentials remain backend-only.
- Frontend sessions persist through navigation and refresh, refresh shortly before access-token expiry, synchronize across tabs, and retry one API request after a successful refresh.

This describes application controls, not a compliance certification.

## Deployment

The intended architecture is:

- Frontend: Vercel.
- Backend: a persistent FastAPI hosting provider selected separately.
- Database, Auth, and private Storage: Supabase.
- AI: OpenAI, called only by the backend.

Set `NEXT_PUBLIC_API_BASE_URL` to the deployed HTTPS backend and set `FRONTEND_ORIGINS` to the exact Vercel production and preview origins that should be allowed. Run `alembic upgrade head` as a controlled backend release step. The `/health` endpoint is suitable for a lightweight host health check and does not call the database or OpenAI.

Current deployment blockers are the unselected backend host and missing final production URLs. Production Supabase configuration, secrets, the private bucket, database migrations, and OpenAI quota must also be provisioned before launch.

## Brand assets

The temporary UI mark is centralized in `frontend/components/branding/BrandMark.tsx`. Approved logo files should follow `frontend/public/branding/README.md`; add the final square Next.js app icon at `frontend/app/icon.png`. Raster assets should retain their aspect ratio.

## MVP limitations

- No automatic applications, job-board scraping, Gmail integration, OCR, resume builder, browser extension, recruiter portal, or social features.
- No voice/video interview or real-time AI interviewer.
- Job search uses offset pagination and simple substring matching.
- Skill vocabulary and deterministic scoring are intentionally basic; semantic-score calibration may require later product validation.
- Jobs can intentionally omit a role, and limited job descriptions produce confidence-aware results rather than fabricated percentages.
- Demo reset is manual.
- Backend hosting has not been selected.

## Source of truth alignment

The implementation follows `JobHunter_MVP_v1_Codex_Source_of_Truth.docx` for product positioning, final navigation, Chinese-default localization, persistence, explicit AI confirmation and Experience selection, interview review, and frozen MVP exclusions. The historical `/profile` and `/analytics` routes remain as compatibility redirects, while Job Search Information lives on Resumes and Dashboard remains operational rather than becoming a separate Analytics product.
