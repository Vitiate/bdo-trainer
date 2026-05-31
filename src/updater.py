"""
Updater - Checks GitHub Releases for a newer version, downloads the
zipball, extracts it over the project tree (skipping user data such as
config/ and logs/), and prompts the user to restart.

No GitHub authentication is required: the public REST API is reached
through stdlib ``urllib``.

Public API
----------
- ``check_and_prompt(...)`` — call from any thread. Hits GitHub, decides
  whether to prompt, and (on the Tk thread) shows the changelog dialog.
- ``UpdateInfo`` — result of a release lookup (used by the tray for the
  manual "Check for Updates…" command).
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
import re
import shutil
import threading
import tkinter as tk
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Callable, Optional

from src import __version__ as APP_VERSION

logger = logging.getLogger("bdo_trainer")

GITHUB_REPO = "Vitiate/bdo-trainer"
RELEASES_LATEST_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
RELEASES_LIST_URL = (
    f"https://api.github.com/repos/{GITHUB_REPO}/releases?per_page=30"
)
USER_AGENT = "BDO-Trainer-Updater"
HTTP_TIMEOUT = 15  # seconds

VALID_CHANNELS = ("stable", "beta")

# Paths skipped when extracting the new release over the project tree.
# Preserves user data + the running Python environment + version control.
_SKIP_TOP_LEVEL = {
    "config",
    "logs",
    ".venv",
    "venv",
    ".git",
    "_update",
    "__pycache__",
}


def _force_to_front(toplevel: tk.Misc) -> None:
    """Keep a Toplevel reliably in front for its lifetime (macOS-friendly).

    On macOS, a Toplevel created next to a parent that already has
    ``-topmost True`` set will lose the z-order race; clicking around can
    bury it. We:
      • Suspend the parent's ``-topmost`` for the dialog's lifetime,
        restoring it on destroy.
      • Re-apply ``-topmost True`` + ``lift`` + ``focus_force`` on a few
        ticks to outlast OS reordering.
    """
    parent = toplevel.master
    parent_was_topmost = False
    if parent is not None:
        try:
            parent_was_topmost = bool(parent.attributes("-topmost"))
            if parent_was_topmost:
                parent.attributes("-topmost", False)
        except tk.TclError:
            parent_was_topmost = False

    def _bring_up() -> None:
        try:
            toplevel.attributes("-topmost", True)
            toplevel.lift()
            toplevel.focus_force()
        except tk.TclError:
            pass

    _bring_up()
    try:
        toplevel.after_idle(_bring_up)
        toplevel.after(50, _bring_up)
        toplevel.after(150, _bring_up)
        toplevel.after(400, _bring_up)
    except tk.TclError:
        pass

    def _on_destroy(event: Optional[tk.Event] = None) -> None:
        if event is not None and event.widget is not toplevel:
            return
        if parent is not None and parent_was_topmost:
            try:
                if parent.winfo_exists():
                    parent.attributes("-topmost", True)
            except tk.TclError:
                pass

    try:
        toplevel.bind("<Destroy>", _on_destroy, add="+")
    except tk.TclError:
        pass


@dataclass
class UpdateInfo:
    tag: str
    name: str
    body: str
    zipball_url: str
    html_url: str
    prerelease: bool = False

    @property
    def display_version(self) -> str:
        return self.tag.lstrip("vV")

    @property
    def channel_label(self) -> str:
        return "Beta" if self.prerelease else "Stable"


# ---------------------------------------------------------------------------
# Version comparison
# ---------------------------------------------------------------------------
_NUM_PREFIX = re.compile(r"^(\d+)")


def _normalize(version: str) -> tuple[int, ...]:
    """Split ``"v1.2.3-rc1"`` → ``(1, 2, 3)``. Stops at the first non-numeric
    component so we ignore pre-release suffixes for the >/< comparison."""
    cleaned = version.strip().lstrip("vV")
    parts = re.split(r"[.\-+_]", cleaned)
    out: list[int] = []
    for p in parts:
        m = _NUM_PREFIX.match(p)
        if not m:
            break
        out.append(int(m.group(1)))
    return tuple(out)


def is_newer(remote: str, local: str) -> bool:
    """True if *remote* sorts strictly above *local*."""
    r, l = _normalize(remote), _normalize(local)
    if not r:
        return False
    return r > l


# ---------------------------------------------------------------------------
# GitHub API
# ---------------------------------------------------------------------------
def _release_from_payload(payload: dict) -> Optional[UpdateInfo]:
    tag = payload.get("tag_name") or ""
    if not tag:
        return None
    return UpdateInfo(
        tag=tag,
        name=payload.get("name") or tag,
        body=payload.get("body") or "",
        zipball_url=payload.get("zipball_url") or "",
        html_url=payload.get("html_url") or "",
        prerelease=bool(payload.get("prerelease")),
    )


def _http_get_json(url: str, timeout: int):
    """Tiny helper: GET *url* and decode as JSON, returning ``None`` on
    any failure (network, HTTP, malformed JSON)."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/vnd.github+json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        logger.warning(f"Update check: HTTP {exc.code} from GitHub")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        logger.warning(f"Update check: network error — {exc}")
    except (ValueError, json.JSONDecodeError) as exc:
        logger.warning(f"Update check: malformed JSON — {exc}")
    return None


