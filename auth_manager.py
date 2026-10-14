# ─── MODULE METADATA ────────────────────────────────────────────────────────
# module:        auth_manager.py
# version:       1.9.7
# project:       Respondeo eDiscovery Platform
# project_ver:   2.9.0
# last_modified: 2026-04-17 02:33
# modified_by:   claude-code
# last_commit:   pending
# ─────────────────────────────────────────────────────────────────────────────
import streamlit as st
import hashlib
import os
import time
import yaml
import bcrypt

AUTH_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "auth_config.yaml")

# Sidebar navigation registry: (file_path, label, permission_required)
# To add a new page, add one tuple here. Order determines sidebar order.
# permission=None means always visible (e.g., Home).
_NAV_PAGES = [
    ("home.py",                   "🏠 Home",        None),
    ("pages/1_Ingestor.py",       "📥 Ingestor",    "ingest"),
    ("pages/2_Processor.py",      "⚙️ Processor",   "process"),
    ("pages/3_Analytics.py",      "📊 Analytics",    "analytics"),
    ("pages/4_Review.py",         "🔍 Review",       "review"),
    ("pages/5_Production.py",     "📦 Production",   "production"),
    ("pages/9_InboundProduction.py", "📨 Inbound Productions", "production"),
    ("pages/6_Sync.py",           "🔄 Sync",         "sync"),
    ("pages/7_Custodians.py",     "👤 Custodians",   "custodian_management"),
    ("pages/8_Exhibits.py",       "📋 Exhibits",     "view_exhibits"),
]

# ---------------------------------------------------------------------------
# Role hierarchy: admin > manager > reviewer
# Each role implicitly includes all roles below it.
# ---------------------------------------------------------------------------
_ROLE_LEVELS = {"admin": 3, "manager": 2, "reviewer": 1}

# ---------------------------------------------------------------------------
# Permission system — hardcoded defaults (used when YAML lacks role_permissions)
# These MUST reproduce current behaviour exactly so the migration is zero-downtime.
# ---------------------------------------------------------------------------
_DEFAULT_PERMISSIONS: dict[str, set] = {
    'admin': {'*'},
    'manager': {
        'case_settings', 'ingest', 'process', 'analytics',
        'review', 'tag', 'redact', 'reimage',
        'export_csv', 'export_pdf',
        'str_run', 'str_export',
        'production', 'inbound_production', 'privilege_log',
        'custodian_management',
        'mark_exhibit', 'view_exhibits',
        'manage_exhibit_sets', 'manage_exhibits', 'export_exhibit_binder',
        'sync', 'audit_view', 'column_picker',
        'saved_search_global', 'saved_search_personal', 'download_produced',
        'split_document',
        'view_shell_documents',
    },
    'reviewer': {
        'review', 'tag', 'redact', 'export_csv', 'export_pdf',
        'str_run', 'saved_search_global', 'saved_search_personal', 'download_produced',
        'mark_exhibit', 'view_exhibits',
    },
}

# All known permission names (used by the admin UI checkbox grid).
ALL_PERMISSIONS = [
    # Pipeline
    'ingest', 'process', 'analytics',
    # Review
    'review', 'tag', 'redact', 'export_csv', 'export_pdf',
    'str_run', 'str_export', 'column_picker',
    'saved_search_global', 'saved_search_personal', 'download_produced',
    'reimage',
    'mark_exhibit', 'view_exhibits',
    # Production / legal
    'production', 'inbound_production', 'privilege_log',
    'custodian_management',
    'manage_exhibit_sets', 'manage_exhibits', 'export_exhibit_binder',
    # Structural
    'split_document',
    'view_shell_documents',  # View Split_Source/Container_Scanned shells in grid & QC tabs
    # Admin
    'case_settings', 'sync', 'audit_view', 'user_admin',
]


def validate_password_complexity(password: str) -> str | None:
    """
    Check password meets complexity requirements.
    Returns an error message string if invalid, or None if valid.
    """
    if len(password) < 8:
        return "Password must be at least 8 characters."
    if not any(c.isupper() for c in password):
        return "Password must contain at least one uppercase letter."
    if not any(c.isdigit() for c in password):
        return "Password must contain at least one number."
    return None


