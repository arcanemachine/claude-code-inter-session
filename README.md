# inter-session

Agent-to-agent messaging for Claude Code sessions on the same machine. Each
Claude Code session connects to a local WebSocket bus and can send messages
to other connected sessions; incoming messages are delivered to the
receiving agent as stdout notifications and **acted on as instructions by
default** (with safety guardrails — see [SKILL.md](./SKILL.md)). One
session can drive another.

Single user, single machine. Unix-only (macOS, Linux, WSL2).

## Prerequisites

- Python ≥ 3.10
- Claude Code ≥ 2.1.105 (plugin mode) or ≥ 2.1.98 (skill-only mode)
- Runtime deps: `websockets`, `psutil` (see [`requirements.txt`](./requirements.txt))

## Install

### As a skill (simplest, no auto-start)

```bash
git clone https://github.com/yilunzhang/claude-code-inter-session ~/.claude/skills/inter-session
```

Then in any Claude Code session, run `/inter-session` to connect. The
skill auto-runs `/inter-session install-deps` on first connect if
dependencies are missing.

### As a plugin (auto-starts the monitor at session open)

For local development:

```bash
claude --plugin-dir /path/to/claude-code-inter-session
```

Or install via the bundled marketplace manifest:

```bash
git clone https://github.com/yilunzhang/claude-code-inter-session
/plugin marketplace add ./claude-code-inter-session
/plugin install inter-session@inter-session
```

Then run `/inter-session install-deps` once to install runtime deps.

### Dependency install — uv preferred, pip fallback

`/inter-session install-deps` runs the right command based on what's
available. Manual equivalents:

```bash
# uv (fastest, handles PEP 668 transparently):
uv pip install --system -r requirements.txt

# system pip with user-level install:
python3 -m pip install --user -r requirements.txt

# explicit venv (most robust under PEP 668):
python3 -m venv ~/.claude/data/inter-session/venv
~/.claude/data/inter-session/venv/bin/pip install -r requirements.txt
```

## Quick example

Two Claude Code sessions on the same machine:

**Session A** (in `~/proj/auth`):
```
/inter-session
→ Connecting as `auth-refactor`…
```

**Session B** (in `~/proj/payments`):
```
/inter-session
→ Connecting as `payments-debug`…
```

**Session A**:
```
/inter-session list
NAME             CWD                       SINCE
auth-refactor    ~/proj/auth               (you)
payments-debug   ~/proj/payments           12s

/inter-session send payments-debug run pytest tests/ and report
```

**Session B** receives a notification, runs the tests, and replies:
```
[inter-session msg=q7r8 from="auth-refactor"] run pytest tests/ and report
→ pytest passes (47 tests)
→ Bash: send.py --to auth-refactor --text 'done: 47 passed in 3.2s'
```

**Session A** sees:
```
[inter-session msg=k2m9 from="payments-debug"] done: 47 passed in 3.2s
```

The receiving agent applies guardrails before acting (see the Reaction
policy section of [SKILL.md](./SKILL.md)) — destructive operations
require explicit affirmative content; ambiguous requests prompt a
`question:` clarifier first.

## Slash commands

| Command                                         | What it does                                                   |
| :---------------------------------------------- | :------------------------------------------------------------- |
| `/inter-session`                                | Connect (alias for `connect`).                                 |
| `/inter-session connect [name]`                 | Connect to the bus; `name` proposed from context if omitted.   |
| `/inter-session list`                           | List connected sessions.                                       |
| `/inter-session send <name> <text>`             | Send a message to one session.                                 |
| `/inter-session broadcast <text>`               | Send to all other sessions (≤ 256 KB).                         |
| `/inter-session rename <new-name>`              | Rename — implemented as disconnect + reconnect.                |
| `/inter-session status`                         | Heuristic connection state.                                    |
| `/inter-session disconnect`                     | Stop the monitor.                                              |
| `/inter-session install-deps`                   | One-time dependency install with confirmation.                 |

## Plugin configuration

When installed as a plugin, the WebSocket port and idle-shutdown timeout
are configurable via `/plugin config`:

| Key                       | Type   | Default | What it does                                              |
| :------------------------ | :----- | :------ | :-------------------------------------------------------- |
| `port`                    | number | `9473`  | Localhost WebSocket port for the bus.                     |
| `idle_shutdown_minutes`   | number | `10`    | Server exits after this many minutes with no connected clients. `0` = never. |

Claude Code injects these as `CLAUDE_PLUGIN_OPTION_PORT` and
`CLAUDE_PLUGIN_OPTION_IDLE_SHUTDOWN_MINUTES` env vars; `client.py`
picks them up automatically. In skill-only mode (no plugin), set
`INTER_SESSION_PORT` or `INTER_SESSION_IDLE_MINUTES` if you need to
override the defaults.

## Threat model

- Server binds `127.0.0.1` only.
- Bearer token at `~/.claude/data/inter-session/token` (mode `0600`,
  directory `0700`).
- Any process running as the same Unix user can read the token and
  connect. This is acceptable for single-user, single-machine.
- The token does **not** protect against malicious code running as your
  user. If you don't trust local code, don't enable inter-session.
- The receiving agent's reaction policy (see [SKILL.md](./SKILL.md))
  treats peer messages as instructions but applies the same caution as
  user input — destructive ops need explicit affirmative content,
  ambiguous requests prompt a `question:` first, broadcasts are
  informational unless addressed via `@<your-name>`.

## Limits

- WebSocket frame size: 16 MB.
- Direct `text` length: 10 MB.
- Broadcast `text` length: 256 KB.
- Stdout notification: 256 KB (above this, truncate + log pointer to
  `~/.claude/data/inter-session/messages.log`).
- Broadcast rate: 60 / minute / session.

## Development

TDD throughout. Test runner: `pytest` + `pytest-asyncio`.

```bash
pip install -r requirements-dev.txt
pytest -q
```

## License

MIT — see [LICENSE](./LICENSE).
