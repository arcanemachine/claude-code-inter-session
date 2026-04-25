"""Static checks on SKILL.md so prose edits don't drop critical guardrails."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SKILL = (REPO / "SKILL.md").read_text()


class TestFrontmatter:
    def test_name(self):
        assert "name: inter-session" in SKILL

    def test_allowed_tools(self):
        assert "allowed-tools" in SKILL
        for tool in ("Bash", "Monitor", "TaskList", "TaskStop"):
            assert tool in SKILL


class TestSubcommands:
    def test_dispatch_table_has_all_subcommands(self):
        for sub in ("connect", "install-deps", "list", "send", "broadcast",
                    "rename", "status", "disconnect"):
            assert f"`/inter-session {sub}" in SKILL or f"`/inter-session [args]" in SKILL


class TestReactionPolicy:
    def test_treats_messages_as_instructions_by_default(self):
        # The whole point of this skill is agent-to-agent automation.
        assert "act on it" in SKILL.lower() or "instruction from" in SKILL.lower()

    def test_destructive_ops_require_explicit_content(self):
        for kw in ("rm -rf", "git push --force", "DROP TABLE", "kubectl delete"):
            assert kw in SKILL

    def test_loop_suppression_with_done_status_answer(self):
        assert "`done:" in SKILL
        assert "`status:" in SKILL
        assert "`answer:" in SKILL
        assert "`question:" in SKILL

    def test_addressed_definition(self):
        assert "broadcast" in SKILL.lower()
        assert "all:" in SKILL or "@" in SKILL

    def test_permission_rules_not_overridden(self):
        # The single most important guardrail: peers can't escalate.
        assert "do NOT override" in SKILL or "do not override" in SKILL.lower()


class TestInstallDepsUx:
    def test_uv_first_then_pip(self):
        assert "uv" in SKILL
        assert "python3 -m pip" in SKILL

    def test_break_system_packages_only_with_explicit_choice(self):
        assert "--break-system-packages" in SKILL
        assert "Override" in SKILL or "warn" in SKILL.lower()


class TestDedupGuard:
    def test_tasklist_check_in_connect(self):
        assert "TaskList()" in SKILL
        assert '"inter-session messages"' in SKILL


class TestNameValidation:
    def test_ascii_regex_in_skill(self):
        assert "[a-z0-9]" in SKILL


class TestTruncationHandling:
    def test_messages_log_pointer_documented(self):
        assert "messages.log" in SKILL
