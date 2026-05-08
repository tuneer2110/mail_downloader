from datetime import timedelta
from config import FILE_TYPE_EXTENSIONS


def build_email_query(
    sender=None,
    recipient=None,
    keyword=None,
    start_date=None,
    end_date=None,
    has_attachment=False,
    file_types=None,
    skip_replies=None,
    skip_forwards=None,
):
    query_parts = []

    if sender:
        query_parts.append(f'from:"{sender}"')
    if recipient:
        query_parts.append(f'to:"{recipient}"')
    if keyword:
        query_parts.append(keyword)

    if start_date:
        query_parts.append(f'after:{start_date - timedelta(days=1)}')
    if end_date:
        query_parts.append(f'before:{end_date + timedelta(days=1)}')

    # ── Attachments ────────────────────────────────────────────────────────
    if has_attachment:
        query_parts.append('has:attachment')

    if file_types:
        extensions = []
        for ft in file_types:
            extensions.extend(FILE_TYPE_EXTENSIONS.get(ft, []))
        if extensions:
            ext_query = ' OR '.join(
                f'filename:{ext.lstrip(".")}' for ext in extensions
            )
            query_parts.append(f'({ext_query})')

    # ── Skip filters ────────────────────────────────────────────────────────
    if skip_replies:
        query_parts.append('-is:reply')
    if skip_forwards:
        query_parts.append('-subject:"Fwd:"')

    return ' '.join(query_parts)
