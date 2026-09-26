import os
import streamlit as st
import re
import requests

# =========================================================================
# 1. SETUP & UTILITY HOOKS
# =========================================================================
st.set_page_config(page_title="NETCHILL | Watch Movies and TV Shows Online", page_icon="🍿", layout="wide")

# Automatically extracts Render's environment variable, dropping down to localhost for local testing
BACKEND_API_URL = "https://onrender.com"

st.markdown("""
    <style>
    .stApp { background-color: #141414; color: #FFFFFF; font-family: 'Inter', sans-serif; }
    hr { border-color: #333; }
    .brand-title { color: #E50914 !important; font-weight: 900; font-size: 2.2rem; letter-spacing: -1px; }
    .hero-title { font-size: 3.5rem; font-weight: 800; line-height: 1.1; margin-bottom: 10px; color: #FFFFFF; }
    .section-title { font-size: 1.8rem; font-weight: 700; margin-top: 20px; margin-bottom: 15px; color: #fff; }
    .profile-card { text-align: center; background: #222; padding: 25px; border-radius: 8px; border: 2px solid transparent; }
    .profile-card:hover { border-color: #E50914; }
    div.stButton > button {
        background-color: #E50914 !important; color: white !important;
        border: none !important; padding: 0.5rem 1.5rem !important;
        font-weight: 600 !important; border-radius: 4px !important;
    }
    div.stButton > button:hover { background-color: #B81D24 !important; }
    </style>
""", unsafe_allow_html=True)

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
    
    if st.button("Sign In", use_container_width=True):
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
    
    if st.button("Register & Start Membership", use_container_width=True):
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
    nav_col1, nav_col2 = st.columns()
    with nav_col1:
        st.markdown('<div class="brand-title">NETCHILL</div>', unsafe_allow_html=True)
    with nav_col2:
        if st.button("Sign In", use_container_width=True):
            show_login_dialog()

    st.write("")
    st.markdown('<p style="color: #E50914; font-weight: 700; text-transform: uppercase;">New & trending</p>', unsafe_allow_html=True)
    st.markdown('<h1 class="hero-title">Unlimited movies, TV shows, and more.</h1>', unsafe_allow_html=True)
    st.markdown('<h5>Watch anywhere. Cancel anytime.</h5>', unsafe_allow_html=True)
    
    st.write("")
    col_em, col_btn = st.columns()
    with col_em:
        hero_email = st.text_input("Email address", placeholder="Email address", label_visibility="collapsed", key="hero_email_input")
    with col_btn:
        if st.button("Get Started", use_container_width=True):
            clean_email = hero_email.strip()
            if not re.match(EMAIL_REGEX, clean_email):
                st.error("Please enter a valid email address.")
            else:
                st.session_state.signup_email = clean_email
                show_registration_dialog()

def dashboard_page():
    view_selection = st.radio("Filter Content Matrix", ["Home", "Series", "Movies"], horizontal=True, label_visibility="collapsed")
    color_emoji = "环境" if st.session_state.profile_color == "amber" else "🔴" if st.session_state.profile_color == "pink" else "🔵"
    st.markdown(f"### {color_emoji} Active Session: **{st.session_state.current_profile}**")
    
    if view_selection in ["Home", "Movies"]:
        st.markdown('<div class="section-title">Movies</div>', unsafe_allow_html=True)
        m_cols = st.columns(4)
        movies = ["Midnight Run", "Skyline", "Crimson Tide", "Neon Glow"]
        for idx, item in enumerate(movies):
            with m_cols[idx]:
                st.image(f"https://placeholder.com{item.replace(' ', '+')}", use_container_width=True)
                st.markdown(f"**{item}**")
                st.button("Play Video", key=f"mov_{idx}")

    if view_selection in ["Home", "Series"]:
        st.markdown('<div class="section-title">TV Shows</div>', unsafe_allow_html=True)
        t_cols = st.columns(4)
        shows = ["Nightfall", "Signal Ridge", "Glass City", "Thorn Lane"]
        for idx, item in enumerate(shows):
            with t_cols[idx]:
                st.image(f"https://placeholder.com{item.replace(' ', '+')}", use_container_width=True)
                st.markdown(f"**{item}**")
                st.button("Watch Episode", key=f"tv_{idx}")

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
                st.toast(f"Switched profilecontext directly to {p['name']}!")
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