def _get_role_permissions(role: str, _visited: set | None = None) -> set:
    """
    Return the permission set for the given role.
    Resolution order:
      1. YAML role_permissions[role] (standard roles)
      2. YAML custom_roles[role] (custom roles with 'permissions' or 'inherits')
      3. Hardcoded _DEFAULT_PERMISSIONS fallback
    """
    if _visited is None:
        _visited = set()
    if role in _visited:
        logger.warning(f"Permission inheritance cycle detected: {role}")
        return set()
    _visited.add(role)

    config = _load_config()
    role_permissions = config.get('role_permissions') or {}
    custom_roles = config.get('custom_roles') or {}

    if role in role_permissions:
        return set(role_permissions[role])

    if role in custom_roles:
        role_def = custom_roles[role]
        if 'permissions' in role_def:
            return set(role_def['permissions'] or [])
        if 'inherits' in role_def:
            inherited_role = role_def['inherits']
            # Block inheriting from admin — prevents wildcard escalation
            if inherited_role == 'admin':
                return set(role_def.get('additional') or [])
            base = _get_role_permissions(inherited_role, _visited)
            additional = set(role_def.get('additional') or [])
            return base | additional

    return set(_DEFAULT_PERMISSIONS.get(role, set()))


def has_permission(permission_name: str) -> bool:
    """Return True if the current user's role includes the named permission."""
    role = st.session_state.get('user_role', 'reviewer')
    role_perms = _get_role_permissions(role)
    return '*' in role_perms or permission_name in role_perms


def require_permission(permission_name: str):
    """
    Page-level gate. Stops execution if the current user lacks the permission.
    Call after check_login().
    """
    if not has_permission(permission_name):
        st.error(
            f"⛔ Access denied — this module requires the **{permission_name}** permission. "
            f"Contact your administrator."
        )
        st.stop()


def _load_config():
    """Load auth config from YAML file."""
    if not os.path.exists(AUTH_CONFIG_PATH):
        return {"users": {}}
    with open(AUTH_CONFIG_PATH, 'r') as f:
        return yaml.safe_load(f) or {"users": {}}

def _save_config(config):
    """Save auth config to YAML file. Raises RuntimeError on I/O failure.
    Restricts file permissions after write (contains password hashes)."""
    try:
        with open(AUTH_CONFIG_PATH, 'w') as f:
            yaml.dump(config, f, default_flow_style=False)
        # Restrict file permissions — auth config contains password hashes
        import sys as _sys
        if _sys.platform == 'win32':
            import subprocess as _sp
            try:
                # Remove inherited permissions + grant only current user full control
                _sp.run(
                    ['icacls', AUTH_CONFIG_PATH, '/inheritance:r',
                     '/grant:r', f'{os.environ.get("USERNAME", "SYSTEM")}:F'],
                    capture_output=True, timeout=5
                )
            except Exception:
                pass  # Best-effort on Windows
        else:
            os.chmod(AUTH_CONFIG_PATH, 0o600)
    except OSError as e:
        raise RuntimeError(f"Failed to save auth configuration: {e}") from e

def _hash_password(password: str) -> str:
    """Hash password with bcrypt."""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def _verify_password(password: str, stored_hash: str) -> bool:
    """
    Verify a password against the stored hash.
    Handles both legacy SHA-256 hashes (64 hex chars) and bcrypt hashes.
    Returns True if the password matches.
    """
    # Detect legacy SHA-256: exactly 64 lowercase hex chars, no bcrypt prefix
    if len(stored_hash) == 64 and not stored_hash.startswith('$2'):
        return hashlib.sha256(password.encode('utf-8')).hexdigest() == stored_hash
    # bcrypt hash
    try:
        return bcrypt.checkpw(password.encode('utf-8'), stored_hash.encode('utf-8'))
    except Exception:
        return False

# ---------------------------------------------------------------------------
# Role utilities
# ---------------------------------------------------------------------------
def get_user_role() -> str:
    """Returns the current user's role string, defaulting to 'reviewer'."""
    return st.session_state.get('user_role', 'reviewer')

def _role_level(role: str) -> int:
    return _ROLE_LEVELS.get(role, 0)

