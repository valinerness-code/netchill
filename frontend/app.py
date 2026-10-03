import os
import json
import time
import html
import random
import hashlib
import streamlit as st
import re
import requests
from datetime import date

def _flatten_html(html_str: str) -> str:
    """Collapses all whitespace runs (including newlines/indentation) down to
    single spaces. HTML rendering here doesn't depend on whitespace, but
    Streamlit's markdown pre-processor can misread heavily-indented, multi-line
    content (e.g. a `style="..."` attribute split across lines) as an indented
    code block and render it as literal text instead of passing it through as
    HTML -- flattening avoids that entirely."""
    return re.sub(r"\s+", " ", html_str).strip()

# =========================================================================
# 1. SETUP & UTILITY HOOKS
# =========================================================================
st.set_page_config(page_title="NETCHILL | Watch Movies and TV Shows Online", page_icon="🍿", layout="wide")

# Set BACKEND_API_URL to the deployed API URL in Render; use localhost for local development.
# In production this should be an https:// URL, since passwords travel over it.
BACKEND_API_URL = os.getenv("BACKEND_API_URL", "http://localhost:8080").rstrip("/")
# Render's free tier spins services down when idle and a cold start can take ~50s,
# so the default is generous. Override with the REQUEST_TIMEOUT env var if you like.
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "60"))

# Must equal API_SHARED_SECRET on the Java service. Lets the backend trust the end-user
# IP we forward, so rate limits apply per user instead of to this server as a whole.
API_SHARED_SECRET = os.getenv("API_SHARED_SECRET", "")

def _backend_headers() -> dict:
    headers = {}
    if API_SHARED_SECRET:
        headers["X-Api-Key"] = API_SHARED_SECRET
        try:
            forwarded = st.context.headers.get("X-Forwarded-For", "")
            client_ip = forwarded.split(",")[0].strip()
            if client_ip:
                headers["X-Client-IP"] = client_ip
        except Exception:
            pass  # older Streamlit without st.context: backend falls back to its own detection
    return headers

# Render's free tier puts the backend to sleep when idle. While it boots, Render's proxy
# answers 502/503/504 (or the connection fails). We then ping the backend's home page
# until it answers, showing progress, and only then send the real request again.
WAKE_STATUSES = (502, 503, 504)
WAKE_MAX_SECONDS = int(os.getenv("WAKE_MAX_SECONDS", "240"))
WAKE_PING_TIMEOUT = 15

def _wake_backend(notice, first_problem: str) -> bool:
    """Ping GET / until the backend answers 200. Returns True once it is awake."""
    started = time.time()
    attempt = 0
    last = first_problem
    while time.time() - started < WAKE_MAX_SECONDS:
        attempt += 1
        try:
            ping = requests.get(f"{BACKEND_API_URL}/", timeout=WAKE_PING_TIMEOUT)
            if ping.status_code == 200:
                print(f"[wake] backend awake after {int(time.time() - started)}s ({attempt} pings)", flush=True)
                return True
            last = f"HTTP {ping.status_code}"
        except requests.RequestException as exc:
            last = type(exc).__name__
        print(f"[wake] ping {attempt} at {int(time.time() - started)}s -> {last}", flush=True)
        elapsed = int(time.time() - started)
        notice.info(
            f"The server is asleep and needs about a minute to start. "
            f"**[Click here to wake it up]({BACKEND_API_URL}/)** "
            f"(opens in a new tab and shows OK when it is ready). "
            f"This window continues on its own once the server answers. "
            f"({elapsed}s elapsed, last response: {last})"
        )
        time.sleep(3)
    print(f"[wake] backend did not wake up within {WAKE_MAX_SECONDS}s (last: {last})", flush=True)
    return False

