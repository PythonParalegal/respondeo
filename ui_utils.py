# ─── MODULE METADATA ────────────────────────────────────────────────────────
# module:        ui_utils.py
# version:       1.3.0
# project:       Respondeo eDiscovery Platform
# project_ver:   2.9.0
# last_modified: 2026-04-15 14:30
# modified_by:   claude-code
# last_commit:   pending
# ─────────────────────────────────────────────────────────────────────────────
import streamlit as st
from contextlib import contextmanager
from pathlib import Path

_ASSETS = Path(__file__).resolve().parent / "assets"


def inject_sidebar_branding():
    """Display Respondeo logo at top of sidebar."""
    logo_path = _ASSETS / "sidebar_logo.png"
    if logo_path.exists():
        st.sidebar.image(str(logo_path), width=200)


def inject_custom_css():
    """Injects global UX CSS: hides running animation, suppresses browser autocomplete."""
    st.markdown("""
    <style>
        /* Hide Streamlit running animation */
        div[data-testid="stStatusWidget"] {
            visibility: hidden;
            height: 0%;
            position: fixed;
        }

        /* Hide auto-generated sidebar nav — replaced by permission-filtered nav in show_user_info() */
        [data-testid="stSidebarNav"] {
            display: none;
        }

        /* Allow browser zoom-out below Streamlit's default min-width */
        .main .block-container {
            min-width: 0 !important;
            max-width: 100% !important;
        }
        section[data-testid="stSidebar"] {
            min-width: 0 !important;
        }

        /* Shrink empty sidebar header — keep just enough for the collapse arrow */
        [data-testid="stSidebarHeader"] {
            min-height: 1.5rem !important;
            padding: 0.25rem 0.5rem !important;
        }



        /*
         * Suppress browser autocomplete dropdown on ALL text inputs.
         * Browser history suggestions are sourced from unrelated sites/forms
         * and are misleading in a legal review context.
         * The platform provides its own saved-search system instead.
         */
        div[data-testid="stTextInput"] input,
        div[data-testid="stTextArea"] textarea {
            autocomplete: off !important;
        }
    </style>
    <script>
        /* JS: set autocomplete=off on all inputs, re-applied after every Streamlit re-render */
        /* Re-enable pinch/scroll zoom — Streamlit sets user-scalable=no */
        (function enableZoom() {
            var meta = document.querySelector('meta[name="viewport"]');
            if (meta) {
                meta.setAttribute('content', 'width=device-width, initial-scale=1, user-scalable=yes');
            }
        })();

        (function suppressAutocomplete() {
            function applyOff() {
                document.querySelectorAll('input, textarea').forEach(function(el) {
                    el.setAttribute('autocomplete', 'off');
                });
            }
            applyOff();
            var observer = new MutationObserver(applyOff);
            observer.observe(document.body, { childList: true, subtree: true });
        })();
    </script>
    """, unsafe_allow_html=True)


def _overlay_html(text: str, sub_text: str = "Please wait — do not navigate away") -> str:
    """
    Returns a self-contained HTML block that renders a full-screen blocking overlay
    with a centered CSS spinner and label. Nothing is injected into the Streamlit
    document flow — every element is position:fixed.
    """
    return f"""
    <style>
        /* ── Blocking overlay ───────────────────────────── */
        .proc-overlay {{
            position: fixed;
            inset: 0;
            background: rgba(0,0,0,0.80);
            z-index: 9999990;
            cursor: wait;
        }}
        /* ── Centred card ───────────────────────────────── */
        .proc-card {{
            position: fixed;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            z-index: 9999999;
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 28px;
        }}
        /* ── CSS ring spinner ───────────────────────────── */
        .proc-ring {{
            width: 90px;
            height: 90px;
            border-radius: 50%;
            border: 8px solid rgba(79,139,249,0.25);
            border-top-color: #4F8BF9;
            animation: proc-spin 0.9s linear infinite;
        }}
        @keyframes proc-spin {{
            to {{ transform: rotate(360deg); }}
        }}
        /* ── Label ──────────────────────────────────────── */
        .proc-label {{
            color: #e8eaf0;
            font-size: 1.55rem;
            font-weight: 700;
            font-family: 'Inter', 'Segoe UI', sans-serif;
            text-align: center;
            letter-spacing: 0.01em;
            text-shadow: 0 2px 12px rgba(0,0,0,0.6);
            max-width: 480px;
            line-height: 1.4;
        }}
        .proc-sub {{
            color: rgba(255,255,255,0.45);
            font-size: 0.85rem;
            font-family: 'Inter', 'Segoe UI', sans-serif;
            text-align: center;
            margin-top: -16px;
        }}
    </style>
    <div class="proc-overlay"></div>
    <div class="proc-card">
        <div class="proc-ring"></div>
        <div class="proc-label">{text}</div>
        <div class="proc-sub">{sub_text}</div>
    </div>
    """