# ---------------------------------------------------------------------------
# Auth flow
# ---------------------------------------------------------------------------
def check_login() -> bool:
    """
    Renders login form if user is not authenticated.
    Returns True if user is logged in, False otherwise.
    Call this at the top of every page.
    """
    if st.session_state.get('authenticated'):
        # ── Session timeout check ────────────────────────────────────
        _timeout_minutes = _load_config().get('session_timeout_minutes', 120)
        if _timeout_minutes and _timeout_minutes > 0:
            _last_activity = st.session_state.get('last_activity_time', 0)
            if _last_activity and (time.time() - _last_activity) > (_timeout_minutes * 60):
                # Session expired — force re-login
                for _key in ('authenticated', 'username', 'user_role', 'display_name',
                             'last_activity_time'):
                    st.session_state.pop(_key, None)
                st.warning("⏱️ Session expired due to inactivity. Please log in again.")
                return False
        # Update activity timestamp
        st.session_state['last_activity_time'] = time.time()

        # Enforce case-access restriction on every page load.
        # If the active case is no longer in the user's allowed list, silently clear it.
        _cf = st.session_state.get('current_case_folder')
        if _cf:
            _uname = st.session_state.get('username', '')
            _allowed = get_allowed_cases(_uname)
            if _allowed is not None and _cf not in _allowed:
                st.session_state.pop('current_case_folder', None)
        return True

    st.title("🔐 Respondeo — Login")

    with st.form("login_form"):
        username = st.text_input("Username", autocomplete="username")
        password = st.text_input("Password", type="password", autocomplete="current-password")
        submitted = st.form_submit_button("Login", width='stretch')

    if submitted:
        config = _load_config()
        users = config.get('users', {})

        if username in users:
            stored_hash = users[username].get('password_hash', '')
            if _verify_password(password, stored_hash):
                # Transparently upgrade legacy SHA-256 hash to bcrypt on first successful login
                if len(stored_hash) == 64 and not stored_hash.startswith('$2'):
                    config['users'][username]['password_hash'] = _hash_password(password)
                    _save_config(config)
                # Clear pre-login session state to prevent session fixation.
                # Stale keys from a prior session (or another user) must not
                # persist into the new authenticated session.
                for _k in list(st.session_state.keys()):
                    del st.session_state[_k]
                st.session_state['authenticated'] = True
                st.session_state['username'] = username
                st.session_state['user_role'] = users[username].get('role', 'reviewer')
                st.session_state['display_name'] = users[username].get('name', username)
                st.session_state['last_activity_time'] = time.time()
                # Restore last-used case if the path still exists on disk
                # and the user is allowed to access it.
                last_case = users[username].get('last_case')
                if last_case and os.path.isdir(last_case):
                    _allowed = get_allowed_cases(username)
                    if _allowed is None or last_case in _allowed:
                        st.session_state['current_case_folder'] = last_case
                st.rerun()
            else:
                st.error("❌ Invalid password.")
        else:
            st.error("❌ User not found.")

    return False


def show_user_info():
    """Show current user info and logout button in sidebar."""
    if st.session_state.get('authenticated'):
        display_name = st.session_state.get('display_name', 'User')
        role = get_user_role()

        role_labels = {
            'admin':    '👑 Admin',
            'manager':  '🏢 Manager',
            'reviewer': '📋 Reviewer',
            'expert':   '🔬 Expert',
        }
        role_label = role_labels.get(role, f'🏷️ {role.capitalize()}')

        st.sidebar.markdown(f"**{display_name}**")
        st.sidebar.caption(role_label)
        if st.sidebar.button("🚪 Logout"):
            st.session_state.clear()
            st.rerun()
        _active_case = st.session_state.get('current_case_folder')
        if _active_case:
            st.sidebar.caption(f"📂 {os.path.basename(_active_case)}")
        st.sidebar.markdown("---")

        # Permission-filtered navigation from _NAV_PAGES registry
        for _nav_path, _nav_label, _nav_perm in _NAV_PAGES:
            if _nav_perm is None or has_permission(_nav_perm):
                st.sidebar.page_link(_nav_path, label=_nav_label)
        st.sidebar.markdown("---")


# ---------------------------------------------------------------------------
# User CRUD — used by admin UI in home.py
# All functions are self-protecting: they verify the caller has user_admin
# permission before executing. During first-user bootstrap (no users exist),
# the check is skipped so the initial admin can be created.
# ---------------------------------------------------------------------------
def _require_admin():
    """Self-protecting guard for admin CRUD. Skips during first-user bootstrap."""
    config = _load_config()
    if not config.get('users'):
        return  # No users yet — bootstrap allowed
    # permission: user_admin
    if not has_permission('user_admin'):
        raise PermissionError("user_admin permission required")


