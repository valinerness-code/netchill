# NETCHILL

A full-stack, streaming-site-style web app with real account sign-up and sign-in and a media catalog. It has a **Streamlit** frontend, a **Java** authentication API, a **PostgreSQL** database for accounts, and a **Cloudflare Worker** that serves the catalog (D1) and the posters and videos (R2). It ships as Docker images through a **GitHub Actions** pipeline and runs on **Render**.

**Live demo:** https://netchill-frontend.onrender.com

> The demo runs on free hosting, so it sleeps when idle. The first load after a quiet period can take up to a minute while the backend wakes up. Sign-up creates a real account in the demo database, so please use a throwaway password.

This is an independent portfolio project and is not affiliated with Netflix. Payments are not implemented: the plans, profiles and billing details on the Account page are placeholder demo content. The catalog and player show whatever media is uploaded to the storage bucket.

## About the demo videos

The videos in the demo catalog are **trailers** only, not full movies or episodes, obtained from [archive.org](https://archive.org/). The trailers, posters, titles and any related names and artwork are the property of their respective owners and are shown here for non-commercial, portfolio demonstration purposes. NETCHILL is not affiliated with, or endorsed by, any studio, network or rights holder.

- The site is non-commercial: no payments are taken and there is no advertising.
- If you are a rights holder and want something removed, open an issue on this repository and it will be taken down promptly.
- If you run your own copy, only upload media you own or have the right to distribute, such as public-domain or Creative Commons works, and keep any credit that a license requires.

## What this project demonstrates

- **Backend engineering:** a dependency-light Java 25 HTTP API (the JDK's built-in server, no framework) with PostgreSQL and a Maven fat-JAR build.
- **Edge architecture:** a Cloudflare Worker in front of R2 object storage and a D1 database, streaming video with range requests and checking signed, expiring links.
- **Security basics done carefully:** salted PBKDF2 password hashing, rate limiting, input validation, parameterized SQL, HMAC-signed media links and secrets kept out of the code. Details are below.
- **DevOps:** two Docker images, a CI/CD pipeline that lints, builds, pushes and deploys on every push to `main`, and infrastructure described in `render.yaml`.
- **Debugging real hosting problems:** free-tier cold starts, port binding and proxy IP handling. Notes are below.

## Architecture

```
Browser ──> Streamlit frontend ──> Java auth API ──> PostgreSQL
            (Render, Docker)       (Render, Docker)   (Aiven, accounts only)
               │
               └──────────────────> Cloudflare Worker ──> D1  (catalog: titles, episodes, tags)
                                    (JavaScript)       └─> R2  (posters/ and videos/)

Browser <───── posters and signed video links, streamed from the Worker
```

```
git push to main
   └─> GitHub Actions: lint ─> build 2 Docker images ─> push to Docker Hub
         └─> Render deploy hooks ─> Render pulls the images tagged with the commit SHA
```

The Worker is deployed separately, by pasting `worker/worker.js` into the Cloudflare dashboard. The pipeline above does not deploy it.

| Part | Technology |
|---|---|
| Frontend | Python 3.12, Streamlit 1.65.0, requests |
| Auth backend | Java 25, JDK `com.sun.net.httpserver`, PostgreSQL JDBC driver, Maven |
| Accounts database | PostgreSQL on Aiven (free plan) |
| Media API | Cloudflare Worker (JavaScript) |
| Catalog database | Cloudflare D1 (SQLite) |
| Posters and videos | Cloudflare R2 |
| Packaging | Docker (multi-stage build for the backend) |
| CI/CD | GitHub Actions, Docker Hub |
| Hosting | Render (free web services, deployed from Docker Hub images) |

## Features

- Two-step sign-up (name and date of birth, then email and password) and sign-in, each in a dialog.
- Signed-in area with Browse, Profiles, Account and Help pages.
- Browse page built from the real catalog: movies and TV shows with their posters, search by title, and Home, Series and Movies filters.
- The poster is the play button. Clicking it opens a large in-page player that starts playing straight away, with an episode picker and a Next button for TV shows.
- No payment details are collected, at sign-up or anywhere else.

## API

### Auth API (Java)

The backend accepts form-encoded `POST` bodies and is designed to be called by the frontend.

| Endpoint | Purpose | Responses |
|---|---|---|
| `GET /` | Health check, returns `OK` | 200 |
| `POST /api/register` | Create an account | 201 created, 400 invalid input, 409 email already registered, 429 rate limited or busy, 500 database error |
| `POST /api/login` | Check credentials | 200 success, 401 wrong credentials, 429 rate limited or busy, 500 database error |

### Media API (Cloudflare Worker)

| Endpoint | Purpose | Access |
|---|---|---|
| `GET /catalog` or `/search` | List or search titles. Query: `q`, `tag`, `kind` (`movie` or `show`), `limit`, `offset` | Public |
| `GET /titles/<id>` | One title; shows include their episodes | Public |
| `GET /media/<key>` | Stream a poster or video, with range requests for seeking | Posters public; videos need a signed link |
| `PUT` or `DELETE /media/<key>`, `GET /list` | Upload, delete and list files | Bearer token (`UPLOAD_TOKEN`) |

## Security design

| Area | What is implemented |
|---|---|
| Password storage | PBKDF2-HMAC-SHA256, 600,000 iterations, a random salt per user, and constant-time comparison. Older hashes (210,000 iterations) are upgraded the next time that user signs in. |
| Password policy | 8 to 128 characters. Passwords on a built-in common-password list, equal to the email address, or highly repetitive are rejected. |
| SQL | Every query is a prepared statement, in the Java API and in the Worker. |
| Login responses | One generic error for a wrong email or a wrong password. A dummy hash runs for unknown emails so response time does not reveal whether an account exists. |
| Rate limiting | 10 sign-ups per hour per IP. 5 failed sign-ins per 15 minutes per email, and 20 per 15 minutes per IP. 120 sign-in and sign-up attempts per minute across the whole API. |
| CPU protection | At most 2 password hashes run at once. Extra requests wait briefly, then get a "busy" response instead of freezing the small free server. |
| Client IP | The frontend forwards the visitor's IP together with a shared secret. The backend trusts it only if the secret matches, otherwise it uses `CF-Connecting-IP`, which Cloudflare sets. It never trusts `X-Forwarded-For`, which a client can forge. IPv6 addresses are grouped by `/64`. |
| Video links | Video files can only be fetched with a link signed by the frontend: an HMAC-SHA256 over the file key and an expiry time, checked by the Worker in constant time. Links expire after 6 to 7 hours, and a signature for one file does not work for another. Posters are public. |
| Media writes | Uploading, deleting and listing files in the bucket require a secret bearer token. |
| Input | Email and name validation on both sides, an 8 KB request body limit, and file keys that reject `..` and leading slashes. |
| Output | User-supplied text and catalog text are HTML-escaped before it is shown, and image URLs are checked against an allow-list pattern or must point at the Worker. |
| Secrets | Database URL, shared secrets, signing secret and API keys come from environment variables. Nothing sensitive is in the repository, and Render generates the shared API secret. |
| Transport | The database connection requires TLS (`sslmode=require`). |
| Containers | Both images run as a non-root user. Frontend dependencies are pinned to exact versions, and `.dockerignore` files keep secrets out of the images. |

## Engineering notes

- **Free-tier cold starts.** Render's free services sleep when idle. Requests sent from the frontend's server to a sleeping backend returned an instant `502` and never woke it, while a request from a real browser did. The page now sends the visitor's own browser to the backend on load. The sign-in and sign-up dialogs also keep retrying, with a click-to-wake link as a fallback.
- **Startup order.** The backend opens its port first and prepares the database in a background retry loop. Render's port check passes even when the database is slow or briefly unreachable, and the API recovers on its own.
- **Rate limits behind proxies.** Behind Render and Cloudflare, the socket address is the proxy's. Limits are keyed on a trustworthy visitor IP so one visitor cannot use forged headers to dodge them, and unrelated visitors do not share one bucket.
- **Accounts and catalog are separate stores.** Accounts live in PostgreSQL behind the Java API. The catalog lives in D1 and is read only by the Worker, so a catalog problem cannot affect sign-in.
- **Stable signed links.** The signing expiry is rounded to the hour, so the video link stays identical across Streamlit reruns and the video does not restart when the page redraws.
- **Poster as a button.** Streamlit buttons cannot contain images, so the real button is stretched invisibly over the poster with CSS. Keyboard and screen-reader access still work through the real button.

## CI/CD

`.github/workflows/deploy.yml` runs on every push to `main`:

1. **Lint:** `py_compile` plus `ruff` for syntax errors and undefined names in `frontend/app.py`.
2. **Build and push:** builds the frontend and backend images, tags each with `latest` and the commit SHA, and pushes them to Docker Hub.
3. **Deploy:** calls the Render deploy hooks, pointing each service at the image tagged with that commit.

The workflow reads four repository secrets: `DOCKER_USERNAME`, `DOCKER_PASSWORD`, `RENDER_BACKEND_DEPLOY_HOOK` and `RENDER_FRONTEND_DEPLOY_HOOK`.

## Run it locally

You need Docker (or JDK 25 with Maven, and Python 3.12), a PostgreSQL database that accepts TLS connections (a free Aiven service works well), and, for the catalog, a Cloudflare account with a Worker, a D1 database and an R2 bucket.

**Backend**

```bash
cd backend
docker build -t netchill-backend .
docker run --rm -p 8080:8080 \
  -e DATABASE_URL="postgres://USER:PASSWORD@HOST:PORT/DBNAME" \
  netchill-backend
```

It creates the `users` table on startup. Open http://localhost:8080/ and you should see `OK`.

**Media Worker**

1. Create a D1 database and run `worker/schema.sql` in its console.
2. Create an R2 bucket with `posters/` and `videos/` folders.
3. Create a Worker, paste in `worker/worker.js`, and add these bindings: R2 bucket `MEDIA`, D1 database `DB`, secrets `UPLOAD_TOKEN` and `MEDIA_SIGNING_SECRET`, and the variable `ALLOWED_ORIGIN`.
4. Add titles to D1. A file's key in the table must match its name in R2 exactly, including capital letters, apostrophes and the extension.

**Frontend**

```bash
cd frontend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
export NETCHILL_WORKER_URL="https://YOUR-WORKER.YOUR-SUBDOMAIN.workers.dev"
export MEDIA_SIGNING_SECRET="the same value as on the Worker"
streamlit run app.py
```

The frontend talks to `http://localhost:8080` for sign-in by default.

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
| `NETCHILL_WORKER_URL` | frontend | none | Address of the Cloudflare Worker. Set in Render's Environment tab, not in the repo. |
| `MEDIA_SIGNING_SECRET` | frontend and Worker | none | Signs and checks video links. Must match on both. While it is unset on the Worker, videos are public. |
| `UNSPLASH_ACCESS_KEY` | frontend | none, optional | Enables the Unsplash background photos on the landing page. |
| `REQUEST_TIMEOUT` | frontend | 60 | Seconds to wait for the backend. |
| `WAKE_MAX_SECONDS` | frontend | 240 | How long to keep waiting for a sleeping backend. |
| `UPLOAD_TOKEN` | Worker | none | Bearer token for uploading, deleting and listing files. |
| `ALLOWED_ORIGIN` | Worker | `*` | Website origin(s), comma-separated, allowed to call the Worker from a browser. |

## Repository layout

```
.
├── .github/workflows/deploy.yml     CI/CD pipeline
├── render.yaml                      Render services and shared secret group
├── backend/
│   ├── Dockerfile
│   ├── pom.xml
│   └── src/main/java/AuthServer.java
├── frontend/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app.py
└── worker/
    ├── worker.js                    Cloudflare Worker (catalog + media)
    └── schema.sql                   D1 tables
```

## Known limitations and roadmap

**Current limitations**

- Sign-in state lives in the Streamlit session. There are no server-issued session tokens yet, because the auth API has no protected endpoints.
- Signed video links are not tied to one viewer. Anyone who is given a valid link can use it until it expires, 6 to 7 hours later.
- Rate-limit counters are kept in memory, so they reset when the backend restarts or sleeps.
- Sign-up reveals whether an email is already registered, and there is no email verification.
- The catalog is cached for 5 minutes, so a new title can take that long to appear. The player does not move to the next episode automatically.
- On the free plans, the backend sleeps when idle, and Aiven can power off a free database after a long period without activity.
- There are no automated tests in the pipeline yet.

**Planned**

- Automated tests in the CI pipeline.
- Email verification and server-side sessions.
- Tying video links to the signed-in viewer, and automatic next-episode playback.