"""User settings, stored as JSON in $XDG_CONFIG_HOME/minisnap/settings.json.

Pure standard library so it can be used before GTK starts.
"""

import json
import os
import tempfile

DEFAULTS = {
    "language": None,            # "vi", "en" or None (= follow LANG)
    "ask_after_select": True,    # show the screenshot / video / scroll bar after a region is selected
    "auto_update_check": True,   # daily check against api.github.com (see PRIVACY.md)
    "last_update_check": None,   # ISO 8601 UTC time of the last check
    "remote_desktop_restore_token": None,   # RemoteDesktop portal token: no permission dialog every time
    "global_shortcuts_enabled": False,      # bind shortcuts through the GlobalShortcuts portal, run in background
    "global_shortcuts_notified": False,     # the "runs in the background" notification was shown once
}

_cache = None


def config_dir():
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "minisnap")


def config_path():
    return os.path.join(config_dir(), "settings.json")


def load(force=False):
    """All settings, with defaults for anything missing or unreadable."""
    global _cache
    if _cache is not None and not force:
        return _cache
    data = dict(DEFAULTS)
    try:
        with open(config_path(), "r", encoding="utf-8") as f:
            saved = json.load(f)
        if isinstance(saved, dict):
            for k in DEFAULTS:
                if k in saved:
                    data[k] = saved[k]
    except (OSError, ValueError):
        pass
    _cache = data
    return data


def get(key):
    return load().get(key, DEFAULTS.get(key))


def set(key, value):  # noqa: A001 - mirrors get()
    """Changes one setting and writes the file atomically. Raises OSError if it cannot be saved."""
    data = load()
    data[key] = value
    save(data)


def save(data=None):
    data = data if data is not None else load()
    folder = config_dir()
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".settings-", suffix=".json", dir=folder)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, config_path())
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def reset_cache():
    global _cache
    _cache = None