def post_to_backend(path: str, data: dict):
    """POST form data to the backend, waking it up first if it is asleep.

    The request is sent normally first. Only if it fails with a gateway error or a failed
    connection (the backend never processed it) do we wait for the backend to wake up and
    send it once more, so a retry can't create a duplicate account.
    Raises requests.RequestException if the backend never comes up.
    """
    def send():
        return requests.post(
            f"{BACKEND_API_URL}{path}",
            data=data,
            headers=_backend_headers(),
            timeout=REQUEST_TIMEOUT,
        )

    try:
        response = send()
        if response.status_code not in WAKE_STATUSES:
            return response
        problem = f"HTTP {response.status_code}"
    except requests.ConnectionError as exc:  # includes connect timeouts
        problem = type(exc).__name__

    notice = st.empty()
    awake = _wake_backend(notice, problem)
    notice.empty()
    if not awake:
        raise requests.ConnectionError("Backend did not wake up in time")
    return send()

def show_backend_error(response):
    """Unexpected backend response: keep the status code visible for debugging."""
    st.error(f"Something went wrong (HTTP {response.status_code}). Please try again.")

APP_BUILD = "wake-v9-future-proof"

# A sleeping Render service wakes when a real browser (or curl) requests it, but requests
# sent from this server get an instant 502 and do not wake it. So the visitor's own browser
# pings the backend through a hidden iframe plus a no-cors fetch as soon as the page loads.
# If that does not work, the signup dialog still shows a "click here to wake it up" link.
# The element is re-emitted on reruns for the first 5 minutes so the browser keeps the same
# iframe instead of reloading it.
if "browser_warm_started" not in st.session_state:
    st.session_state["browser_warm_started"] = time.time()
if (BACKEND_API_URL.startswith("http")
        and time.time() - st.session_state["browser_warm_started"] < 300):
    try:
        _home = BACKEND_API_URL + "/"
        _wake_page = (
            f'<iframe src="{html.escape(_home, quote=True)}" tabindex="-1" aria-hidden="true" '
            f'style="position:absolute;width:1px;height:1px;opacity:0;border:0"></iframe>'
            f'<script>fetch({json.dumps(_home)}, {{mode: "no-cors", keepalive: true}})'
            f'.catch(function () {{}});</script>'
        )
        try:
            # Proven to work on this deployment, but Streamlit has deprecated it
            # (it prints a warning and is scheduled for removal).
            import streamlit.components.v1 as components
            components.html(_wake_page, height=0)
        except Exception:
            # Newer replacement, used automatically once components.html is gone.
            st.iframe(_wake_page, height=1)
    except Exception as exc:  # never let the warm-up break the page
        print(f"[browser-wake] skipped: {type(exc).__name__}: {exc}", flush=True)

# Open the site with ?debug=1 on the end of the address to see this panel.
if st.query_params.get("debug") == "1":
    with st.expander("Connection diagnostics", expanded=True):
        st.write(f"Build: {APP_BUILD}")
        st.write(f"Backend address: {BACKEND_API_URL}")
        if st.button("Ping backend now"):
            t0 = time.time()
            try:
                r = requests.get(f"{BACKEND_API_URL}/", timeout=120)
                st.write(f"Result: HTTP {r.status_code} after {time.time() - t0:.1f}s")
            except requests.RequestException as exc:
                st.write(f"Result: {type(exc).__name__} after {time.time() - t0:.1f}s")

# Unsplash API key: set it in Render's Environment tab, never in the code.
UNSPLASH_ACCESS_KEY = os.getenv("UNSPLASH_ACCESS_KEY", "")

# ---- Input validation (strict allowlists) ----
EMAIL_REGEX = r"^[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,190}\.[A-Za-z]{2,}$"
NAME_REGEX = r"^[^\W\d_]+(?:[ '\-][^\W\d_]+)*$"  # letters, spaces, ' and -

def valid_email(s: str) -> bool:
    # fullmatch (like Java's matches()): plain `$` would also accept a trailing newline
    return len(s) <= 254 and re.fullmatch(EMAIL_REGEX, s) is not None

def valid_name(s: str) -> bool:
    # \w also admits some non-letters (e.g. superscript digits) that Java's \p{L} rejects,
    # so additionally require every character to be a real letter, space, ' or -.
    return (
        0 < len(s) <= 50
        and re.fullmatch(NAME_REGEX, s) is not None
        and all(ch.isalpha() or ch in " '-" for ch in s)
    )

