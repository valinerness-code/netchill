import os
import random
import hashlib
import streamlit as st
import re
import requests

# =========================================================================
# 1. SETUP & UTILITY HOOKS
# =========================================================================
st.set_page_config(page_title="NETCHILL | Watch Movies and TV Shows Online", page_icon="🍿", layout="wide")

# Set BACKEND_API_URL to the deployed API URL in Render; use localhost for local development.
BACKEND_API_URL = os.getenv("BACKEND_API_URL", "http://localhost:8080").rstrip("/")

# 1. Random background image on every refresh, using Lorem Picsum (source.unsplash.com's
#    old random-redirect endpoint was shut down, so we use a service that still returns
#    a real image directly). A random seed + cache-busting query param guarantees a new
#    photo each time the script reruns (e.g. on every page refresh or interaction).
if "bg_seed" not in st.session_state:
    st.session_state.bg_seed = random.randint(1, 1_000_000)

BACKGROUND_IMAGE_URL = f"https://picsum.photos/seed/{st.session_state.bg_seed}/1920/1080"

# ---- Poster-card generator ---------------------------------------------
# There's no free API for real (licensed) movie-poster art, and pulling actual
# studio poster images would raise copyright issues. Instead we generate
# original "poster-look" cards in pure CSS: a deterministic gradient (so the
# same title always gets the same look), bold poster-style type, a rating
# badge, and a framed/shadowed card -- styled like a streaming-service tile.
_PALETTES = [
    ("#1f1c2c", "#928dab"), ("#0f2027", "#2c5364"), ("#3a1c71", "#d76d77"),
    ("#0f0c29", "#302b63"), ("#833ab4", "#fd1d1d"), ("#134e5e", "#71b280"),
    ("#360033", "#0b8793"), ("#2b5876", "#4e4376"), ("#8e0e00", "#1f1c18"),
    ("#141e30", "#243b55"), ("#5f2c82", "#49a09d"), ("#642b73", "#c6426e"),
]

def _poster_palette(title: str):
    idx = int(hashlib.md5(title.encode()).hexdigest(), 16) % len(_PALETTES)
    return _PALETTES[idx]

def poster_card_html(title: str, genre: str = "Drama", rating: str = None, height: int = 260) -> str:
    c1, c2 = _poster_palette(title)
    if rating is None:
        rating = f"{(int(hashlib.md5((title+'r').encode()).hexdigest(), 16) % 25 + 70) / 10:.1f}"
    words = title.split()
    big = words[0]
    rest = " ".join(words[1:])
    return f"""
    <div class="poster-tile" style="
        position:relative; height:{height}px; border-radius:10px; overflow:hidden;
        background: linear-gradient(155deg, {c1} 0%, {c2} 100%);
        box-shadow: 0 8px 20px rgba(0,0,0,0.55);
        border: 1px solid rgba(255,255,255,0.08);
        display:flex; flex-direction:column; justify-content:space-between;
        padding:14px; box-sizing:border-box;
        margin-bottom:8px;
    ">
        <div style="display:flex; justify-content:space-between; align-items:flex-start;">
            <span style="
                background:rgba(0,0,0,0.45); color:#FFD166; font-size:0.7rem;
                font-weight:700; padding:2px 8px; border-radius:4px; letter-spacing:1px;
                text-transform:uppercase;">{genre}</span>
            <span style="
                background:rgba(0,0,0,0.45); color:#fff; font-size:0.75rem;
                font-weight:700; padding:2px 8px; border-radius:4px;">★ {rating}</span>
        </div>
        <div style="text-align:center;">
            <div style="
                font-family: Georgia, 'Times New Roman', serif; font-weight:900;
                font-size:1.6rem; line-height:1.05; color:#fff; text-transform:uppercase;
                text-shadow: 0 3px 10px rgba(0,0,0,0.6);">{big}</div>
            <div style="
                font-family: Georgia, 'Times New Roman', serif; font-weight:700;
                font-size:1.05rem; color:rgba(255,255,255,0.9); text-transform:uppercase;
                letter-spacing:2px;">{rest}</div>
        </div>
        <div style="
            height:3px; width:40%; margin:0 auto; background:rgba(255,255,255,0.35);
            border-radius:2px;"></div>
    </div>
    """

