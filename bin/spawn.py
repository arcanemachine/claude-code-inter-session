"""Server election + detached spawn. Unix-only for v1."""

from __future__ import annotations

import errno
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

from bin import shared

_SERVER_PATH = Path(__file__).parent / "server.py"


def is_server_up(host: str, port: int, timeout: float = 0.3) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def wait_for_server(host: str, port: int, timeout: float = 5.0) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        if is_server_up(host, port):
            return True
        time.sleep(0.05)
    return False


def ensure_server_running(
    port: int = shared.DEFAULT_PORT,
    host: str = "127.0.0.1",
    idle_shutdown_minutes: float = 10,
    server_path: Path = _SERVER_PATH,
    python: str = sys.executable,
) -> bool:
    """Ensure a server is listening on (host, port). Race-safe via bind() election.

    Returns True if a server is up after this call (either preexisting, or freshly
    spawned by us, or freshly spawned by a peer that won the bind race).
    """
    import logging
    log = logging.getLogger("inter-session.spawn")
    if is_server_up(host, port):
        log.info("ensure: already up")
        return True

    log.info("ensure: not up, attempting bind")
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # SO_REUSEADDR=1: allow rebind after a previous server crashed. bind() is
    # still atomic across concurrent peers, so race detection works either way.
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind((host, port))
    except OSError as e:
        s.close()
        log.info("ensure: bind failed errno=%s", e.errno)
        if e.errno in (errno.EADDRINUSE, errno.EACCES):
            return wait_for_server(host, port, timeout=2.0)
        raise

    log.info("ensure: bind succeeded; spawning server")
    shared.secure_dir(shared.data_dir())
    shared.ensure_token(shared.token_path())

    os.set_inheritable(s.fileno(), True)
    log_path = shared.server_log_path()
    log_fd = os.open(str(log_path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        proc = subprocess.Popen(
            [
                python,
                str(server_path),
                "--fd", str(s.fileno()),
                "--host", str(host),
                "--port", str(port),
                "--idle-shutdown-minutes", str(idle_shutdown_minutes),
            ],
            pass_fds=(s.fileno(),),
            stdin=subprocess.DEVNULL,
            stdout=log_fd,
            stderr=log_fd,
            start_new_session=True,
            close_fds=True,
        )
        log.info("ensure: spawned server pid=%s", proc.pid)
    finally:
        os.close(log_fd)
    s.close()
    ready = wait_for_server(host, port, timeout=5.0)
    log.info("ensure: wait_for_server returned %s", ready)
    return ready