# Only allow Unsplash image URLs made of URL-safe characters (no quotes/parens),
# so a URL can never break out of the CSS url('...') it is placed in.
_UNSPLASH_URL_RE = re.compile(r"https://images\.unsplash\.com/[A-Za-z0-9._~:/?#\[\]@!$&*+,;=%-]+")

def _safe_image_url(url) -> bool:
    return isinstance(url, str) and len(url) < 2000 and _UNSPLASH_URL_RE.fullmatch(url) is not None

if "bg_seed" not in st.session_state:
    st.session_state.bg_seed = random.randint(1, 1_000_000)

# ---- Unsplash background images ----
# The old source.unsplash.com/random URL is dead, so we use the official API.
def _request_unsplash(count: int) -> list:
    r = requests.get(
        "https://api.unsplash.com/photos/random",
        params={"count": count, "orientation": "portrait"},
        headers={"Authorization": f"Client-ID {UNSPLASH_ACCESS_KEY}"},
        timeout=10,
    )
    r.raise_for_status()
    return [p["urls"]["small"] for p in r.json()]

@st.cache_data(ttl=3600, show_spinner=False)
def _cached_unsplash(seed: int, count: int) -> list:
    # Cached for 1 hour so we don't call the API on every rerun.
    # Errors aren't cached, so a failed call is retried next time.
    return _request_unsplash(count)

def fetch_unsplash_images(seed: int, count: int = 30) -> list:
    """Returns image URLs, or [] on failure (tiles then use gradients)."""
    if not UNSPLASH_ACCESS_KEY:
        return []
    try:
        return [u for u in _cached_unsplash(seed, count) if _safe_image_url(u)]
    except Exception:
        return []

# ---- Poster-card generator ---------------------------------------------
# Movie/TV cards: a gradient picked from the title, plus genre and rating.
_PALETTES = [
    ("#1f1c2c", "#928dab"), ("#0f2027", "#2c5364"), ("#3a1c71", "#d76d77"),
    ("#0f0c29", "#302b63"), ("#833ab4", "#fd1d1d"), ("#134e5e", "#71b280"),
    ("#360033", "#0b8793"), ("#2b5876", "#4e4376"), ("#8e0e00", "#1f1c18"),
    ("#141e30", "#243b55"), ("#5f2c82", "#49a09d"), ("#642b73", "#c6426e"),
]

def _poster_palette(title: str):
    idx = int(hashlib.md5(title.encode()).hexdigest(), 16) % len(_PALETTES)
    return _PALETTES[idx]

def _title_font_cqw(title: str, cap: float, usable: float = 88.0, char_w: float = 0.86) -> float:
    """Font size (in cqw = % of the tile's width) so the longest word fits on one line.
    char_w is a safe average width of a bold uppercase Georgia letter, in em."""
    longest = max((len(w) for w in title.split()), default=1)
    return round(min(cap, usable / (longest * char_w)), 2)

_TITLE_FIT_CSS = ("overflow-wrap:normal; word-break:keep-all; hyphens:manual; "
                  "text-wrap:balance; ")

_WALL_TITLES = [
    "Midnight Run", "Skyline", "Crimson Tide", "Neon Glow", "Nightfall",
    "Signal Ridge", "Glass City", "Thorn Lane", "Last Harbor", "Iron Orchard",
    "Silent Echo", "Paper Moon", "Wild Static", "Ember Road", "Northern Lights",
    "Velvet Hour", "Dark Meridian", "Golden Hollow", "Lost Frequency", "Broken Compass",
]

