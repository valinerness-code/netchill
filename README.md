# NETCHILL

A full-stack, streaming-site-style web app with real account sign-up and sign-in. It has a **Streamlit** frontend, a **Java** authentication API, and a **PostgreSQL** database. It ships as Docker images through a **GitHub Actions** pipeline and runs on **Render**.

**Live demo:** https://netchill-frontend.onrender.com

> The demo runs on free hosting, so it sleeps when idle. The first load after a quiet period can take up to a minute while the backend wakes up. Sign-up creates a real account in the demo database, so please use a throwaway password.

This is an independent portfolio project and is not affiliated with Netflix. There are no real payments or video streaming yet. The movie and TV cards, the profiles and the billing details on the Account page are placeholder demo content.

## What this project demonstrates

- **Backend engineering:** a dependency-light Java 25 HTTP API (the JDK's built-in server, no framework) with PostgreSQL and a Maven fat-JAR build.
- **Security basics done carefully:** salted PBKDF2 password hashing, rate limiting, input validation, parameterized SQL and secrets kept out of the code. Details are below.
- **DevOps:** two Docker images, a CI/CD pipeline that lints, builds, pushes and deploys on every push to `main`, and infrastructure described in `render.yaml`.
- **Debugging real hosting problems:** free-tier cold starts, port binding and proxy IP handling. Notes are below.

## Architecture

```
Browser ──> Streamlit frontend ──> Java auth API ──> PostgreSQL
            (Render, Docker)       (Render, Docker)   (Aiven)
```

```
git push to main
   └─> GitHub Actions: lint ─> build 2 Docker images ─> push to Docker Hub
         └─> Render deploy hooks ─> Render pulls the images tagged with the commit SHA
```

| Part | Technology |
|---|---|
| Frontend | Python 3.12, Streamlit 1.65.0, requests |
| Backend | Java 25, JDK `com.sun.net.httpserver`, PostgreSQL JDBC driver, Maven |
| Database | PostgreSQL on Aiven (free plan) |
| Packaging | Docker (multi-stage build for the backend) |
| CI/CD | GitHub Actions, Docker Hub |
| Hosting | Render (free web services, deployed from Docker Hub images) |

## Features

- Two-step sign-up (name and date of birth, then email and password) and sign-in, each in a dialog.
- Signed-in area with Browse, Profiles, Account and Help pages.
- No payment details are collected, at sign-up or anywhere else.

## API

The backend accepts form-encoded `POST` bodies and is designed to be called by the frontend.

| Endpoint | Purpose | Responses |
|---|---|---|
| `GET /` | Health check, returns `OK` | 200 |
| `POST /api/register` | Create an account | 201 created, 400 invalid input, 409 email already registered, 429 rate limited or busy, 500 database error |
| `POST /api/login` | Check credentials | 200 success, 401 wrong credentials, 429 rate limited or busy, 500 database error |

## Security design

| Area | What is implemented |
|---|---|
| Password storage | PBKDF2-HMAC-SHA256, 600,000 iterations, a random salt per user, and constant-time comparison. Older hashes (210,000 iterations) are upgraded the next time that user signs in. |
| Password policy | 8 to 128 characters. Passwords on a built-in common-password list, equal to the email address, or highly repetitive are rejected. |
| SQL | Every query is a prepared statement. |
| Login responses | One generic error for a wrong email or a wrong password. A dummy hash runs for unknown emails so response time does not reveal whether an account exists. |
| Rate limiting | 10 sign-ups per hour per IP. 5 failed sign-ins per 15 minutes per email, and 20 per 15 minutes per IP. 120 sign-in and sign-up attempts per minute across the whole API. |
| CPU protection | At most 2 password hashes run at once. Extra requests wait briefly, then get a "busy" response instead of freezing the small free server. |
| Client IP | The frontend forwards the visitor's IP together with a shared secret. The backend trusts it only if the secret matches, otherwise it uses `CF-Connecting-IP`, which Cloudflare sets. It never trusts `X-Forwarded-For`, which a client can forge. IPv6 addresses are grouped by `/64`. |
| Input | Email and name validation on both sides, and an 8 KB request body limit. |
| Output | User-supplied text is HTML-escaped before it is shown, and image URLs are checked against an allow-list pattern. |
| Secrets | Database URL, shared secret and API keys come from environment variables. Nothing sensitive is in the repository, and Render generates the shared secret. |
| Transport | The database connection requires TLS (`sslmode=require`). |
| Containers | Both images run as a non-root user. Frontend dependencies are pinned to exact versions, and `.dockerignore` files keep secrets out of the images. |

## Engineering notes

- **Free-tier cold starts.** Render's free services sleep when idle. Requests sent from the frontend's server to a sleeping backend returned an instant `502` and never woke it, while a request from a real browser did. The page now sends the visitor's own browser to the backend on load. The sign-in and sign-up dialogs also keep retrying, with a click-to-wake link as a fallback.
- **Startup order.** The backend opens its port first and prepares the database in a background retry loop. Render's port check passes even when the database is slow or briefly unreachable, and the API recovers on its own.
- **Rate limits behind proxies.** Behind Render and Cloudflare, the socket address is the proxy's. Limits are keyed on a trustworthy visitor IP so one visitor cannot use forged headers to dodge them, and unrelated visitors do not share one bucket.

## CI/CD

`.github/workflows/deploy.yml` runs on every push to `main`:

1. **Lint:** `py_compile` plus `ruff` for syntax errors and undefined names in `frontend/app.py`.
2. **Build and push:** builds the frontend and backend images, tags each with `latest` and the commit SHA, and pushes them to Docker Hub.
3. **Deploy:** calls the Render deploy hooks, pointing each service at the image tagged with that commit.

The workflow reads four repository secrets: `DOCKER_USERNAME`, `DOCKER_PASSWORD`, `RENDER_BACKEND_DEPLOY_HOOK` and `RENDER_FRONTEND_DEPLOY_HOOK`.

## Run it locally

You need Docker (or JDK 25 with Maven, and Python 3.12) and a PostgreSQL database that accepts TLS connections. The backend always connects with `sslmode=require`, so a free Aiven PostgreSQL service works well.

**Backend**

```bash
cd backend
docker build -t netchill-backend .
docker run --rm -p 8080:8080 \
  -e DATABASE_URL="postgres://USER:PASSWORD@HOST:PORT/DBNAME" \
  netchill-backend
```

It creates the `users` table on startup. Open http://localhost:8080/ and you should see `OK`.

**Frontend**

```bash
cd frontend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

The frontend talks to `http://localhost:8080` by default.

### Configuration

| Variable | Service | Default | Purpose |
|---|---|---|---|
| `DATABASE_URL` | backend | none, required | PostgreSQL connection URL. `PGHOST`, `PGUSER`, `PGPASSWORD`, `PGDATABASE` and `PGPORT` also work. |
| `PORT` | both | 8080 backend, 8501 frontend | Port to listen on. |
| `API_SHARED_SECRET` | both | none, optional | Lets the backend trust the visitor IP forwarded by the frontend. Must match on both. |
| `CLIENT_IP_HEADER` | backend | `CF-Connecting-IP` | Header carrying the visitor IP. Set to `none` to disable. |
| `HASH_CONCURRENCY` | backend | 2 | Maximum simultaneous password hashes. |
| `GLOBAL_AUTH_PER_MINUTE` | backend | 120 | API-wide cap on sign-in and sign-up attempts per minute. |
| `BACKEND_API_URL` | frontend | `http://localhost:8080` | Address of the backend. |
| `UNSPLASH_ACCESS_KEY` | frontend | none, optional | Enables the Unsplash background photos on the landing page. |
| `REQUEST_TIMEOUT` | frontend | 60 | Seconds to wait for the backend. |
| `WAKE_MAX_SECONDS` | frontend | 240 | How long to keep waiting for a sleeping backend. |

## Repository layout

```
.
├── .github/workflows/deploy.yml     CI/CD pipeline
├── render.yaml                      Render services and shared secret group
├── backend/
│   ├── Dockerfile
│   ├── pom.xml
│   └── src/main/java/AuthServer.java
└── frontend/
    ├── Dockerfile
    ├── requirements.txt
    └── app.py
```

## Known limitations and roadmap

**Current limitations**

- Sign-in state lives in the Streamlit session. There are no server-issued session tokens yet, because there are no protected API endpoints.
- Rate-limit counters are kept in memory, so they reset when the backend restarts or sleeps.
- Sign-up reveals whether an email is already registered, and there is no email verification.
- On the free plans, the backend sleeps when idle, and Aiven can power off a free database after a long period without activity.
- There are no automated tests in the pipeline yet.

**Planned**

- A real video catalog: files in Cloudflare R2, catalog rows in the Aiven PostgreSQL database, and keyword search with Zilliz, using PostgreSQL as the fallback search.
- Automated tests in the CI pipeline.
- Email verification and server-side sessions.
