"""
ui_components.py — all Streamlit rendering. app.py calls these; no widgets elsewhere.
"""

import streamlit as st

PAGE_SIZE_OPTIONS = [10, 25, 50, 100]
DEFAULT_PAGE_SIZE = 25

COLUMNS = [
    ('From',    'From',    2),
    ('To',      'To',      2),
    ('Date',    'Date',    1),
    ('Subject', 'Subject', 4),
]


# ── CSS ───────────────────────────────────────────────────────────────────────

def inject_styles():
    st.markdown("""
    <style>
    div.stButton > button {
        background-color: #3d6b74; color: #ffffff; border: none;
        border-radius: 6px; padding: 0.4rem 1.2rem; font-weight: 500;
        transition: background-color 0.15s ease;
    }
    div.stButton > button:hover { background-color: #2f5560; color: #ffffff; }
    div.stButton > button:disabled {
        background-color: #b0c4c8 !important; color: #ffffff !important;
    }
    div.stDownloadButton > button {
        background-color: #3d6b74; color: #ffffff; border: none;
        border-radius: 6px; padding: 0.4rem 1.4rem; font-weight: 500;
        transition: background-color 0.15s ease;
    }
    div.stDownloadButton > button:hover { background-color: #2f5560; color: #ffffff; }
    </style>
    """, unsafe_allow_html=True)


# ── Progress bar ─────────────────────────────────────────────────────────────

def make_progress_bar():
    text_ph = st.empty()
    bar_ph  = st.empty()
    return bar_ph, text_ph

def update_progress_bar(bar_ph, text_ph, completed, total):
    pct = completed / total if total else 1.0
    text_ph.caption(f"Loading metadata — {completed} of {total}")
    bar_ph.progress(pct)

def clear_progress_bar(bar_ph, text_ph):
    bar_ph.empty(); text_ph.empty()


# ── Session-state helpers ─────────────────────────────────────────────────────

def _clear_chk_keys():
    for k in list(st.session_state.keys()):
        if k.startswith('chk_'):
            del st.session_state[k]


def reset_results_state():
    st.session_state.messages      = []
    st.session_state.emails_data   = {}
    st.session_state.messages_list = []
    st.session_state.selected_ids  = {}
    st.session_state.page          = 0
    st.session_state.page_size     = DEFAULT_PAGE_SIZE
    st.session_state.loading_done  = False
    st.session_state.stop_loading  = False
    _clear_chk_keys()


# ── Results table ─────────────────────────────────────────────────────────────

def render_results_table(emails_data: dict, total_found: int):
    """
    emails_data: dict {index: metadata_dict} — may be partial during streaming.
    total_found: total IDs from search (denominator for progress display).
    """
    loaded = [emails_data[i] for i in sorted(emails_data.keys())]
    if not loaded:
        st.caption("Loading…")
        return

    total = len(loaded)
    sel   = st.session_state.get('selected_ids', {})

    # ── Pagination ────────────────────────────────────────────────────────
    page_size   = st.session_state.get('page_size', DEFAULT_PAGE_SIZE)
    total_pages = max(1, -(-total // page_size))
    page        = max(0, min(st.session_state.get('page', 0), total_pages - 1))
    st.session_state.page = page
    start      = page * page_size
    end        = min(start + page_size, total)
    page_slice = loaded[start:end]

    # ── Toolbar: count info only ──────────────────────────────────────────
    n_sel = len(sel)
    info  = f"**{total}** loaded"
    if total_found > total:
        info += f" of **{total_found}** found"
    if n_sel:
        info += f" · **{n_sel}** selected"
    st.caption(info)

    # ── Page size ─────────────────────────────────────────────────────────
    ps_col, _ = st.columns([2, 5])
    with ps_col:
        new_ps = st.selectbox("Rows per page", PAGE_SIZE_OPTIONS,
                              index=PAGE_SIZE_OPTIONS.index(page_size),
                              key='page_size_select')
    if new_ps != page_size:
        st.session_state.page_size = new_ps
        st.session_state.page = 0
        _clear_chk_keys()
        st.rerun()

    # ── Headers ───────────────────────────────────────────────────────────
    col_widths  = [0.5] + [w for _, _, w in COLUMNS]
    hdr         = st.columns(col_widths)
    hdr[0].markdown("&nbsp;", unsafe_allow_html=True)
    for i, (_, label, _) in enumerate(COLUMNS):
        hdr[i+1].markdown(f"**{label}**")
    st.divider()

    # ── Rows ──────────────────────────────────────────────────────────────
    for row in page_slice:
        cols     = st.columns(col_widths)
        email_id = row['id']
        with cols[0]:
            was_checked = bool(st.session_state.get('selected_ids', {}).get(email_id))
            ticked = st.checkbox('', value=was_checked, key=f'chk_{email_id}',
                                 label_visibility='collapsed')
            if ticked != was_checked:
                new_sel = dict(st.session_state.get('selected_ids', {}))
                if ticked:
                    new_sel[email_id] = True
                else:
                    new_sel.pop(email_id, None)
                st.session_state.selected_ids = new_sel
        with cols[1]: st.caption(_trim(row.get('From', ''), 30))
        with cols[2]: st.caption(_trim(row.get('To', ''), 30))
        with cols[3]: st.caption(row.get('Date', ''))
        with cols[4]: st.caption(row.get('Subject', ''))

    st.divider()

    # ── Pagination ────────────────────────────────────────────────────────
    pl, pm, pr = st.columns([1, 3, 1])
    with pl:
        if st.button("← Prev", disabled=(page == 0), use_container_width=True):
            st.session_state.page -= 1
            _clear_chk_keys()
            st.rerun()
    with pm:
        st.caption(f"Page **{page+1}** of **{total_pages}** — showing {start+1}–{end} of {total}")
    with pr:
        if st.button("Next →", disabled=(page >= total_pages-1), use_container_width=True):
            st.session_state.page += 1
            _clear_chk_keys()
            st.rerun()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _trim(value: str, max_chars: int) -> str:
    if not value:
        return ''
    if '<' in value:
        value = value[:value.index('<')].strip()
    return value if len(value) <= max_chars else value[:max_chars-1] + '…'