def build_hero_poster_wall_html(cols: int = 5, rows: int = 3) -> str:
    """Full-screen tile grid behind a dark overlay, each tile with a fake title."""
    total = cols * rows
    images = fetch_unsplash_images(st.session_state.bg_seed, total)
    rng = random.Random(st.session_state.bg_seed)
    titles = rng.sample(_WALL_TITLES, total)
    tiles = []
    for i in range(total):
        if images:
            url = html.escape(images[i % len(images)], quote=True)
            bg = f"#111 url('{url}') center/cover no-repeat"
        else:
            c1, c2 = rng.choice(_PALETTES)
            bg = f"linear-gradient(155deg, {c1} 0%, {c2} 100%)"
        title = html.escape(titles[i])
        tiles.append(
            f'<div style="background: {bg}; position: relative; overflow: hidden; container-type:inline-size;">'
            f'<div style="position:absolute; inset:0; background:linear-gradient(to top, rgba(0,0,0,0.8) 0%, rgba(0,0,0,0) 55%);"></div>'
            f'<div style="position:absolute; left:10px; right:10px; bottom:14px; text-align:center; '
            f"font-family:Georgia,'Times New Roman',serif; font-weight:900; text-transform:uppercase; "
            f'font-size:clamp(0.9rem,1.8vw,1.6rem); font-size:{_title_font_cqw(titles[i], 9, 84)}cqw; '
            f'line-height:1.1; color:#fff; {_TITLE_FIT_CSS}'
            f'text-shadow:0 3px 10px rgba(0,0,0,0.8);">{title}</div>'
            f'</div>'
        )
    result = f"""
    <div style="
        position:fixed; top:0; left:0; width:100vw; height:100vh; z-index:-2;
        display:grid; grid-template-columns:repeat({cols}, 1fr); grid-template-rows:repeat({rows}, 1fr);
        overflow:hidden;
    ">{''.join(tiles)}</div>
    <div style="
        position:fixed; top:0; left:0; width:100vw; height:100vh; z-index:-1;
        background: rgba(0,0,0,0.55);
    "></div>
    """
    return _flatten_html(result)

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

def poster_card_html(title: str, genre: str = "Drama", rating: str = None, height: int = 260) -> str:
    c1, c2 = _poster_palette(title)
    if rating is None:
        rating = f"{(int(hashlib.md5((title+'r').encode()).hexdigest(), 16) % 25 + 70) / 10:.1f}"
    n = len(title)
    cap = 12 if n <= 12 else 10 if n <= 20 else 8.5
    font_cqw = _title_font_cqw(title, cap)
    font_size = 1.6 if n <= 12 else 1.3 if n <= 20 else 1.05  # fallback for old browsers
    safe_title = html.escape(title)
    safe_genre = html.escape(genre)
    safe_rating = html.escape(str(rating))
    result = f"""
    <div class="poster-tile" style="
        position:relative; height:{int(height)}px; border-radius:10px; overflow:hidden;
        background: linear-gradient(155deg, {c1} 0%, {c2} 100%);
        box-shadow: 0 8px 20px rgba(0,0,0,0.55);
        border: 1px solid rgba(255,255,255,0.08);
        display:flex; flex-direction:column; justify-content:space-between;
        padding:14px; box-sizing:border-box;
        margin-bottom:8px; container-type:inline-size;
    ">
        <div style="display:flex; justify-content:space-between; align-items:flex-start;">
            <span style="
                background:rgba(0,0,0,0.45); color:#FFD166; font-size:0.7rem;
                font-weight:700; padding:2px 8px; border-radius:4px; letter-spacing:1px;
                text-transform:uppercase;">{safe_genre}</span>
            <span style="
                background:rgba(0,0,0,0.45); color:#fff; font-size:0.75rem;
                font-weight:700; padding:2px 8px; border-radius:4px;">★ {safe_rating}</span>
        </div>
        <div style="flex:1; min-height:0; min-width:0; display:flex; align-items:center; justify-content:center; text-align:center;">
            <div style="
                font-family: Georgia, 'Times New Roman', serif; font-weight:900;
                font-size:{font_size}rem; font-size:{font_cqw}cqw;
                line-height:1.1; color:#fff; text-transform:uppercase;
                text-shadow: 0 3px 10px rgba(0,0,0,0.6);
                {_TITLE_FIT_CSS}
            ">{safe_title}</div>
        </div>
        <div style="
            height:3px; width:40%; margin:0 auto; background:rgba(255,255,255,0.35);
            border-radius:2px;"></div>
    </div>
    """
    return _flatten_html(result)