def create_user(username: str, password: str, name: str, role: str = 'reviewer'):
    """Add a new user to the auth config."""
    _require_admin()
    config = _load_config()
    config['users'][username] = {
        'name': name,
        'password_hash': _hash_password(password),
        'role': role,
    }
    _save_config(config)


def update_password(username: str, new_password: str):
    """Reset a user's password."""
    _require_admin()
    config = _load_config()
    if username in config.get('users', {}):
        config['users'][username]['password_hash'] = _hash_password(new_password)
        _save_config(config)
        return True
    return False


def update_role(username: str, new_role: str):
    """Change a user's role."""
    _require_admin()
    config = _load_config()
    if username in config.get('users', {}):
        config['users'][username]['role'] = new_role
        _save_config(config)
        return True
    return False


def delete_user(username: str):
    """Remove a user from auth config."""
    _require_admin()
    config = _load_config()
    if username in config.get('users', {}):
        del config['users'][username]
        _save_config(config)
        return True
    return False


def save_user_pref(username: str, key: str, value):
    """Persist an arbitrary per-user preference into auth_config.yaml."""
    config = _load_config()
    if username in config.get('users', {}):
        config['users'][username][key] = value
        _save_config(config)


def get_allowed_cases(username: str) -> list[str] | None:
    """
    Return the case-access restriction list for the user.
    Returns None  → user is unrestricted (sees all cases).
    Returns []    → user has an empty restriction list (no cases visible).
    Returns [...]  → user may only access the listed paths.
    """
    config = _load_config()
    allowed = config.get('users', {}).get(username, {}).get('allowed_cases')
    if not allowed:  # None or empty list → unrestricted
        return None
    return list(allowed)


def update_allowed_cases(username: str, paths: list[str]):
    """
    Set or clear the allowed_cases restriction for a user.
    Passing an empty list removes the restriction (unrestricted access).
    """
    _require_admin()
    config = _load_config()
    if username not in config.get('users', {}):
        return
    if paths:
        config['users'][username]['allowed_cases'] = sorted(paths)
    else:
        config['users'][username].pop('allowed_cases', None)
    _save_config(config)


def get_doc_visibility(username: str) -> dict:
    """
    Return the document visibility config for a user.
    Returns dict with keys:
      'mode': 'full' | 'produced_only' | 'hidden_tags'
      'hidden_tags': list[str]  (only meaningful when mode == 'hidden_tags')
    Defaults to {'mode': 'full', 'hidden_tags': []} if not configured.
    Admin users ALWAYS return full regardless of config.
    """
    config = _load_config()
    user_data = config.get('users', {}).get(username, {})

    # Admin override: always full universe
    if user_data.get('role') == 'admin':
        return {'mode': 'full', 'hidden_tags': []}

    vis = user_data.get('doc_visibility', {})
    mode = vis.get('mode', 'full')
    if mode not in ('full', 'produced_only', 'hidden_tags'):
        mode = 'full'
    hidden_tags = vis.get('hidden_tags', [])
    if not isinstance(hidden_tags, list):
        hidden_tags = []
    return {'mode': mode, 'hidden_tags': hidden_tags}


def update_doc_visibility(username: str, mode: str, hidden_tags: list = None):
    """
    Set the document visibility config for a user.
    mode: 'full' | 'produced_only' | 'hidden_tags'
    hidden_tags: list of tag strings to hide (only used when mode == 'hidden_tags')
    Returns True on success, False if username not found.
    """
    _require_admin()
    config = _load_config()
    if username not in config.get('users', {}):
        return False
    vis = {'mode': mode}
    if mode == 'hidden_tags' and hidden_tags:
        vis['hidden_tags'] = hidden_tags
    config['users'][username]['doc_visibility'] = vis
    _save_config(config)
    return True


def list_users() -> list[dict]:
    """Return all users as a list of dicts (no password hashes)."""
    config = _load_config()
    result = []
    for uname, udata in config.get('users', {}).items():
        result.append({
            'username': uname,
            'name': udata.get('name', uname),
            'role': udata.get('role', 'reviewer'),
        })
    return sorted(result, key=lambda u: (_role_levels_sort(u['role']), u['username']))


def _role_levels_sort(role: str) -> int:
    return {'admin': 0, 'manager': 1, 'reviewer': 2}.get(role, 99)


