from email.utils import parsedate_to_datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from googleapiclient.discovery import build


# ── Search ──────────────────────────────────────────────────────────────────

def search_emails(service, query: str, max_results: int | None = None) -> list:
    """
    Return list of {id, threadId} dicts. Handles Gmail pagination.
    max_results=None fetches everything.
    """
    all_messages = []
    page_token   = None
    try:
        while True:
            results  = service.users().messages().list(
                userId='me', q=query, pageToken=page_token,
            ).execute()
            messages = results.get('messages', [])
            all_messages.extend(messages)
            if max_results and len(all_messages) >= max_results:
                return all_messages[:max_results]
            page_token = results.get('nextPageToken')
            if not page_token:
                break
    except Exception:
        return []
    return all_messages


# ── Single metadata fetch ────────────────────────────────────────────────────

def get_email_metadata(service, message_id: str) -> dict:
    response = service.users().messages().get(
        userId='me', id=message_id,
        format='metadata',
        metadataHeaders=['Subject', 'From', 'To', 'Date'],
    ).execute()
    headers    = response.get('payload', {}).get('headers', [])
    header_map = {h['name']: h['value'] for h in headers}
    raw_date   = header_map.get('Date', '')
    try:
        formatted_date = parsedate_to_datetime(raw_date).strftime('%d %b %y %H:%M')
    except Exception:
        formatted_date = raw_date
    return {
        'id':      message_id,
        'From':    header_map.get('From', ''),
        'To':      header_map.get('To', ''),
        'Date':    formatted_date,
        'Subject': header_map.get('Subject', ''),
    }


# ── Thread-safe single fetch (builds its own service) ────────────────────────

def _fetch_one(creds, message_id: str) -> dict:
    thread_service = build('gmail', 'v1', credentials=creds)
    return get_email_metadata(thread_service, message_id)


# ── Streaming batch fetch ────────────────────────────────────────────────────

def stream_emails_metadata(
    service,
    messages: list,
    on_result,          # callable(index, metadata_dict) — called as each result arrives
    stop_flag,          # callable() → bool — return True to abort
    max_workers: int = 5,
):
    """
    Fetch metadata for all messages in parallel, calling on_result() as each
    completes. Stops early if stop_flag() returns True.

    on_result(index, dict) lets the caller insert results at the correct
    position so the table stays in original search-result order.
    """
    creds = service._http.credentials
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_index = {
            executor.submit(_fetch_one, creds, msg['id']): i
            for i, msg in enumerate(messages)
        }
        for future in as_completed(future_to_index):
            if stop_flag():
                executor.shutdown(wait=False, cancel_futures=True)
                return
            idx = future_to_index[future]
            try:
                result = future.result()
            except Exception:
                result = {
                    'id': messages[idx]['id'], 'From': '', 'To': '',
                    'Date': '', 'Subject': '(failed to load)',
                }
            on_result(idx, result)


# ── Legacy batch (kept for compatibility) ────────────────────────────────────

def get_emails_metadata_batch(service, messages, on_result=None, max_workers=5):
    total   = len(messages)
    results = [None] * total
    done    = [0]

    def _on(idx, data):
        results[idx] = data
        done[0] += 1
        if on_result:
            on_result(done[0], total)

    stream_emails_metadata(service, messages, _on, stop_flag=lambda: False,
                           max_workers=max_workers)
    return results