# 2. Base theme: .stApp is transparent so the background wall shows through.
st.markdown(f"""
    <style>
    html, body {{ background: #0b0b0f; }}
    .stApp {{ 
        background: transparent !important;
        color: #FFFFFF; 
        font-family: 'Inter', sans-serif; 
    }}
    [data-testid="stAppViewContainer"] {{
        position: relative;
        z-index: 1;
        background: transparent !important;
    }}
    [data-testid="stHeader"] {{
        background: transparent !important;
    }}
    hr {{ border-color: #333; }}
    .brand-title {{ color: #E50914 !important; font-weight: 900; font-size: 2.2rem; letter-spacing: -1px; }}
    .hero-title {{ font-size: 3.5rem; font-weight: 800; line-height: 1.1; margin-bottom: 10px; color: #FFF; }}

    /* Netflix-style row headers */
    .section-title {{
        font-size: 1.4rem; font-weight: 700; margin-top: 28px; margin-bottom: 10px;
        color: #FFF; letter-spacing: 0.2px;
    }}

    .profile-card {{ text-align: center; background: #222; padding: 25px; border-radius: 8px; border: 2px solid #333; }}
    .profile-card:hover {{ border-color: #E50914; }}

    /* Poster tiles zoom + lift on hover, like a Netflix row card */
    .poster-tile {{
        transition: transform 0.25s ease, box-shadow 0.25s ease;
        transform-origin: center;
    }}
    .poster-tile:hover {{
        transform: scale(1.045);
        box-shadow: 0 16px 34px rgba(0,0,0,0.75) !important;
        z-index: 5;
    }}
    /* Let the hover scale show instead of being clipped (older + newer Streamlit test ids) */
    div[data-testid="column"], div[data-testid="stColumn"] {{ overflow: visible !important; }}
    div[data-testid="stVerticalBlock"] {{ overflow: visible !important; }}

    /* Primary CTAs -- bold red */
    button[kind="primary"] {{
        background-color: #E50914 !important; color: white !important;
        border: none !important; padding: 0.5rem 1.5rem !important;
        font-weight: 600 !important; border-radius: 4px !important;
        transition: transform 0.15s ease, box-shadow 0.15s ease, background-color 0.15s ease;
    }}
    button[kind="primary"]:hover {{
        background-color: #B81D24 !important;
        transform: translateY(-1px);
        box-shadow: 0 6px 16px rgba(229,9,20,0.45);
    }}

    /* Row-action chips -- slim ghost pills */
    button[kind="secondary"] {{
        background-color: rgba(255,255,255,0.10) !important;
        color: #FFF !important;
        border: 1px solid rgba(255,255,255,0.35) !important;
        border-radius: 20px !important;
        padding: 0.25rem 1rem !important;
        font-weight: 600 !important;
        font-size: 0.82rem !important;
        letter-spacing: 0.3px;
        backdrop-filter: blur(4px);
    }}
    button[kind="secondary"]:hover {{
        background-color: #FFFFFF !important;
        color: #000 !important;
        border-color: #FFFFFF !important;
    }}

    /* Netflix-style top filter tabs (Home / Series / Movies) */
    div[role="radiogroup"] label {{
        font-size: 1rem !important;
        font-weight: 600 !important;
        letter-spacing: 0.5px;
        text-transform: uppercase;
        margin-right: 6px;
    }}
    input[type="radio"] {{ accent-color: #E50914; }}
    </style>
    """, 
    unsafe_allow_html=True
)

if "user_email" not in st.session_state:
    st.session_state.user_email = ""
if "signup_email" not in st.session_state:
    st.session_state.signup_email = ""
if "signup_step" not in st.session_state:
    st.session_state.signup_step = None  # None -> "info" -> "plan"
