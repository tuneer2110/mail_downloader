"""
app.py  –  Gmail Content Downloader
Run with:  streamlit run app.py
"""

import time
import streamlit as st
from datetime import datetime

from config import FILE_TYPE_EXTENSIONS
from auth import authenticate_gmail
from query_builder import build_email_query, MAILBOX_LABELS, EXCLUDABLE_LABELS
from email_service import search_emails, stream_emails_metadata
from download_service import build_export_zip_streaming
from ui_components import inject_styles, reset_results_state, render_results_table

st.set_page_config(page_title="Gmail Content Downloader", page_icon="✉️", layout="wide")
inject_styles()

LOAD_OPTIONS = ["10", "25", "50", "100", "All"]


def main():
    st.title("Gmail Content Downloader")

    # ═══════════════════════════════════════════════════════════════════════
    # STEP 1 — AUTHENTICATION
    # ═══════════════════════════════════════════════════════════════════════
    # ── Handle Google redirect return (cloud only) ───────────────────────
    # When Google redirects back with ?code=xxx, email is in session_state
    # from before the redirect. Attempt auth immediately without showing the form.
    if 'service' not in st.session_state and st.query_params.get('code'):
        pending_email = st.session_state.get('_pending_email', '')
        if pending_email:
            try:
                svc = authenticate_gmail(pending_email)
                if svc is not None:
                    st.session_state.service      = svc
                    st.session_state.authed_email = pending_email
                    st.rerun()
            except Exception as e:
                st.error(f"Authentication failed: {e}")

    if 'service' not in st.session_state:
        st.header("Step 1 — Authenticate")
        email_id = st.text_input("Gmail address", placeholder="you@gmail.com", key='email_id')

        if st.button("Connect to Gmail"):
            if not email_id:
                st.warning("Please enter your email address first.")
            else:
                try:
                    svc = authenticate_gmail(email_id)
                    if svc is None:
                        # Cloud flow — redirecting to Google, stop rendering
                        st.stop()
                    else:
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

    keyword = st.text_input("Keyword", placeholder="Subject, body or attachment name")

    # ── Dates — optional, empty by default ───────────────────────────────
    col_start, col_end = st.columns(2)
    with col_start:
        use_start = st.checkbox("Start date", key='use_start')
        start_date = st.date_input(
            "Start date value", max_value=datetime.today(),
            key='start_date_val', label_visibility='collapsed',
        ) if use_start else None
    with col_end:
        use_end = st.checkbox("End date", key='use_end')
        end_date = st.date_input(
            "End date value",
            min_value=start_date if start_date else datetime(2000, 1, 1),
            max_value=datetime.today(),
            key='end_date_val', label_visibility='collapsed',
        ) if use_end else None

    col_from, col_to = st.columns(2)
    with col_from:
        sender    = st.text_input("From", placeholder="name or email@example.com")
    with col_to:
        recipient = st.text_input("To",   placeholder="name or email@example.com")

    mailbox = st.selectbox(
        "Search in",
        list(MAILBOX_LABELS.keys()),
        index=0,
        key='mailbox',
    )

    has_attachments  = st.checkbox("Has attachments")
    attachment_types = []
    if has_attachments:
        attachment_types = st.multiselect(
            "Attachment types", list(FILE_TYPE_EXTENSIONS.keys())
        )

    # ── Advanced ──────────────────────────────────────────────────────────
    with st.expander("Advanced search"):
        exclude_keywords = st.text_input(
            "Exclude keywords",
            placeholder="words or phrases to exclude (space-separated)",
        )
        exclude_labels = st.multiselect(
            "Exclude results from",
            EXCLUDABLE_LABELS,
            help="Remove emails that belong to any of these categories",
        )
        col_a1, col_a2 = st.columns(2)
        with col_a1:
            skip_replies  = st.checkbox("Skip replies")
        with col_a2:
            skip_forwards = st.checkbox("Skip forwards")

    # ── Search button ─────────────────────────────────────────────────────
    _, btn_col, _ = st.columns([1, 2, 1])
    with btn_col:
        search_clicked = st.button("🔍  Search", use_container_width=True)

    if search_clicked:
        query = build_email_query(
            sender=sender, recipient=recipient,
            keyword=keyword, exclude_keywords=exclude_keywords,
            start_date=start_date, end_date=end_date,
            mailbox=mailbox,
            has_attachment=has_attachments, file_types=attachment_types,
            skip_replies=skip_replies, skip_forwards=skip_forwards,
            exclude_labels=exclude_labels,
        )
        # Persist query so the expander survives subsequent reruns
        st.session_state['last_query'] = query

        with st.spinner("Searching…"):
            messages = search_emails(service, query, max_results=None)

        if not messages:
            st.info("No messages found.")
            reset_results_state()
            st.session_state['last_query'] = query   # keep query visible even on no results
            st.stop()

        reset_results_state()
        st.session_state.messages_list = messages
        st.session_state.total_found   = len(messages)
        st.rerun()

    # Show persisted query expander whenever a search has been run
    if st.session_state.get('last_query'):
        with st.expander("Generated query", expanded=False):
            st.code(st.session_state['last_query'], language=None)

    # ═══════════════════════════════════════════════════════════════════════
    # METADATA LOAD LIMIT — shown after search, before loading starts
    # ═══════════════════════════════════════════════════════════════════════
    messages_list = st.session_state.get('messages_list', [])
    if not messages_list:
        st.stop()

    total_found = st.session_state.get('total_found', len(messages_list))

    st.divider()
    lc1, lc2 = st.columns([3, 2])
    with lc1:
        st.caption(f"**{total_found}** match{'es' if total_found != 1 else ''} found")
    with lc2:
        load_choice = st.selectbox(
            "Load details for how many results?",
            LOAD_OPTIONS,
            index=1,    # default 25
            key='load_limit',
        )

    load_n    = None if load_choice == "All" else int(load_choice)
    load_list = messages_list if load_n is None else messages_list[:load_n]

    # Reset emails_data if load choice changed
    if st.session_state.get('_last_load') != load_choice:
        st.session_state.emails_data  = {}
        st.session_state.loading_done = False
        st.session_state.stop_loading = False
        st.session_state._last_load   = load_choice

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
            sc, _ = st.columns([1, 4])
            with sc:
                if st.button("⏹ Stop loading", key='stop_btn'):
                    st.session_state.stop_loading = True
                    st.rerun()

            already = len(emails_data)
            load_status.caption(f"Loading email details — {already} of {load_target}")
            load_bar.progress(already / load_target if load_target else 1.0)

            BATCH     = 10
            batch     = remaining[:BATCH]
            b_msgs    = [m for _, m in batch]
            b_idxs    = [i for i, _ in batch]
            collected = {}

            stream_emails_metadata(
                service, b_msgs,
                on_result=lambda idx, meta: collected.__setitem__(idx, meta),
                stop_flag=lambda: st.session_state.get('stop_loading', False),
            )

            new_data = dict(emails_data)
            for li, gi in enumerate(b_idxs):
                if li in collected:
                    new_data[gi] = collected[li]
            st.session_state.emails_data = new_data

            if len(new_data) >= load_target:
                st.session_state.loading_done = True
                load_status.empty(); load_bar.empty()
            else:
                time.sleep(0.05)
                st.rerun()
        else:
            st.session_state.loading_done = True

    # ═══════════════════════════════════════════════════════════════════════
    # STEP 3 — SELECT
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
        st.caption(f"⏹ Stopped — {len(emails_data)} of {load_target} loaded. You can still export.")

    render_results_table(emails_data, load_target)

    # ═══════════════════════════════════════════════════════════════════════
    # STEP 4 — DOWNLOAD
    # ═══════════════════════════════════════════════════════════════════════
    st.divider()
    st.header("Step 4 — Download")

    selected_ids   = dict(st.session_state.get('selected_ids', {}))
    n_sel          = len(selected_ids)
    all_loaded     = [emails_data[i] for i in sorted(emails_data.keys())]
    n_loaded       = len(all_loaded)
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
    scope_opts = []
    if n_sel > 0:
        scope_opts.append(f"Download selection ({n_sel})")
    scope_opts.append(f"Download loaded results ({n_loaded})")
    if total_found > n_loaded:
        scope_opts.append(f"Download all matches ({total_found})")

    scope = st.radio(
        "Export scope",
        scope_opts,
        index=0,
        horizontal=True,
        key='export_scope',
    )
    st.session_state['_scope_committed'] = scope

    if scope.startswith("Download selection"):
        scope_key     = "selection"
        preview_count = n_sel
    elif scope.startswith("Download all"):
        scope_key     = "all_matches"
        preview_count = total_found
    else:
        scope_key     = "loaded"
        preview_count = n_loaded

    st.caption(
        f"Will export **{preview_count}** email{'s' if preview_count != 1 else ''}  —  "
        + ", ".join(download_options)
    )

    # ── Prepare button ────────────────────────────────────────────────────
    if st.button("Prepare export", key='prep_export'):
        committed = st.session_state.get('_scope_committed', scope)

        if committed.startswith("Download selection"):
            final_emails = [_with_thread(em) for em in all_loaded
                            if em['id'] in st.session_state.get('selected_ids', {})]
        elif committed.startswith("Download all"):
            # Load any remaining unloaded metadata first
            remaining_msgs = [m for m in messages_list
                              if m['id'] not in {e['id'] for e in all_loaded}]
            if remaining_msgs:
                ext_ph  = st.empty()
                ext_bar = st.empty()
                extra   = {}

                stream_emails_metadata(
                    service, remaining_msgs,
                    on_result=lambda idx, meta: (
                        extra.__setitem__(idx, meta) or
                        ext_ph.caption(f"Loading remaining — {len(extra)} of {len(remaining_msgs)}") or
                        ext_bar.progress(len(extra) / len(remaining_msgs))
                    ),
                    stop_flag=lambda: False,
                )
                ext_ph.empty(); ext_bar.empty()
                offset   = len(all_loaded)
                new_data = dict(st.session_state.get('emails_data', {}))
                for i, meta in extra.items():
                    new_data[offset + i] = meta
                st.session_state.emails_data  = new_data
                st.session_state.loading_done = True
                all_loaded_full = [new_data[k] for k in sorted(new_data.keys())]
            else:
                all_loaded_full = all_loaded
            final_emails = [_with_thread(em) for em in all_loaded_full]
        else:
            final_emails = [_with_thread(em) for em in all_loaded]

        if not final_emails:
            st.warning("No emails to export — check your selection.")
        else:
            prog_text = st.empty()
            prog_bar  = st.empty()
            prog_text.caption("Preparing export…")
            prog_bar.progress(0.0)

            excel_emails = final_emails if committed.startswith("Download all") else all_loaded

            def _dl_progress(done, total, phase):
                if total:
                    prog_bar.progress(done / total)
                prog_text.caption(f"{phase} — {done} of {total}")

            try:
                zip_bytes = build_export_zip_streaming(
                    service             = service,
                    emails_data         = excel_emails,
                    selected_emails     = final_emails,
                    include_metadata    = include_metadata,
                    include_attachments = include_attachments,
                    include_bodies      = include_bodies,
                    on_progress         = _dl_progress,
                    stop_flag           = lambda: False,
                )
                prog_text.empty(); prog_bar.empty()
                st.session_state.export_zip   = zip_bytes
                st.session_state.export_label = _export_label(download_options)
            except RuntimeError as e:
                prog_text.empty(); prog_bar.empty()
                st.error(str(e))
            except Exception as e:
                prog_text.empty(); prog_bar.empty()
                st.error(f"Export failed: {e}")

    if st.session_state.get('export_zip'):
        today = datetime.now().strftime('%y-%m-%d')
        fname = f"gmail_export_{today}.zip"
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