# 2. Re-injecting your custom theme while adding the dynamic cloud background layers
st.markdown(f"""
    <style>
    .stApp {{ 
        background: linear-gradient(rgba(0, 0, 0, 0.70), rgba(0, 0, 0, 0.70)), url("{BACKGROUND_IMAGE_URL}");
        background-size: cover;
        background-position: center;
        background-repeat: no-repeat;
        background-attachment: fixed;
        color: #FFFFFF; 
        font-family: 'Inter', sans-serif; 
    }}
    hr {{ border-color: #333; }}
    .brand-title {{ color: #E50914 !important; font-weight: 900; font-size: 2.2rem; letter-spacing: -1px; }}
    .hero-title {{ font-size: 3.5rem; font-weight: 800; line-height: 1.1; margin-bottom: 10px; color: #FFF; }}

    /* Netflix-style row headers: tight, bold, no big margin -- the row IS the focus, not the label */
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
    /* Let the hover scale actually show instead of being clipped by Streamlit's column padding */
    div[data-testid="column"] {{ overflow: visible !important; }}
    div[data-testid="stVerticalBlock"] {{ overflow: visible !important; }}

    /* Primary CTAs (Sign In / Get Started / Register) -- bold red, Netflix's signature button */
    button[kind="primary"] {{
        background-color: #E50914 !important; color: white !important;
        border: none !important; padding: 0.5rem 1.5rem !important;
        font-weight: 600 !important; border-radius: 4px !important;
    }}
    button[kind="primary"]:hover {{ background-color: #B81D24 !important; }}

    /* Row-action chips (Play / Watch Episode / Activate / Sign Out) -- slim ghost pills */
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

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "user_email" not in st.session_state:
    st.session_state.user_email = ""
if "signup_email" not in st.session_state:
    st.session_state.signup_email = ""
if "current_profile" not in st.session_state:
    st.session_state.current_profile = "Alex"
if "profile_color" not in st.session_state:
    st.session_state.profile_color = "amber"

EMAIL_REGEX = r"^[^\s@]+@[^\s@]+\.[^\s@]+$"

def sign_out_action():
    st.session_state.logged_in = False
    st.session_state.user_email = ""
    st.session_state.current_profile = "Alex"
    st.session_state.profile_color = "amber"
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
        if not re.match(EMAIL_REGEX, email):
            st.error("Enter a valid email address.")
        elif len(password) < 6:
            st.error("Password must be 6+ characters.")
        else:
            try:
                # Java accepts form URL encoding (x-www-form-urlencoded) parameters natively
                payload = {"email": email, "password": password}
                response = requests.post(f"{BACKEND_API_URL}/api/login", data=payload)

                if response.status_code == 200:
                    st.session_state.user_email = email
                    st.session_state.logged_in = True
                    st.success("Signed in successfully!")
                    st.rerun()
                else:
                    st.error(f"Authentication Failed: {response.text}")
            except Exception as e:
                st.error(f"Cannot link to target API service container at {BACKEND_API_URL}. Details: {e}")

@st.dialog("Start Your Membership")
def show_registration_dialog():
    """Form-encodes new metrics to construct databases via Java api/register endpoint"""
    st.write("Choose your plan and establish account credentials.")
    plan = st.radio("Choose your plan", ["Basic - $8.99/mo", "Standard - $15.49/mo", "Premium - $22.99/mo"], index=2)
    email = st.text_input("Email address", value=st.session_state.signup_email).strip().lower()
    password = st.text_input("Create Password", type="password")

    if st.button("Register & Start Membership", use_container_width=True, type="primary"):
        if not re.match(EMAIL_REGEX, email):
            st.error("Please enter a valid email address.")
        elif len(password) < 6 or len(password) > 128:
            st.error("Password must be between 6 and 128 characters.")
        else:
            try:
                payload = {"email": email, "password": password}
                response = requests.post(f"{BACKEND_API_URL}/api/register", data=payload)

                if response.status_code == 201:
                    st.session_state.user_email = email
                    st.session_state.logged_in = True
                    st.session_state.signup_email = ""
                    st.success("Account created successfully!")
                    st.rerun()
                else:
                    st.error(f"Registration Error: {response.text}")
            except Exception as e:
                st.error(f"Cannot link to target API service container. Details: {e}")

# =========================================================================
# 3. INTERACTION FEEDS & PLATFORM WORKSPACES
# =========================================================================

def landing_page():
    nav_col1, nav_col2 = st.columns(2)
    with nav_col1:
        st.markdown('<div class="brand-title">NETCHILL</div>', unsafe_allow_html=True)
    with nav_col2:
        if st.button("Sign In", use_container_width=True, type="primary"):
            show_login_dialog()

    st.write("")
    st.markdown('<p style="color: #E50914; font-weight: 700; text-transform: uppercase;">New & trending</p>', unsafe_allow_html=True)
    st.markdown('<h1 class="hero-title">Unlimited movies, TV shows, and more.</h1>', unsafe_allow_html=True)
    st.markdown('<h5>Watch anywhere. Cancel anytime.</h5>', unsafe_allow_html=True)

    st.write("")
    col_em, col_btn = st.columns(2)
    with col_em:
        hero_email = st.text_input("Email address", placeholder="Email address", label_visibility="collapsed", key="hero_email_input")
    with col_btn:
        if st.button("Get Started", use_container_width=True, type="primary"):
            clean_email = hero_email.strip()
            if not re.match(EMAIL_REGEX, clean_email):
                st.error("Please enter a valid email address.")
            else:
                st.session_state.signup_email = clean_email
                show_registration_dialog()

def dashboard_page():
    view_selection = st.radio("Filter Content Matrix", ["Home", "Series", "Movies"], horizontal=True, label_visibility="collapsed")
    color_emoji = "🟡" if st.session_state.profile_color == "amber" else "🔴" if st.session_state.profile_color == "pink" else "🔵"
    st.markdown(f"### {color_emoji} Active Session: **{st.session_state.current_profile}**")

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
        {"name": "Alex", "color": "amber", "avatar": "🟡"},
        {"name": "Mia", "color": "pink", "avatar": "🔴"},
        {"name": "Kids", "color": "blue", "avatar": "🔵"}
    ]
    for idx, p in enumerate(profiles_data):
        with p_cols[idx]:
            st.markdown(f"""
            <div class="profile-card">
                <h1 style='font-size:4rem; margin:0;'>{p['avatar']}</h1>
                <h3>{p['name']}</h3>
            </div>
            """, unsafe_allow_html=True)
            if st.button(f"Activate {p['name']}", key=f"set_prof_{p['name']}", use_container_width=True):
                st.session_state.current_profile = p['name']
                st.session_state.profile_color = p['color']
                st.toast(f"Switched profile context directly to {p['name']}!")
                st.rerun()

def account_page():
    st.markdown('<div class="section-title">Account Details</div>', unsafe_allow_html=True)
    st.write("---")
    col_lbl, col_val = st.columns(2)
    with col_lbl:
        st.markdown("**Membership Tier**\n\n**Registered User Email**\n\n**Video Resolution Profile**\n\n**Billing Account Record**")
    with col_val:
        st.markdown(f"Premium Framework\n\n{st.session_state.user_email}\n\n4K Ultra-HD Streaming Active\n\nVisa •••• 2431")

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
        st.caption(st.session_state.user_email)
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