if "signup_first_name" not in st.session_state:
    st.session_state.signup_first_name = ""
if "signup_last_name" not in st.session_state:
    st.session_state.signup_last_name = ""
if "signup_dob" not in st.session_state:
    st.session_state.signup_dob = None
if "current_profile" not in st.session_state:
    st.session_state.current_profile = ""
if "user_name" not in st.session_state:
    st.session_state.user_name = ""
if "profile_color" not in st.session_state:
    st.session_state.profile_color = "amber"

def sign_out_action():
    st.session_state.logged_in = False
    st.session_state.user_email = ""
    st.session_state.current_profile = ""
    st.session_state.user_name = ""
    st.session_state.profile_color = "amber"
    st.session_state.signup_step = None
    st.session_state.signup_first_name = ""
    st.session_state.signup_last_name = ""
    st.session_state.signup_dob = None
    st.success("Successfully logged out.")
    st.rerun()

# =========================================================================
# 2. DIALOG INTERFACES (COMMUNICATES WITH JAVA BACKEND CONTROLLERS)
# =========================================================================

@st.dialog("Sign In")
def show_login_dialog():
    """Form-encodes credentials to safely authorize users via Java api/login endpoint"""
    email = st.text_input("Email", placeholder="Enter your email").strip().lower()
    password = st.text_input("Password", type="password", placeholder="Enter your password")

    if st.button("Sign In", use_container_width=True, type="primary"):
        if not valid_email(email):
            st.error("Enter a valid email address.")
        elif not (6 <= len(password) <= 128):
            st.error("Password must be 6-128 characters.")
        else:
            try:
                # Java accepts form URL encoding (x-www-form-urlencoded) parameters natively
                response = post_to_backend("/api/login", {"email": email, "password": password})
            except requests.RequestException:
                st.error("Can't reach the server right now. Please wait a minute and try again.")
                return

            if response.status_code == 200:
                try:
                    data = response.json()
                except ValueError:
                    data = {}
                name = str(data.get("first_name") or data.get("firstName") or "")[:50]
                if not valid_name(name):
                    name = email.split("@")[0]
                st.session_state.user_email = email
                st.session_state.logged_in = True
                st.session_state.user_name = name
                st.session_state.current_profile = name
                st.rerun()
            elif response.status_code == 429:
                st.error("Too many attempts. Please wait a few minutes and try again.")
            elif response.status_code == 401:
                st.error("Incorrect email or password.")
            else:
                show_backend_error(response)

@st.dialog("Tell Us About You")
def show_personal_info_dialog():
    """Step 1 of signup: collect profile basics, Netflix-style. No payment info here or ever."""
    st.text(f"Almost there, {st.session_state.signup_email}. Just a little more about you.")
    first_name = st.text_input("First name", value=st.session_state.signup_first_name, max_chars=50)
    last_name = st.text_input("Last name", value=st.session_state.signup_last_name, max_chars=50)
    dob = st.date_input(
        "Date of birth",
        value=st.session_state.signup_dob or date(2000, 1, 1),
        min_value=date(1900, 1, 1),
        max_value=date.today(),
    )

    if st.button("Continue", use_container_width=True, type="primary"):
        if not (valid_name(first_name.strip()) and valid_name(last_name.strip())):
            st.error("Names may only contain letters, spaces, apostrophes and hyphens (max 50).")
        else:
            st.session_state.signup_first_name = first_name.strip()
            st.session_state.signup_last_name = last_name.strip()
            st.session_state.signup_dob = dob
            st.session_state.signup_step = "plan"
            st.rerun()