def fetch_latest_release(
    channel: str = "stable",
    timeout: int = HTTP_TIMEOUT,
) -> Optional[UpdateInfo]:
    """Return the latest release for *channel*.

    - ``"stable"`` — latest non-prerelease (uses ``/releases/latest``,
      which excludes prereleases server-side and never 404s on draft).
    - ``"beta"``   — newest release overall, prerelease or not. We pull
      ``/releases?per_page=30`` and pick the highest version tag.

    Returns ``None`` on any network/parse failure or if no qualifying
    release exists.
    """
    ch = channel if channel in VALID_CHANNELS else "stable"

    if ch == "stable":
        payload = _http_get_json(RELEASES_LATEST_URL, timeout)
        if not isinstance(payload, dict):
            return None
        return _release_from_payload(payload)

    # Beta channel — prereleases are eligible too.
    payload = _http_get_json(RELEASES_LIST_URL, timeout)
    if not isinstance(payload, list):
        return None
    candidates: list[UpdateInfo] = []
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        if entry.get("draft"):
            continue
        info = _release_from_payload(entry)
        if info is not None:
            candidates.append(info)
    if not candidates:
        return None
    # Newest by version key, ties broken by stable winning over beta so a
    # 0.5.4 stable beats a 0.5.4 prerelease (shouldn't happen in practice
    # but keeps the order deterministic).
    candidates.sort(
        key=lambda r: (_normalize(r.tag), 0 if r.prerelease else 1),
        reverse=True,
    )
    return candidates[0]


