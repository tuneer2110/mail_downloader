"""
auth.py
───────
Unified authentication for both local and Streamlit Cloud environments.

Local:
  - Reads credentials from credentials.json on disk
  - Opens a browser window for OAuth approval
  - Saves token to token_<username>.json for reuse

Streamlit Cloud:
  - Reads credentials from st.secrets["google_credentials"]["json"]
  - Cannot open a browser, so uses the manual code flow:
      1. Shows the user a Google auth URL to visit
      2. User approves and copies the auth code shown by Google
      3. User pastes the code into a text input in the app
      4. Token is stored in st.session_state (lasts for the session)
  - st.session_state means re-auth is needed each new browser session
    on the cloud, which is acceptable for a personal tool

Environment detection:
  - If st.secrets has a "google_credentials" key → cloud mode
  - Otherwise → local mode
  No env vars to set, no config to change.
"""

import os
import json
import streamlit as st
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from config import SCOPES, CREDENTIALS_FILE


# ── Environment detection ─────────────────────────────────────────────────────

def _is_cloud() -> bool:
    """True when running on Streamlit Cloud (secrets key present)."""
    try:
        return "google_credentials" in st.secrets
    except Exception:
        return False


# ── Local auth ────────────────────────────────────────────────────────────────

def _authenticate_local(email_id: str):
    """Standard local flow — browser popup, token saved to disk."""
    creds      = None
    token_file = f"token_{email_id.split('@')[0]}.json"

    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)

    if not creds or not creds.valid:
        needs_new_login = True

        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                needs_new_login = False
            except Exception:
                if os.path.exists(token_file):
                    os.remove(token_file)

        if needs_new_login:
            flow  = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(token_file, 'w') as f:
            f.write(creds.to_json())

    return build('gmail', 'v1', credentials=creds)


# ── Cloud auth ────────────────────────────────────────────────────────────────

def _get_cloud_flow():
    """Build an InstalledAppFlow from credentials stored in st.secrets."""
    creds_json = st.secrets["google_credentials"]["json"]
    creds_dict = json.loads(creds_json)
    return InstalledAppFlow.from_client_config(creds_dict, SCOPES)


def _authenticate_cloud(email_id: str):
    """
    Manual code flow for Streamlit Cloud.

    Two-pass approach using session_state:
      Pass 1 — generate the auth URL and show it to the user with a
               text input for the code. Return None to signal "not done yet".
      Pass 2 — user has pasted a code; exchange it for a token and return
               the service object.

    app.py checks for None and shows a waiting message instead of
    proceeding to the search UI.
    """
    session_key = f'cloud_token_{email_id.split("@")[0]}'

    # Already have a valid token in this session
    if session_key in st.session_state:
        creds = Credentials.from_authorized_user_info(
            json.loads(st.session_state[session_key]), SCOPES
        )
        if creds.valid:
            return build('gmail', 'v1', credentials=creds)
        if creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                st.session_state[session_key] = creds.to_json()
                return build('gmail', 'v1', credentials=creds)
            except Exception:
                del st.session_state[session_key]

    # Generate auth URL and show it
    flow     = _get_cloud_flow()
    auth_url, _ = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
    )

    st.markdown("**Step 1 — Authorise access**")
    st.markdown(
        f"[Click here to authorise Gmail access]({auth_url})",
        unsafe_allow_html=False,
    )
    st.caption(
        "You'll see a warning that the app isn't verified — click "
        "**Advanced → Go to [app name]** to continue. "
        "Google will then show you a code."
    )

    st.markdown("**Step 2 — Paste the code below**")
    auth_code = st.text_input(
        "Authorisation code from Google",
        key='cloud_auth_code',
        placeholder="Paste the code Google showed you",
    )

    if st.button("Submit code", key='submit_auth_code'):
        if not auth_code.strip():
            st.warning("Please paste the authorisation code first.")
            return None
        try:
            flow.fetch_token(code=auth_code.strip())
            creds = flow.credentials
            st.session_state[session_key] = creds.to_json()
            st.rerun()
        except Exception as e:
            st.error(f"Code exchange failed: {e}")
            return None

    return None   # Waiting for user to complete the flow


# ── Public entry point ────────────────────────────────────────────────────────

def authenticate_gmail(email_id: str):
    """
    Authenticate with Gmail. Returns a service object or None.

    Returns None only in the cloud flow while waiting for the user to
    paste their auth code — app.py should check for None and st.stop().
    In the local flow it either succeeds or raises.
    """
    if _is_cloud():
        return _authenticate_cloud(email_id)
    return _authenticate_local(email_id)