@st.dialog("Start Your Membership")
def show_registration_dialog():
    """Step 2 of signup: plan + password. Form-encodes everything, including the
    name/DOB collected in step 1, to the Java api/register endpoint. Deliberately
    no credit card / payment fields -- membership stays fake past this point."""
    st.text(f"Hi {st.session_state.signup_first_name} — choose your plan and set a password.")
    plan = st.radio("Choose your plan", ["Basic - $8.99/mo", "Standard - $15.49/mo", "Premium - $22.99/mo"], index=2)
    email = st.text_input("Email address", value=st.session_state.signup_email).strip().lower()
    password = st.text_input("Create Password", type="password")

    if st.button("Register & Start Membership", use_container_width=True, type="primary"):
        if not valid_email(email):
            st.error("Please enter a valid email address.")
        elif len(password) < 6 or len(password) > 128:
            st.error("Password must be between 6 and 128 characters.")
        elif not (valid_name(st.session_state.signup_first_name) and valid_name(st.session_state.signup_last_name)):
            st.error("Please go back and re-enter your name.")
        else:
            payload = {
                "email": email,
                "password": password,
                "first_name": st.session_state.signup_first_name,
                "last_name": st.session_state.signup_last_name,
                "date_of_birth": st.session_state.signup_dob.isoformat() if st.session_state.signup_dob else "",
            }
            try:
                response = post_to_backend("/api/register", payload)
            except requests.RequestException:
                st.error("Can't reach the server right now. Please wait a minute and try again.")
                return

            if response.status_code == 201:
                st.session_state.user_email = email
                st.session_state.logged_in = True
                st.session_state.current_profile = st.session_state.signup_first_name
                st.session_state.user_name = st.session_state.signup_first_name
                st.session_state.signup_email = ""
                st.session_state.signup_step = None
                st.rerun()
            elif response.status_code == 409:
                st.error("An account with that email already exists. Try signing in instead.")
            elif response.status_code == 429:
                st.error("Too many attempts. Please try again later.")
            elif response.status_code == 400:
                st.error("Please check your details and try again.")
            else:
                show_backend_error(response)

# =========================================================================
# 3. INTERACTION FEEDS & PLATFORM WORKSPACES
# =========================================================================

def landing_page():
    st.markdown(build_hero_poster_wall_html(), unsafe_allow_html=True)

    if st.session_state.signup_step == "info":
        show_personal_info_dialog()
    elif st.session_state.signup_step == "plan":
        show_registration_dialog()

    # Top bar: empty left | NETCHILL centered | Sign In on the right side 
    nav_left, nav_center, nav_right = st.columns([3, 4, 3])
    with nav_center:
        st.markdown(
            '<div class="brand-title" style="text-align:center; font-size:4rem;">NETCHILL</div>'
            '<div style="text-align:center; color:#E50914; font-weight:700; text-transform:uppercase; '
            'font-size:1.8rem; letter-spacing:2px; margin-top:-8px;">New &amp; trending</div>',
            unsafe_allow_html=True,
        )
    with nav_right:
        _spacer, signin_col = st.columns([1, 1])   # button takes half of this column
        with signin_col:
            if st.button("Sign In", use_container_width=True, type="primary"):
                show_login_dialog()

    st.write("")
    st.markdown('<h1 class="hero-title">Unlimited movies, TV shows, and more.</h1>', unsafe_allow_html=True)
    st.markdown('<h5>Watch anywhere. Cancel anytime.</h5>', unsafe_allow_html=True)

    # Push the email box and button further down the page
    st.markdown('<div style="height:160px;"></div>', unsafe_allow_html=True)

    # Email box and button are each 25% of the page width, pushed to the right side
    _rest, col_em, col_btn = st.columns([2, 1, 1])
    with col_em:
        hero_email = st.text_input("Email address", placeholder="Email address", label_visibility="collapsed", key="hero_email_input", max_chars=254)
    with col_btn:
        if st.button("Get Started", use_container_width=True, type="primary"):
            clean_email = hero_email.strip().lower()
            if not valid_email(clean_email):
                st.error("Please enter a valid email address.")
            else:
                st.session_state.signup_email = clean_email
                st.session_state.signup_step = "info"
                st.rerun()

