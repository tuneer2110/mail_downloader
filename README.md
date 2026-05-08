# Gmail Content Downloader

A local Streamlit app that connects to your Gmail account via the official Google API and lets you search, browse, and export emails — metadata, attachments, and full email content as PDFs — into a structured ZIP archive.

---

## Capabilities

- **Search** across any Gmail mailbox or category (Inbox, Sent, Starred, Drafts, Spam, Social, Promotions, etc.) with filters for sender, recipient, keyword, date range, attachment type, and more
- **Advanced filters** — exclude keywords, exclude specific mailbox categories, skip replies and forwards
- **Progressive results** — email metadata loads in the background as results stream into a paginated table; stop loading at any time
- **Flexible export** — choose any combination of:
  - Metadata table as a dated `.xlsx` file with clickable hyperlinks to exported files
  - Attachments organised by month and file type
  - Full email threads as PDFs (entire chain in one file)
- **Export scope** — download your selection, all loaded results, or all matched results
- **Read-only** — uses `gmail.readonly` scope; the app never modifies or deletes anything

---

## Prerequisites

- Python 3.11 or later
- A Google account
- A Google Cloud project with the Gmail API enabled (setup below)

---

## Google Cloud Console Setup

Follows these steps exactly once per Google account you want to use.

### 1. Create a project

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Click the project dropdown at the top → **New Project**
3. Give it a name (e.g. `gmail-downloader`) and click **Create**
4. Make sure the new project is selected in the dropdown before continuing

### 2. Enable the Gmail API

1. In the left sidebar go to **APIs & Services → Library**
2. Search for **Gmail API** and click it
3. Click **Enable**

### 3. Configure the OAuth consent screen

1. Go to **APIs & Services → OAuth consent screen**
2. Choose **External** and click **Create**
3. Fill in the required fields:
   - **App name** — anything you like, e.g. `Gmail Downloader`
   - **User support email** — your email address
   - **Developer contact email** — your email address
4. Click **Save and Continue** through the Scopes screen (no need to add scopes manually — the app requests `gmail.readonly` at runtime)
5. On the **Test users** screen, click **Add users** and add the Gmail address(es) you want to use the app with. This is required while the app is in Testing mode.
6. Click **Save and Continue**, then **Back to Dashboard**

### 4. Create OAuth credentials

1. Go to **APIs & Services → Credentials**
2. Click **Create Credentials → OAuth client ID**
3. Set **Application type** to **Desktop app**
4. Give it a name and click **Create**
5. Click **Download JSON** on the confirmation screen (or download it later from the credentials list)
6. Rename the downloaded file to exactly `credentials.json`
7. Place `credentials.json` in the root folder of this project (same level as `app.py`)

> **Keep `credentials.json` private.** It is listed in `.gitignore` and should never be committed to any repository.

---

## Local Setup

### 1. Clone the repo

```bash
git clone https://github.com/YOUR_USERNAME/gmail-content-downloader.git
cd gmail-content-downloader
```

### 2. Create and activate a virtual environment

```bash
python -m venv venv

# macOS / Linux
source venv/bin/activate

# Windows
venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Add your credentials file

Place your `credentials.json` file (downloaded from Google Cloud Console in the steps above) in the project root.

### 5. Run the app

```bash
streamlit run app.py
```

The app will open in your browser at `http://localhost:8501`.

### 6. First-time authentication

The first time you click **Connect to Gmail**, a browser window will open asking you to log in with your Google account and grant the app read-only access to Gmail. After approving, a `token_<username>.json` file is saved locally so you don't have to re-authenticate on subsequent runs.

> If you see a warning saying **"Google hasn't verified this app"**, click **Advanced → Go to [app name] (unsafe)**. This is expected for apps in Testing mode that haven't gone through Google's verification process.

---

## Deploying on Streamlit Community Cloud

1. Push the repository to GitHub (all files except `credentials.json` and `token_*.json`, which are in `.gitignore`)
2. Go to [share.streamlit.io](https://share.streamlit.io) and sign in with GitHub
3. Click **New app**, select your repo and set the main file to `app.py`
4. Before deploying, go to **Advanced settings → Secrets** and add your credentials file contents as a secret:

```toml
[google_credentials]
contents = '''
PASTE THE ENTIRE CONTENTS OF credentials.json HERE
'''
```

5. You will also need to update `auth.py` to read credentials from `st.secrets` instead of a local file when running on Streamlit Cloud. This is a small code change — raise an issue or PR if you need a guide for this.

> **Note:** Streamlit Cloud deployment requires an additional auth code change because the OAuth browser redirect flow (`run_local_server`) does not work in a cloud environment. Local use works out of the box.

---

## Project Structure

```
gmail-content-downloader/
├── app.py                  # Main Streamlit app — UI orchestration
├── auth.py                 # Gmail OAuth authentication
├── config.py               # Scopes, credentials filename, file type map
├── query_builder.py        # Builds Gmail API search query strings
├── email_service.py        # Gmail API calls — search and metadata fetch
├── download_service.py     # ZIP builder — attachments, PDFs, Excel metadata
├── ui_components.py        # Reusable Streamlit rendering functions
├── requirements.txt
├── README.md
├── .gitignore
├── credentials.json        # ← YOU provide this, never committed
└── token_*.json            # ← auto-generated on first auth, never committed
```

---

## .gitignore

Make sure your `.gitignore` includes at minimum:

```
credentials.json
token_*.json
venv/
__pycache__/
*.pyc
.env
```

---

## Known limitations

- The OAuth flow opens a local browser window on first run. This does not work on remote/headless servers without additional configuration.
- Streamlit Cloud deployment requires a modified auth flow (see Deployment section above).
- Very large exports (hundreds of emails with attachments) can be slow due to Gmail API rate limits. The progress bar and stop button let you manage this.

---
