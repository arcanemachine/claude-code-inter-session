import os
import socket
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILL_DIR = REPO_ROOT / "skills" / "inter-session"
# Put the skill dir first so `from bin import ...` resolves to
# <skill-dir>/bin/, where the runtime now lives.
sys.path.insert(0, str(SKILL_DIR))


@pytest.fixture
def tmp_data_dir(tmp_path, monkeypatch):
    d = tmp_path / "inter-session"
    monkeypatch.setenv("INTER_SESSION_DATA_DIR", str(d))
    return d


@pytest.fixture
def free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port
