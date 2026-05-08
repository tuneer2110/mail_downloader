"""
auth.py — unified local + Streamlit Cloud Gmail authentication.

Local:  reads credentials.json, opens browser, saves token_*.json to disk.
Cloud:  reads credentials from st.secrets, uses redirect flow where Google
        redirects back to the Streamlit app URL with a code in the query string.
        Token stored in st.session_state for the duration of the browser session.
"""

import os
import json
import streamlit as st
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow, Flow
from googleapiclient.discovery import build

from config import SCOPES, CREDENTIALS_FILE

REDIRECT_URI = 'https://maildownloader-tc2110.streamlit.app/'


# ── Environment detection ─────────────────────────────────────────────────────

def _is_cloud() -> bool:
    try:
        return "google_credentials" in st.secrets
    except Exception:
        return False


# ── Local auth ────────────────────────────────────────────────────────────────

def _authenticate_local(email_id: str):
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

def _get_flow():
    creds_dict = json.loads(st.secrets["google_credentials"]["json"])
    flow = Flow.from_client_config(creds_dict, scopes=SCOPES, redirect_uri=REDIRECT_URI)
    return flow


def _authenticate_cloud(email_id: str):
    """
    Redirect-based OAuth flow for Streamlit Cloud.

    How it works:
      1. User clicks Connect — we generate a Google auth URL and redirect them there.
      2. Google redirects back to the Streamlit app URL with ?code=xxx in the query string.
      3. On that return load we detect the code, exchange it for a token, save to
         session_state, and proceed. No manual copy-paste needed.
    """
    token_key = f'cloud_token_{email_id.split("@")[0]}'

    # ── Already have a token — validate and return service ────────────────
    if token_key in st.session_state:
        try:
            creds = Credentials.from_authorized_user_info(
                json.loads(st.session_state[token_key]), SCOPES
            )
            if creds.valid:
                return build('gmail', 'v1', credentials=creds)
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
                st.session_state[token_key] = creds.to_json()
                return build('gmail', 'v1', credentials=creds)
        except Exception:
            pass
        # Token invalid — clear it and re-auth
        del st.session_state[token_key]

    # ── Check if Google just redirected back with a code ──────────────────
    params = st.query_params
    code  = params.get('code')
    state = params.get('state')

    if code and st.session_state.get('oauth_state') == state:
        # Exchange code for token
        try:
            flow = _get_flow()
            flow.fetch_token(code=code)
            creds = flow.credentials
            st.session_state[token_key] = creds.to_json()
            # Save email so app.py can restore it after rerun
            st.session_state['authed_email'] = email_id
            # Clear the code from the URL
            st.query_params.clear()
            return build('gmail', 'v1', credentials=creds)
        except Exception as e:
            st.error(f"Failed to exchange auth code: {e}")
            st.query_params.clear()
            return None

    # ── No token, no code — send user to Google ───────────────────────────
    flow = _get_flow()
    auth_url, state = flow.authorization_url(access_type='offline', prompt='consent')
    st.session_state['oauth_state']      = state
    st.session_state['_pending_email']   = email_id

    st.markdown("**Authorise Gmail access**")
    st.markdown(f"[Click here to connect your Gmail account]({auth_url})")
    st.caption(
        "You'll be taken to Google to approve read-only access. "
        "After approving you'll be redirected back here automatically."
    )
    return None


# ── Public entry point ────────────────────────────────────────────────────────

def authenticate_gmail(email_id: str):
    """Returns a Gmail service object, or None if cloud auth is mid-flow."""
    if _is_cloud():
        return _authenticate_cloud(email_id)
    return _authenticate_local(email_id)