@contextmanager
def lottie_spinner(text="Processing...", lottie_path="assets/law.json"):
    """
    Context manager: shows a full-screen CSS overlay while the block executes.
    The lottie_path argument is retained for signature compatibility but ignored —
    the animation is now a pure CSS ring spinner that cannot escape into page flow.
    """
    placeholder = st.empty()
    placeholder.markdown(_overlay_html(text), unsafe_allow_html=True)
    try:
        yield
    finally:
        placeholder.empty()

def start_lottie_spinner(text="Processing...", lottie_path="assets/law.json", sub_text="Please wait — do not navigate away"):
    """
    Non-context-manager version. Returns the placeholder — caller MUST call placeholder.empty().
    lottie_path retained for signature compatibility but ignored.
    """
    placeholder = st.empty()
    placeholder.markdown(_overlay_html(text, sub_text), unsafe_allow_html=True)
    return placeholder

def update_lottie_spinner(placeholder, text="Processing...", sub_text="Please wait — do not navigate away"):
    """Dynamically updates an existing overlay spinner with new text/sub_text status."""
    placeholder.markdown(_overlay_html(text, sub_text), unsafe_allow_html=True)


def show_overlay_cancel_button():
    """
    Inject a cancel button into the blocking overlay via JavaScript.

    Streamlit's st.markdown sanitiser strips <button> and onclick attributes,
    so we use streamlit.components.v1.html() which renders in an unrestricted
    iframe. The script injects a real button element into the parent page's
    .proc-card overlay div. A MutationObserver re-injects the button whenever
    the overlay is updated (update_lottie_spinner replaces the card HTML).
    When the overlay is removed (processing complete), the observer cleans up.

    The injected button finds and clicks a hidden Streamlit button whose text
    contains 'Cancel Processing'. That Streamlit button's on_click callback
    sets the session_state cancel flag that the processing loop checks.
    """
    import streamlit.components.v1 as components
    components.html("""
    <script>
    (function() {
        var pdoc = window.parent.document;

        function injectBtn() {
            var card = pdoc.querySelector('.proc-card');
            if (!card || card.querySelector('.proc-cancel-btn')) return;

            var btn = document.createElement('button');
            btn.className = 'proc-cancel-btn';
            btn.innerHTML = '\\u26D4 Cancel Processing';
            btn.style.cssText =
                'margin-top:8px;padding:10px 32px;'
                + 'background:rgba(220,53,69,0.85);color:#fff;'
                + 'border:2px solid rgba(255,255,255,0.3);border-radius:8px;'
                + 'font-size:1rem;font-weight:600;'
                + "font-family:'Inter','Segoe UI',sans-serif;"
                + 'cursor:pointer;letter-spacing:0.02em;'
                + 'transition:background 0.2s,border-color 0.2s;';

            btn.onmouseover = function() {
                btn.style.background = 'rgba(220,53,69,1)';
                btn.style.borderColor = 'rgba(255,255,255,0.6)';
            };
            btn.onmouseout = function() {
                if (!btn.disabled) {
                    btn.style.background = 'rgba(220,53,69,0.85)';
                    btn.style.borderColor = 'rgba(255,255,255,0.3)';
                }
            };

            btn.addEventListener('click', function() {
                btn.disabled = true;
                btn.style.opacity = '0.5';
                btn.style.cursor = 'not-allowed';
                btn.textContent = 'Cancelling\\u2026';
                /* Click the hidden Streamlit cancel button */
                var allBtns = pdoc.querySelectorAll('button');
                for (var i = 0; i < allBtns.length; i++) {
                    if (allBtns[i] !== btn
                        && allBtns[i].textContent.indexOf('Cancel Processing') !== -1) {
                        allBtns[i].click();
                        break;
                    }
                }
            });

            card.appendChild(btn);
        }

        injectBtn();

        /* Re-inject after overlay updates (update_lottie_spinner replaces the card) */
        var observer = new MutationObserver(function() {
            if (!pdoc.querySelector('.proc-overlay')) {
                /* Overlay gone — processing finished; clean up */
                var stale = pdoc.querySelector('.proc-cancel-btn');
                if (stale) stale.remove();
                observer.disconnect();
                return;
            }
            injectBtn();
        });
        observer.observe(pdoc.body, { childList: true, subtree: true });
    })();
    </script>
    """, height=0)

