from datetime import timedelta
from config import FILE_TYPE_EXTENSIONS

# Gmail label/mailbox tokens
MAILBOX_LABELS = {
    'All Mail':   None,           # no label filter
    'Inbox':      'in:inbox',
    'Sent':       'in:sent',
    'Starred':    'is:starred',
    'Drafts':     'in:drafts',
    'Trash':      'in:trash',
    'Spam':       'in:spam',
    'Social':     'category:social',
    'Purchases':  'category:purchases',
    'Updates':    'category:updates',
    'Forums':     'category:forums',
    'Promotions': 'category:promotions',
}

# Labels that can be excluded (exclude_labels list)
EXCLUDABLE_LABELS = [k for k in MAILBOX_LABELS if k != 'All Mail']


def build_email_query(
    sender=None,
    recipient=None,
    keyword=None,
    exclude_keywords=None,   # str — words/phrases to exclude
    start_date=None,
    end_date=None,
    mailbox=None,            # one of MAILBOX_LABELS keys
    has_attachment=False,
    file_types=None,
    skip_replies=False,
    skip_forwards=False,
    exclude_labels=None,     # list of MAILBOX_LABELS keys to exclude
):
    query_parts = []

    # ── Mailbox scope ──────────────────────────────────────────────────────
    if mailbox and mailbox != 'All Mail':
        token = MAILBOX_LABELS.get(mailbox)
        if token:
            query_parts.append(token)

    # ── Participants ───────────────────────────────────────────────────────
    if sender:
        query_parts.append(f'from:"{sender}"')
    if recipient:
        query_parts.append(f'to:"{recipient}"')

    # ── Keywords ──────────────────────────────────────────────────────────
    if keyword:
        query_parts.append(keyword)
    if exclude_keywords:
        for word in exclude_keywords.split():
            query_parts.append(f'-{word}')

    # ── Dates ─────────────────────────────────────────────────────────────
    if start_date:
        query_parts.append(f'after:{start_date - timedelta(days=1)}')
    if end_date:
        query_parts.append(f'before:{end_date + timedelta(days=1)}')

    # ── Attachments ───────────────────────────────────────────────────────
    if has_attachment:
        query_parts.append('has:attachment')
    if file_types:
        extensions = []
        for ft in file_types:
            extensions.extend(FILE_TYPE_EXTENSIONS.get(ft, []))
        if extensions:
            ext_query = ' OR '.join(f'filename:{e.lstrip(".")}' for e in extensions)
            query_parts.append(f'({ext_query})')

    # ── Skip filters ──────────────────────────────────────────────────────
    if skip_replies:
        query_parts.append('-is:reply')
    if skip_forwards:
        query_parts.append('-subject:"Fwd:"')

    # ── Exclude labels ────────────────────────────────────────────────────
    if exclude_labels:
        for label in exclude_labels:
            token = MAILBOX_LABELS.get(label)
            if token:
                # Negate the token: "in:sent" → "-in:sent", "is:starred" → "-is:starred"
                query_parts.append(f'-{token}')

    return ' '.join(query_parts)