def dashboard_page():
    view_selection = st.radio("Filter Content Matrix", ["Home", "Series", "Movies"], horizontal=True, label_visibility="collapsed")
    color_emoji = "🟡" if st.session_state.profile_color == "amber" else "🔴" if st.session_state.profile_color == "pink" else "🔵"
    safe_profile = html.escape(st.session_state.current_profile)
    st.markdown(
        f"<h3>{color_emoji} Active Session: <b>{safe_profile}</b></h3>",
        unsafe_allow_html=True,
    )

    if view_selection in ["Home", "Movies"]:
        st.markdown('<div class="section-title">Movies</div>', unsafe_allow_html=True)
        m_cols = st.columns(4)
        movies = [
            ("Midnight Run", "Thriller"), ("Skyline", "Sci-Fi"),
            ("Crimson Tide", "Action"), ("Neon Glow", "Drama"),
        ]
        for idx, (item, genre) in enumerate(movies):
            with m_cols[idx]:
                st.markdown(poster_card_html(item, genre), unsafe_allow_html=True)
                st.button("Play Video", key=f"mov_{idx}", use_container_width=True)

    if view_selection in ["Home", "Series"]:
        st.markdown('<div class="section-title">TV Shows</div>', unsafe_allow_html=True)
        t_cols = st.columns(4)
        shows = [
            ("Nightfall", "Mystery"), ("Signal Ridge", "Sci-Fi"),
            ("Glass City", "Drama"), ("Thorn Lane", "Horror"),
        ]
        for idx, (item, genre) in enumerate(shows):
            with t_cols[idx]:
                st.markdown(poster_card_html(item, genre), unsafe_allow_html=True)
                st.button("Watch Episode", key=f"tv_{idx}", use_container_width=True)

def manage_profiles_page():
    st.markdown('<div class="section-title" style="text-align:center;">Manage Profiles</div>', unsafe_allow_html=True)
    p_cols = st.columns(3)
    profiles_data = [
        {"name": st.session_state.user_name or "Me", "color": "amber", "avatar": "🟡"},
        {"name": "Mia", "color": "pink", "avatar": "🔴"},
        {"name": "Kids", "color": "blue", "avatar": "🔵"}
    ]
    for idx, p in enumerate(profiles_data):
        with p_cols[idx]:
            st.markdown(f"""
            <div class="profile-card">
                <h1 style='font-size:4rem; margin:0;'>{p['avatar']}</h1>
                <h3>{html.escape(p['name'])}</h3>
            </div>
            """, unsafe_allow_html=True)
            # Key by index (not name) so a user named "Mia" or "Kids" can't cause a duplicate-key error.
            if st.button(f"Activate {p['name']}", key=f"set_prof_{idx}", use_container_width=True):
                st.session_state.current_profile = p['name']
                st.session_state.profile_color = p['color']
                st.toast(f"Switched profile context directly to {p['name']}!")
                st.rerun()

def account_page():
    st.markdown('<div class="section-title">Account Details</div>', unsafe_allow_html=True)
    st.write("---")
    rows = [
        ("Membership Tier", "Premium Framework"),
        ("Registered User Email", st.session_state.user_email),
        ("Video Resolution Profile", "4K Ultra-HD Streaming Active"),
        ("Billing Account Record", "Visa •••• 2431"),
    ]
    for label, value in rows:
        col_lbl, col_val = st.columns(2)
        col_lbl.markdown(f"**{label}**")
        col_val.text(value)  # plain text: never interpreted as markdown/HTML

def help_page():
    st.markdown('<div class="section-title">Help Center Assistance Dashboard</div>', unsafe_allow_html=True)
    st.write("For account or playback support, contact NETCHILL customer service.")

def run_app():
    if not st.session_state.logged_in:
        landing_page()
        return

    with st.sidebar:
        st.markdown('<div class="brand-title">NETCHILL</div>', unsafe_allow_html=True)
        page = st.radio("Navigation", ["Browse", "Profiles", "Account", "Help"])
        st.text(st.session_state.user_email)
        if st.button("Sign Out", use_container_width=True):
            sign_out_action()

    pages = {
        "Browse": dashboard_page,
        "Profiles": manage_profiles_page,
        "Account": account_page,
        "Help": help_page,
    }
    pages[page]()

run_app()