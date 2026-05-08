"""
auth.py — unified local + Streamlit Cloud Gmail authentication.

Local:  reads credentials.json, opens browser, saves token_*.json to disk.
Cloud:  reads credentials from st.secrets, uses redirect flow where Google
        redirects back to the Streamlit app URL with a code in the query string.
        Token stored in st.session_state for the duration of the browser session.
"""

# Added for the Streamlit Cloud OAuth fix:
# the app encodes the user's email into a signed OAuth state value so the
# Google redirect can be completed even if Streamlit session_state resets.
import base64
import hashlib
import hmac
import json
import os
import secrets
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

def _get_flow(code_verifier: str | None = None):
    creds_dict = json.loads(st.secrets["google_credentials"]["json"])
    flow = Flow.from_client_config(
        creds_dict,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI,
        code_verifier=code_verifier,
        autogenerate_code_verifier=(code_verifier is None),
    )
    return flow


# OAuth loop fix:
# Earlier version relied on this pre-redirect session state:
#
#     auth_url, state = flow.authorization_url(access_type='offline', prompt='consent')
#     st.session_state['oauth_state'] = state
#     st.session_state['_pending_email'] = email_id
#
# That works locally, but Streamlit Cloud can lose session_state during the
# external Google redirect. These helpers put the email inside Google's returned
# state parameter, signed with the OAuth client secret so it cannot be tampered
# with by the browser.
#
# PKCE verifier fix:
# Google also expects the token exchange to include the same code_verifier that
# was used to create the login URL. Streamlit Cloud loses the original Flow
# object during the redirect, so the old code reached Google with a code but no
# verifier. The nonce below is fresh for each login; the verifier is derived
# from that nonce plus the app secret, so it is deterministic for one login but
# not a single hard-coded value shared by all users.
def _cloud_client_secret() -> str:
    creds_dict = json.loads(st.secrets["google_credentials"]["json"])
    client_config = creds_dict.get("web") or creds_dict.get("installed") or {}
    return client_config["client_secret"]


def _derive_code_verifier(email_id: str, nonce: str) -> str:
    digest = hmac.new(
        _cloud_client_secret().encode("utf-8"),
        f"{email_id}\0{nonce}".encode("utf-8"),
        hashlib.sha512,
    ).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _encode_state(email_id: str, nonce: str) -> str:
    payload = json.dumps(
        {"email": email_id, "nonce": nonce},
        separators=(",", ":"),
    ).encode("utf-8")
    body = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
    signature = hmac.new(
        _cloud_client_secret().encode("utf-8"),
        body.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()
    return f"{body}.{signature}"


def _decode_state(state: str) -> tuple[str, str]:
    try:
        body, signature = state.split(".", 1)
    except ValueError as exc:
        raise ValueError("Invalid OAuth state.") from exc

    expected = hmac.new(
        _cloud_client_secret().encode("utf-8"),
        body.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise ValueError("Invalid OAuth state signature.")

    padded = body + ("=" * (-len(body) % 4))
    payload = base64.urlsafe_b64decode(padded.encode("ascii"))
    state_data = json.loads(payload.decode("utf-8"))
    email_id = state_data.get("email")
    nonce = state_data.get("nonce")
    if not email_id:
        raise ValueError("OAuth state did not include an email address.")
    if not nonce:
        raise ValueError("OAuth state did not include a verifier nonce.")
    return email_id, nonce


def _authenticate_cloud(email_id: str | None):
    """
    Redirect-based OAuth flow for Streamlit Cloud.

    How it works:
      1. User clicks Connect — we generate a Google auth URL and redirect them there.
      2. Google redirects back to the Streamlit app URL with ?code=xxx in the query string.
      3. On that return load we detect the code, exchange it for a token, save to
         session_state, and proceed. No manual copy-paste needed.
    """
    params = st.query_params
    code  = params.get('code')
    state = params.get('state')

    # Earlier version checked:
    #
    #     if code and st.session_state.get('oauth_state') == state:
    #
    # That created a loop on Streamlit Cloud when oauth_state was lost after
    # Google redirected back. Now the signed state itself carries the email.
    code_verifier = None
    if code:
        try:
            email_id, nonce = _decode_state(state or "")
            code_verifier = _derive_code_verifier(email_id, nonce)
        except Exception as e:
            st.error(f"Authentication failed: {e}")
            st.query_params.clear()
            return None

    if not email_id:
        return None

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
    if code:
        # Exchange code for token
        try:
            flow = _get_flow(code_verifier=code_verifier)
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
    # Earlier version:
    #
    #     auth_url, state = flow.authorization_url(access_type='offline', prompt='consent')
    #     st.session_state['oauth_state'] = state
    #     st.session_state['_pending_email'] = email_id
    #
    # New version: send a signed state value through Google, so the return trip
    # has everything needed to finish auth without pre-redirect session_state.
    nonce = secrets.token_urlsafe(32)
    code_verifier = _derive_code_verifier(email_id, nonce)
    flow = _get_flow(code_verifier=code_verifier)
    auth_url, _ = flow.authorization_url(
        access_type='offline',
        prompt='consent',
        state=_encode_state(email_id, nonce),
    )

    st.markdown("**Authorise Gmail access**")
    st.markdown(f"[Click here to connect your Gmail account]({auth_url})")
    st.caption(
        "You'll be taken to Google to approve read-only access. "
        "After approving you'll be redirected back here automatically."
    )
    return None


# ── Public entry point ────────────────────────────────────────────────────────

def authenticate_gmail(email_id: str | None = None):
    """Returns a Gmail service object, or None if cloud auth is mid-flow."""
    if _is_cloud():
        return _authenticate_cloud(email_id)
    return _authenticate_local(email_id)