def list_roles() -> list[str]:
    """Return all defined roles: the three defaults plus any custom roles."""
    config = _load_config()
    custom = list((config.get('custom_roles') or {}).keys())
    return ['admin', 'manager', 'reviewer'] + sorted(custom)


def get_role_permissions_for_ui(role: str) -> set:
    """Return the permission set for a role — for display in the admin UI."""
    return _get_role_permissions(role)


def save_role_permissions(role: str, permissions: list[str]):
    """
    Persist a role's permission list to auth_config.yaml.
    Cannot modify the 'admin' wildcard role.
    Blocks '*' wildcard and validates against ALL_PERMISSIONS.
    """
    _require_admin()
    if role == 'admin':
        return  # admin always gets '*'; never overwrite
    # Block wildcard escalation
    if '*' in permissions:
        raise ValueError("Wildcard '*' permission cannot be assigned to non-admin roles")
    # Validate all permissions exist
    invalid = set(permissions) - set(ALL_PERMISSIONS)
    if invalid:
        raise ValueError(f"Unknown permissions: {', '.join(sorted(invalid))}")
    config = _load_config()
    if 'role_permissions' not in config or config['role_permissions'] is None:
        config['role_permissions'] = {}
    config['role_permissions'][role] = sorted(permissions)
    # Keep custom_roles in sync if this role is a custom role
    custom_roles = config.get('custom_roles') or {}
    if role in custom_roles:
        config['custom_roles'][role]['permissions'] = sorted(permissions)
    _save_config(config)


def create_custom_role(role_name: str, permissions: list[str]):
    """Create a new custom role with an explicit permission list.
    Blocks '*' wildcard and validates against ALL_PERMISSIONS."""
    _require_admin()
    # Block wildcard escalation
    if '*' in permissions:
        raise ValueError("Wildcard '*' permission cannot be assigned to custom roles")
    # Validate all permissions exist
    invalid = set(permissions) - set(ALL_PERMISSIONS)
    if invalid:
        raise ValueError(f"Unknown permissions: {', '.join(sorted(invalid))}")
    config = _load_config()
    if 'custom_roles' not in config or config['custom_roles'] is None:
        config['custom_roles'] = {}
    if 'role_permissions' not in config or config['role_permissions'] is None:
        config['role_permissions'] = {}
    config['custom_roles'][role_name] = {'permissions': sorted(permissions)}
    config['role_permissions'][role_name] = sorted(permissions)
    _save_config(config)


def delete_custom_role(role_name: str) -> tuple[bool, str]:
    """
    Delete a custom role. Blocked if any users are currently assigned to it.
    Returns (success, error_message).
    """
    _require_admin()
    if role_name in ('admin', 'manager', 'reviewer'):
        return False, "Cannot delete built-in roles."
    config = _load_config()
    users_with_role = [
        u for u, d in (config.get('users') or {}).items()
        if d.get('role') == role_name
    ]
    if users_with_role:
        return False, f"Cannot delete — {len(users_with_role)} user(s) assigned to this role."
    if 'custom_roles' in config and role_name in config['custom_roles']:
        del config['custom_roles'][role_name]
    if 'role_permissions' in config and role_name in config['role_permissions']:
        del config['role_permissions'][role_name]
    _save_config(config)
    return True, ""


# ---------------------------------------------------------------------------
# First-run setup
# ---------------------------------------------------------------------------
def setup_initial_admin() -> bool:
    """
    First-run setup: if no users exist, prompt to create the Admin account.
    Returns True if setup is complete (users exist), False if still setting up.
    """
    config = _load_config()
    if config.get('users'):
        return True  # Users already exist

    st.title("🔧 First-Time Setup")
    st.info("No users configured. Create your administrator account to get started.")

    with st.form("setup_form"):
        username = st.text_input("Admin Username", value="admin")
        display_name = st.text_input("Display Name", placeholder="e.g. Jane Smith")
        password = st.text_input("Password", type="password")
        password_confirm = st.text_input("Confirm Password", type="password")
        submitted = st.form_submit_button("Create Admin Account", width='stretch')

    if submitted:
        if not username or not password:
            st.error("Username and password are required.")
        elif password != password_confirm:
            st.error("Passwords don't match.")
        elif (pw_err := validate_password_complexity(password)):
            st.error(pw_err)
        else:
            create_user(username, password, display_name or username, role='admin')
            st.success(f"✅ Admin account '{username}' created! Please log in.")
            st.rerun()

    return False
