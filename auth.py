import os
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from config import SCOPES, CREDENTIALS_FILE


def authenticate_gmail(email_id: str):
    """
    Authenticate with Gmail for the given email address.
    Returns a Gmail API service object.
    Raises on failure — callers handle display.
    """
    creds = None
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
            flow = InstalledAppFlow.from_client_secrets_file(
                CREDENTIALS_FILE, SCOPES
            )
            creds = flow.run_local_server(port=0)

        with open(token_file, 'w') as token:
            token.write(creds.to_json())

    return build('gmail', 'v1', credentials=creds)
