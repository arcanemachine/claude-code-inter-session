"""Static validation of the plugin manifest + monitors config."""

from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


class TestPluginJson:
    def test_loads(self):
        cfg = json.loads((REPO / ".claude-plugin" / "plugin.json").read_text())
        assert cfg["name"] == "inter-session"
        assert cfg["skills"] == ["./"]
        assert cfg["monitors"] == "./monitors/monitors.json"

    def test_user_config_shape(self):
        cfg = json.loads((REPO / ".claude-plugin" / "plugin.json").read_text())
        uc = cfg["userConfig"]
        assert "port" in uc
        assert uc["port"]["type"] == "number"
        assert uc["port"]["default"] == 9473
        assert "idle_shutdown_minutes" in uc


class TestMonitorsJson:
    def test_loads(self):
        monitors = json.loads((REPO / "monitors" / "monitors.json").read_text())
        assert isinstance(monitors, list)
        assert len(monitors) == 1
        m = monitors[0]
        assert m["name"] == "inter-session-client"
        assert m["description"] == "inter-session messages"
        assert m["when"] == "always"
        assert "${CLAUDE_PLUGIN_ROOT}/bin/client.py" in m["command"]

    def test_command_works_in_plugin_dir_mode(self):
        """`--plugin-dir` mode does NOT run the userConfig prompt, so the
        monitor command must not depend on `${user_config.*}` substitution.
        Defaults are read from env vars by client.py instead."""
        m = json.loads((REPO / "monitors" / "monitors.json").read_text())[0]
        assert "${user_config" not in m["command"], (
            "monitors.json must not use ${user_config.*}: it breaks --plugin-dir "
            "loading because CC doesn't prompt + substitute in that mode. "
            "Read CLAUDE_PLUGIN_OPTION_* env vars in client.py instead."
        )

    def test_command_uses_plugin_root(self):
        m = json.loads((REPO / "monitors" / "monitors.json").read_text())[0]
        assert "${CLAUDE_PLUGIN_ROOT}" in m["command"]

    def test_command_does_not_hardcode_userconfig_args(self):
        """Hardcoded `--port` / `--idle-shutdown-minutes` would override the
        argparse defaults in client.py, which read the configured values
        from CLAUDE_PLUGIN_OPTION_* env vars CC injects from userConfig.
        Hardcoding the defaults silently nullifies the user's plugin config.
        """
        m = json.loads((REPO / "monitors" / "monitors.json").read_text())[0]
        for forbidden in ("--port", "--idle-shutdown-minutes"):
            assert forbidden not in m["command"], (
                f"monitors.json must not pass {forbidden}; CC's userConfig "
                f"is delivered via CLAUDE_PLUGIN_OPTION_* env vars and a "
                f"hardcoded CLI arg would override it."
            )


class TestRepoRootHasSkillMd:
    def test_skill_md_at_root(self):
        # plugin.json sets "skills": ["./"] so the SKILL.md must live at the repo root.
        assert (REPO / "SKILL.md").is_file()

    def test_skill_md_has_frontmatter_name(self):
        first = (REPO / "SKILL.md").read_text().splitlines()
        assert first[0] == "---"
        assert "name: inter-session" in "\n".join(first[:10])


class TestBinScriptsExist:
    def test_client_py(self):
        assert (REPO / "bin" / "client.py").is_file()

    def test_server_py(self):
        assert (REPO / "bin" / "server.py").is_file()

    def test_send_and_list(self):
        assert (REPO / "bin" / "send.py").is_file()
        assert (REPO / "bin" / "list.py").is_file()


class TestRequirements:
    def test_runtime_deps(self):
        req = (REPO / "requirements.txt").read_text()
        assert "websockets" in req
        assert "psutil" in req

    def test_dev_deps_inherit_runtime(self):
        dev = (REPO / "requirements-dev.txt").read_text()
        assert "-r requirements.txt" in dev
        assert "pytest" in dev
