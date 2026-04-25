"""Toggle the inter-session plugin monitor's auto-start behavior.

Edits the `when` field of the inter-session-client monitor in
`${CLAUDE_PLUGIN_ROOT}/monitors/monitors.json` atomically.

Modes:
  always                          start at every CC session open
  on-skill-invoke:inter-session   start when /inter-session is first invoked

Only meaningful when running as a plugin (CLAUDE_PLUGIN_ROOT must be set).
Standalone-skill installs have no monitors.json to edit.

Changes take effect on `/reload-plugins` or the next CC session.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

ALWAYS = "always"
LAZY = "on-skill-invoke:inter-session"
MONITOR_NAME = "inter-session-client"


def _resolve_monitors_path() -> Path:
    root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if not root:
        sys.stderr.write(
            "auto_start: CLAUDE_PLUGIN_ROOT is not set. This command only "
            "applies when inter-session is installed as a plugin; "
            "standalone-skill installs have no monitors.json to edit.\n"
        )
        sys.exit(2)
    p = Path(root) / "monitors" / "monitors.json"
    if not p.is_file():
        sys.stderr.write(f"auto_start: {p} not found\n")
        sys.exit(2)
    return p


def _load(path: Path) -> list:
    monitors = json.loads(path.read_text())
    if not isinstance(monitors, list):
        sys.stderr.write("auto_start: monitors.json must be a JSON list\n")
        sys.exit(2)
    return monitors


def _find_entry(monitors: list) -> dict:
    for m in monitors:
        if isinstance(m, dict) and m.get("name") == MONITOR_NAME:
            return m
    sys.stderr.write(
        f"auto_start: no monitor named {MONITOR_NAME!r} found in monitors.json\n"
    )
    sys.exit(2)


def _atomic_write(path: Path, data: str) -> None:
    fd, tmp = tempfile.mkstemp(prefix=".monitors.", suffix=".json", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def cmd_status() -> int:
    path = _resolve_monitors_path()
    entry = _find_entry(_load(path))
    when = entry.get("when", "always")
    if when == ALWAYS:
        label = "ON  (auto-start at every session)"
    elif when == LAZY:
        label = "OFF (lazy: starts on first /inter-session invocation)"
    else:
        label = f"CUSTOM ({when})"
    print(f"auto-start: {label}")
    print(f"  when: {when}")
    print(f"  file: {path}")
    return 0


def cmd_set(target: str) -> int:
    path = _resolve_monitors_path()
    monitors = _load(path)
    entry = _find_entry(monitors)
    prev = entry.get("when", "always")
    if prev == target:
        print(f"auto-start: already {target!r}; no change")
        return 0
    entry["when"] = target
    _atomic_write(path, json.dumps(monitors, indent=2) + "\n")
    print(f"auto-start: {prev!r} -> {target!r}")
    print("Reload to apply: /reload-plugins (or open a new Claude Code session).")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--status", action="store_true", help="print current setting")
    g.add_argument("--on", action="store_true", help=f'set when="{ALWAYS}"')
    g.add_argument("--off", action="store_true", help=f'set when="{LAZY}"')
    args = parser.parse_args(argv)

    if args.status:
        return cmd_status()
    if args.on:
        return cmd_set(ALWAYS)
    if args.off:
        return cmd_set(LAZY)
    return 2  # unreachable due to required=True


if __name__ == "__main__":
    raise SystemExit(main())