# ---------------------------------------------------------------------------
# Download + install
# ---------------------------------------------------------------------------
def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def download_zipball(
    info: UpdateInfo,
    progress_cb: Optional[Callable[[int, int], None]] = None,
) -> Path:
    """Download the release zipball to ``<project>/_update/<tag>.zip`` and
    return the path. *progress_cb(received, total)* is invoked from the
    download thread (total may be ``-1`` if the server omits Content-Length)."""
    staging = _project_root() / "_update"
    staging.mkdir(exist_ok=True)
    out_path = staging / f"{info.tag}.zip"

    req = urllib.request.Request(info.zipball_url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        total = int(resp.headers.get("Content-Length") or -1)
        received = 0
        chunk_size = 64 * 1024
        with open(out_path, "wb") as fh:
            while True:
                chunk = resp.read(chunk_size)
                if not chunk:
                    break
                fh.write(chunk)
                received += len(chunk)
                if progress_cb:
                    progress_cb(received, total)
    logger.info(f"Update: downloaded {out_path.name} ({received} bytes)")
    return out_path


def install_zipball(zip_path: Path, replace_config: bool = False) -> Optional[Path]:
    """Extract the zipball over the project tree, preserving user data.

    Args:
        zip_path: The downloaded source zipball.
        replace_config: When True, back up the current ``config/`` directory
            to ``config_backup_<YYYYMMDD-HHMMSS>/`` before extracting, so
            the new release's ``config/`` can be written over the empty
            slot. When False (default), ``config/`` is preserved untouched.

    Returns:
        The backup directory path if ``replace_config`` was True and a
        backup was actually made, otherwise ``None``.

    The GitHub source zipball wraps everything in a top-level
    ``<owner>-<repo>-<sha>/`` directory; we strip that prefix when copying.
    """
    project = _project_root()
    extract_root = project / "_update" / "extracted"
    if extract_root.exists():
        shutil.rmtree(extract_root, ignore_errors=True)
    extract_root.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(extract_root)

    # Find the single top-level directory the zipball produced.
    top_dirs = [p for p in extract_root.iterdir() if p.is_dir()]
    if len(top_dirs) != 1:
        raise RuntimeError(
            f"Unexpected zipball layout: {len(top_dirs)} top-level dirs in {extract_root}"
        )
    src_root = top_dirs[0]

    # If the user opted in to replacing configs, move the current config/
    # aside to a timestamped backup so the new files install cleanly.
    backup_dir: Optional[Path] = None
    skip_top = set(_SKIP_TOP_LEVEL)
    if replace_config:
        live_config = project / "config"
        if live_config.exists():
            stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
            backup_dir = project / f"config_backup_{stamp}"
            # Avoid clobbering a backup folder that somehow already exists.
            n = 1
            while backup_dir.exists():
                backup_dir = project / f"config_backup_{stamp}_{n}"
                n += 1
            shutil.move(str(live_config), str(backup_dir))
            logger.info(f"Update: backed up config/ to {backup_dir.name}/")
        # Drop config/ from the skip list so the release's config/ installs.
        skip_top.discard("config")

    copied = 0
    for src in src_root.rglob("*"):
        rel = src.relative_to(src_root)
        # Skip preserved top-level directories.
        if rel.parts and rel.parts[0] in skip_top:
            continue
        dest = project / rel
        if src.is_dir():
            dest.mkdir(parents=True, exist_ok=True)
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            copied += 1
    logger.info(f"Update: installed {copied} files into {project}")
    return backup_dir


# ---------------------------------------------------------------------------
# Tk dialog
# ---------------------------------------------------------------------------
class _UpdateDialog:
    """Modal-ish dialog that shows the changelog and walks the user through
    download → install → restart-required."""

    def __init__(self, parent: tk.Misc, info: UpdateInfo) -> None:
        self.info = info
        self.parent = parent

        # Filled in by the install handler before the worker thread runs.
        self._replace_config: bool = False
        self._backup_dir: Optional[Path] = None

        self.win = tk.Toplevel(parent)
        self.win.title("BDO Trainer — Update Available")
        self.win.geometry("640x520")
        self.win.transient(parent)
        try:
            self.win.grab_set()
        except tk.TclError:
            pass
        self.win.protocol("WM_DELETE_WINDOW", self._on_later)
        _force_to_front(self.win)

        # --- Header --------------------------------------------------------
        header = ttk.Frame(self.win, padding=(16, 14, 16, 8))
        header.pack(fill="x")
        title = (
            f"A new {info.channel_label} build is available: "
            f"{info.display_version}"
            if info.prerelease
            else f"A new version is available: {info.display_version}"
        )
        ttk.Label(
            header,
            text=title,
            font=("Segoe UI", 13, "bold"),
        ).pack(anchor="w")
        ttk.Label(
            header,
            text=f"You are running {APP_VERSION}.",
            foreground="#666",
        ).pack(anchor="w", pady=(2, 0))
        if info.prerelease:
            ttk.Label(
                header,
                text=(
                    "This is a Beta release. Disable the Beta channel in "
                    "Settings → Updates to receive only Stable releases."
                ),
                foreground="#a55",
                wraplength=580,
                justify="left",
            ).pack(anchor="w", pady=(4, 0))

        # --- Changelog -----------------------------------------------------
        body = ttk.LabelFrame(self.win, text="Release notes", padding=8)
        body.pack(fill="both", expand=True, padx=16, pady=(4, 8))
        text = tk.Text(body, wrap="word", height=14, relief="flat")
        text.insert("1.0", info.body or "(no release notes)")
        text.configure(state="disabled")
        scroll = ttk.Scrollbar(body, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self._text = text

        # --- Progress ------------------------------------------------------
        self._progress_var = tk.DoubleVar(value=0.0)
        self._progress_label_var = tk.StringVar(value="")
        progress_frame = ttk.Frame(self.win, padding=(16, 0, 16, 0))
        progress_frame.pack(fill="x")
        self._progress_bar = ttk.Progressbar(
            progress_frame,
            variable=self._progress_var,
            maximum=100,
            mode="determinate",
        )
        self._progress_bar.pack(fill="x")
        self._progress_label = ttk.Label(
            progress_frame, textvariable=self._progress_label_var, foreground="#666"
        )
        self._progress_label.pack(anchor="w", pady=(4, 0))
        self._progress_bar.pack_forget()
        self._progress_label.pack_forget()

        # --- Buttons -------------------------------------------------------
        btns = ttk.Frame(self.win, padding=(16, 4, 16, 14))
        btns.pack(fill="x")
        self._later_btn = ttk.Button(btns, text="Later", command=self._on_later)
        self._later_btn.pack(side="right", padx=(8, 0))
        self._install_btn = ttk.Button(
            btns, text="Download && Install", command=self._on_install
        )
        self._install_btn.pack(side="right")

    # ---- button handlers ------------------------------------------------
    def _on_later(self) -> None:
        try:
            self.win.grab_release()
        except tk.TclError:
            pass
        self.win.destroy()

    def _show_messagebox(self, kind: str, *args, **kwargs):
        """Wrap messagebox calls so they appear above ``self.win``.

        The native messagebox lands behind a Toplevel that already has
        ``-topmost True`` on macOS. We drop our topmost flag for the
        duration of the prompt, then restore it.
        """
        was_topmost = False
        try:
            was_topmost = bool(self.win.attributes("-topmost"))
            if was_topmost:
                self.win.attributes("-topmost", False)
        except tk.TclError:
            pass
        try:
            fn = getattr(messagebox, kind)
            return fn(*args, **kwargs)
        finally:
            if was_topmost:
                try:
                    self.win.attributes("-topmost", True)
                    self.win.lift()
                    self.win.focus_force()
                except tk.TclError:
                    pass

    def _on_install(self) -> None:
        # Ask the user whether to keep their existing configs or take the
        # ones from the new release. Default is "keep" (No) — replacing is
        # destructive and only useful if the release ships updated combos
        # the user wants verbatim.
        replace = self._show_messagebox(
            "askyesno",
            "Replace configs?",
            "Replace your existing configs with the ones from the new release?\n\n"
            "• No  — keep your current config/ (recommended).\n"
            "• Yes — back up your current config/ to "
            "config_backup_<timestamp>/ and install the release's configs "
            "in its place.",
            default="no",
            parent=self.win,
        )
        self._replace_config = bool(replace)

        self._install_btn.state(["disabled"])
        self._later_btn.state(["disabled"])
        self._progress_bar.pack(fill="x")
        self._progress_label.pack(anchor="w", pady=(4, 0))
        self._progress_label_var.set("Starting download…")
        threading.Thread(target=self._run_install, daemon=True).start()

    # ---- worker thread --------------------------------------------------
    def _run_install(self) -> None:
        try:
            zip_path = download_zipball(self.info, progress_cb=self._on_progress)
            self._post(lambda: self._progress_label_var.set("Installing…"))
            backup_dir = install_zipball(
                zip_path, replace_config=self._replace_config,
            )
            self._backup_dir = backup_dir
            self._post(self._on_install_done)
        except Exception as exc:
            logger.exception("Update install failed")
            self._post(lambda: self._on_install_failed(exc))

    def _on_progress(self, received: int, total: int) -> None:
        if total > 0:
            pct = (received / total) * 100
            self._post(lambda: self._progress_var.set(pct))
            self._post(
                lambda: self._progress_label_var.set(
                    f"Downloading… {received // 1024} / {total // 1024} KB"
                )
            )
        else:
            self._post(
                lambda: self._progress_label_var.set(
                    f"Downloading… {received // 1024} KB"
                )
            )

    def _on_install_done(self) -> None:
        self._progress_var.set(100)
        self._progress_label_var.set("Update installed.")

        msg = (
            f"Version {self.info.display_version} has been installed.\n\n"
            "Please EXIT BDO Trainer fully and relaunch it. The currently "
            "running process is still on the old code, and continuing to "
            "use it before restart can crash the app."
        )
        if self._backup_dir is not None:
            msg += (
                f"\n\nYour previous configs were backed up to:\n"
                f"{self._backup_dir.name}/"
            )
        elif self._replace_config:
            msg += (
                "\n\nNo existing config/ was found, so no backup was made."
            )

        self._show_messagebox("showinfo", "BDO Trainer", msg, parent=self.win)
        self._on_later()

    def _on_install_failed(self, exc: Exception) -> None:
        self._progress_label_var.set("")
        self._install_btn.state(["!disabled"])
        self._later_btn.state(["!disabled"])
        self._show_messagebox(
            "showerror",
            "BDO Trainer",
            f"Update failed: {exc}\n\nThe app is unchanged.",
            parent=self.win,
        )

    def _post(self, fn: Callable[[], None]) -> None:
        """Marshal a call back to the Tk thread."""
        try:
            self.win.after(0, fn)
        except tk.TclError:
            pass


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------
def show_update_dialog(parent: tk.Misc, info: UpdateInfo) -> None:
    """Open the changelog dialog. Must be called on the Tk thread."""
    _UpdateDialog(parent, info)


def show_no_update(parent: tk.Misc, channel: str = "stable") -> None:
    label = "Beta" if channel == "beta" else "Stable"
    messagebox.showinfo(
        "BDO Trainer",
        f"You're up to date (version {APP_VERSION}).\n\n"
        f"Update channel: {label}",
        parent=parent,
    )


def show_ahead_of_channel(
    parent: tk.Misc, info: UpdateInfo, channel: str
) -> None:
    """Notify the user that they're running a build newer than the
    channel they just selected (typical case: switched from beta to
    stable while running a beta build)."""
    label = "Beta" if channel == "beta" else "Stable"
    messagebox.showinfo(
        "BDO Trainer",
        f"You're running version {APP_VERSION}, which is newer than the "
        f"latest {label} release ({info.display_version}).\n\n"
        "No update will be installed. Switch back to the Beta channel "
        "in Settings → Updates if you want to keep receiving prereleases, "
        "or wait for the next Stable release.",
        parent=parent,
    )


def show_check_failed(parent: tk.Misc) -> None:
    messagebox.showwarning(
        "BDO Trainer",
        "Could not check for updates. Please try again later.",
        parent=parent,
    )


def check_and_prompt(
    schedule: Callable[[Callable[[], None]], None],
    parent_supplier: Callable[[], tk.Misc],
    *,
    show_no_update_dialog: bool = False,
    show_failure_dialog: bool = False,
    channel: str = "stable",
) -> None:
    """Run a release check on a background thread and, if a newer version
    is available, hop back onto the Tk thread to show the dialog.

    Args:
        schedule: Function that takes a callable and runs it on the Tk
            thread (typically ``overlay.schedule``).
        parent_supplier: Returns the Tk parent for the dialog. Resolved
            on the Tk thread so we never read Tk state from this worker.
        show_no_update_dialog: If True, also notify when already up to
            date. Used by the manual "Check for Updates…" tray entry.
        show_failure_dialog: If True, surface network/parse errors via
            a dialog. Otherwise failures are silent (just logged).
        channel: ``"stable"`` (default) or ``"beta"``. Beta also accepts
            prereleases as upgrade candidates.
    """
    ch = channel if channel in VALID_CHANNELS else "stable"

    def worker() -> None:
        info = fetch_latest_release(channel=ch)
        if info is None:
            logger.info(f"Update check ({ch}): no release info returned")
            if show_failure_dialog:
                schedule(lambda: show_check_failed(parent_supplier()))
            return
        if not is_newer(info.tag, APP_VERSION):
            # Either equal (up to date) or local is ahead of the channel.
            local_v = _normalize(APP_VERSION)
            remote_v = _normalize(info.tag)
            if local_v > remote_v and ch == "stable" and show_no_update_dialog:
                # Beta user manually switched to Stable while running a
                # newer beta — surface that explicitly so they don't
                # think the updater is broken.
                logger.info(
                    f"Update check (stable): local {APP_VERSION} is ahead of "
                    f"latest stable {info.tag}; not downgrading."
                )
                schedule(
                    lambda: show_ahead_of_channel(parent_supplier(), info, ch)
                )
                return
            logger.info(
                f"Update check ({ch}): latest is {info.tag}, "
                f"local is {APP_VERSION} — up to date"
            )
            if show_no_update_dialog:
                schedule(lambda: show_no_update(parent_supplier(), ch))
            return
        logger.info(
            f"Update check ({ch}): {info.tag} available (local {APP_VERSION})"
        )
        schedule(lambda: show_update_dialog(parent_supplier(), info))

    threading.Thread(target=worker, daemon=True, name="updater-check").start()
