"""
app.py  –  Gmail Content Downloader
Run with:  streamlit run app.py
"""

import time
import streamlit as st
from datetime import datetime

from config import FILE_TYPE_EXTENSIONS
from auth import authenticate_gmail
from query_builder import build_email_query
from email_service import search_emails, stream_emails_metadata
from download_service import build_export_zip_streaming
from ui_components import (
    inject_styles, reset_results_state, render_results_table,
)

st.set_page_config(page_title="Gmail Content Downloader", page_icon="✉️", layout="wide")
inject_styles()

PREVIEW_OPTIONS = ["10", "25", "50", "100", "All"]


def main():
    st.title("Gmail Content Downloader")

    # ═══════════════════════════════════════════════════════════════════════
    # STEP 1 — AUTHENTICATION
    # ═══════════════════════════════════════════════════════════════════════
    if 'service' not in st.session_state:
        st.header("Step 1 — Authenticate")
        email_id = st.text_input("Gmail address", placeholder="you@gmail.com", key='email_id')
        if st.button("Connect to Gmail"):
            if not email_id:
                st.warning("Please enter your email address first.")
            else:
                try:
                    with st.spinner("Authenticating…"):
                        svc = authenticate_gmail(email_id)
                    st.session_state.service      = svc
                    st.session_state.authed_email = email_id
                    st.rerun()
                except Exception as e:
                    st.error(f"Authentication failed: {e}")
        st.stop()

    service = st.session_state.service
    st.caption(f"✓ Connected as **{st.session_state.get('authed_email', '')}**")

    # ═══════════════════════════════════════════════════════════════════════
    # STEP 2 — SEARCH
    # ═══════════════════════════════════════════════════════════════════════
    st.divider()
    st.header("Step 2 — Search")

    col_start, col_end = st.columns(2)
    with col_start:
        start_date = st.date_input("Start date", max_value=datetime.today())
    with col_end:
        end_date = st.date_input("End date", min_value=start_date, max_value=datetime.today())

    col_from, col_to = st.columns(2)
    with col_from:
        sender    = st.text_input("From", placeholder="name or email@example.com")
    with col_to:
        recipient = st.text_input("To",   placeholder="name or email@example.com")

    keyword = st.text_input("Keyword", placeholder="Subject or body text")

    has_attachments  = st.checkbox("Has attachments")
    attachment_types = []
    if has_attachments:
        attachment_types = st.multiselect("Attachment types", list(FILE_TYPE_EXTENSIONS.keys()))

    col_s1, col_s2 = st.columns(2)
    with col_s1: skip_replies  = st.checkbox("Skip replies")
    with col_s2: skip_forwards = st.checkbox("Skip forwards")

    _, btn_col, _ = st.columns([1, 2, 1])
    with btn_col:
        search_clicked = st.button("🔍  Search", use_container_width=True)

    if search_clicked:
        query = build_email_query(
            sender=sender, recipient=recipient, keyword=keyword,
            start_date=start_date, end_date=end_date,
            has_attachment=has_attachments, file_types=attachment_types,
            skip_replies=skip_replies, skip_forwards=skip_forwards,
        )
        with st.expander("Generated query", expanded=False):
            st.code(query, language=None)

        with st.spinner("Searching…"):
            # Always fetch all matching IDs — this is fast (index-only)
            messages = search_emails(service, query, max_results=None)

        if not messages:
            st.info("No messages found.")
            reset_results_state()
            st.stop()

        reset_results_state()
        st.session_state.messages_list = messages
        st.session_state.total_found   = len(messages)
        st.rerun()

    # ═══════════════════════════════════════════════════════════════════════
    # PREVIEW LIMIT — shown after search returns IDs, before loading metadata
    # ═══════════════════════════════════════════════════════════════════════
    messages_list = st.session_state.get('messages_list', [])
    if not messages_list:
        st.stop()

    total_found = st.session_state.get('total_found', len(messages_list))

    # Only show the selector when we have results
    pc1, pc2, _ = st.columns([2, 2, 3])
    with pc1:
        st.caption(f"**{total_found}** match{'es' if total_found != 1 else ''} found")
    with pc2:
        preview_choice = st.selectbox(
            "Load metadata for",
            PREVIEW_OPTIONS,
            index=1,          # default 25
            key='preview_limit',
            label_visibility='collapsed',
        )
    preview_n = None if preview_choice == "All" else int(preview_choice)
    load_list = messages_list if preview_n is None else messages_list[:preview_n]

    # If preview limit changed, reset emails_data so we reload
    prev_preview = st.session_state.get('_last_preview')
    if prev_preview != preview_choice:
        st.session_state.emails_data  = {}
        st.session_state.loading_done = False
        st.session_state.stop_loading = False
        st.session_state._last_preview = preview_choice

    # ═══════════════════════════════════════════════════════════════════════
    # PROGRESSIVE METADATA LOADING
    # ═══════════════════════════════════════════════════════════════════════
    emails_data  = st.session_state.get('emails_data', {})
    loading_done = st.session_state.get('loading_done', False)
    stop_loading = st.session_state.get('stop_loading', False)
    load_target  = len(load_list)

    if not loading_done and not stop_loading:
        remaining = [(i, m) for i, m in enumerate(load_list) if i not in emails_data]

        if remaining:
            load_status = st.empty()
            load_bar    = st.empty()
            stop_col, _ = st.columns([1, 4])
            with stop_col:
                if st.button("⏹ Stop loading", key='stop_btn'):
                    st.session_state.stop_loading = True
                    st.rerun()

            already = len(emails_data)
            load_status.caption(f"Loading details — {already} of {load_target}")
            load_bar.progress(already / load_target if load_target else 1.0)

            BATCH = 10
            batch      = remaining[:BATCH]
            batch_msgs = [m for _, m in batch]
            batch_idxs = [i for i, _ in batch]
            collected  = {}

            stream_emails_metadata(
                service, batch_msgs,
                on_result=lambda idx, meta: collected.__setitem__(idx, meta),
                stop_flag=lambda: st.session_state.get('stop_loading', False),
            )

            new_data = dict(emails_data)
            for local_i, global_i in enumerate(batch_idxs):
                if local_i in collected:
                    new_data[global_i] = collected[local_i]
            st.session_state.emails_data = new_data

            if len(new_data) >= load_target:
                st.session_state.loading_done = True
                load_status.empty()
                load_bar.empty()
            else:
                time.sleep(0.05)
                st.rerun()
        else:
            st.session_state.loading_done = True

    # ═══════════════════════════════════════════════════════════════════════
    # STEP 3 — RESULTS TABLE
    # ═══════════════════════════════════════════════════════════════════════
    emails_data = st.session_state.get('emails_data', {})
    if not emails_data:
        st.stop()

    st.divider()
    st.header("Step 3 — Select emails")

    loading_done = st.session_state.get('loading_done', False)
    stop_loading = st.session_state.get('stop_loading', False)
    if not loading_done and not stop_loading:
        st.caption("⏳ Still loading — table updates as results arrive.")
    elif stop_loading and not loading_done:
        st.caption(f"⏹ Stopped at {len(emails_data)} of {load_target} — you can still select and export.")

    render_results_table(emails_data, load_target)

    # ═══════════════════════════════════════════════════════════════════════
    # STEP 4 — DOWNLOAD
    # ═══════════════════════════════════════════════════════════════════════
    st.divider()
    st.header("Step 4 — Download")

    # Read selection fresh from session_state every render
    selected_ids = dict(st.session_state.get('selected_ids', {}))
    n_sel        = len(selected_ids)
    all_loaded   = [emails_data[i] for i in sorted(emails_data.keys())]
    n_loaded     = len(all_loaded)
    messages_by_id = {m['id']: m for m in messages_list}

    def _with_thread(em):
        e = dict(em)
        if 'threadId' not in e:
            e['threadId'] = messages_by_id.get(e['id'], {}).get('threadId', e['id'])
        return e

    # ── What to include ───────────────────────────────────────────────────
    download_options = st.multiselect(
        "What to include in export",
        ["Metadata table", "Attachments", "Email content (PDF)"],
        default=["Metadata table"],
        key='download_options',
    )
    if not download_options:
        st.caption("Choose at least one option above.")
        st.stop()

    include_metadata    = "Metadata table"      in download_options
    include_attachments = "Attachments"         in download_options
    include_bodies      = "Email content (PDF)" in download_options

    # ── Scope ─────────────────────────────────────────────────────────────
    # Store scope in session_state so it survives reruns caused by the
    # Prepare button — reading it from the radio directly at button-click
    # time is unreliable because Streamlit processes widgets top-to-bottom
    # and the radio may not yet have committed its value.
    if n_sel > 0:
        scope = st.radio(
            "Export scope",
            ["Download selection", "Download all loaded results"],
            index=0,
            horizontal=True,
            key='export_scope',
        )
    else:
        scope = "Download all loaded results"
        st.caption("No emails selected — exporting all loaded results.")

    # Persist scope explicitly so the Prepare handler reads the committed value
    st.session_state['_export_scope_committed'] = scope

    if scope == "Download selection":
        export_emails = [_with_thread(em) for em in all_loaded if em['id'] in selected_ids]
    else:
        export_emails = [_with_thread(em) for em in all_loaded]

    scope_label = f"{len(export_emails)} email{'s' if len(export_emails) != 1 else ''}"
    st.caption(f"Will export **{scope_label}** — {', '.join(download_options)}")

    # ── Prepare + progress ────────────────────────────────────────────────
    can_export = bool(export_emails)

    if st.button("Prepare export", key='prep_export', disabled=not can_export):
        # Re-read scope from the committed value to avoid timing issues
        committed_scope = st.session_state.get('_export_scope_committed', scope)
        if committed_scope == "Download selection":
            final_emails = [_with_thread(em) for em in all_loaded
                           if em['id'] in st.session_state.get('selected_ids', {})]
        else:
            final_emails = [_with_thread(em) for em in all_loaded]

        if not final_emails:
            st.warning("No emails to export — check your selection.")
        else:
            prog_text = st.empty()
            prog_bar  = st.empty()
            stop_dl_col, _ = st.columns([1, 4])
            with stop_dl_col:
                # Render the stop button placeholder — the button itself is
                # inside the streaming loop in download_service
                pass

            prog_text.caption("Preparing export…")
            prog_bar.progress(0.0)

            stop_download = [False]

            def _dl_progress(done, total, phase):
                if total:
                    prog_bar.progress(done / total)
                prog_text.caption(f"{phase} — {done} of {total}")

            try:
                zip_bytes = build_export_zip_streaming(
                    service             = service,
                    emails_data         = all_loaded,
                    selected_emails     = final_emails,
                    include_metadata    = include_metadata,
                    include_attachments = include_attachments,
                    include_bodies      = include_bodies,
                    on_progress         = _dl_progress,
                    stop_flag           = lambda: stop_download[0],
                )
                prog_text.empty()
                prog_bar.empty()
                st.session_state.export_zip   = zip_bytes
                st.session_state.export_label = _export_label(download_options)
            except RuntimeError as e:
                prog_text.empty(); prog_bar.empty()
                st.error(str(e))
            except Exception as e:
                prog_text.empty(); prog_bar.empty()
                st.error(f"Export failed: {e}")

    if st.session_state.get('export_zip'):
        fname = f"gmail_export_{datetime.now().strftime('%Y%m%d')}.zip"
        st.download_button(
            label=f"⬇ Download {st.session_state.get('export_label', 'export')}.zip",
            data=st.session_state.export_zip,
            file_name=fname,
            mime="application/zip",
            key='dl_export',
        )


def _export_label(options):
    parts = []
    if "Metadata table"      in options: parts.append("metadata")
    if "Attachments"         in options: parts.append("attachments")
    if "Email content (PDF)" in options: parts.append("content")
    return "+".join(parts) or "export"


if __name__ == '__main__':
    main()
