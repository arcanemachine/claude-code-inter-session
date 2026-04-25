# inter-session

Agent-to-agent messaging for Claude Code sessions on the same machine. Each
Claude Code session connects to a local WebSocket bus and can send messages
to other connected sessions; incoming messages are delivered to the
receiving agent as stdout notifications and **acted on as instructions by
default** (with safety guardrails — see
[SKILL.md](./skills/inter-session/SKILL.md)). One session can drive
another.

Localhost only and Unix-only (macOS, Linux, WSL2) for now.

## Prerequisites

- Python ≥ 3.10
- Claude Code ≥ 2.1.105

## Install

In any Claude Code session:

```
/plugin marketplace add https://github.com/yilunzhang/claude-code-inter-session
/plugin install inter-session
```

Then start using it:

```
/inter-session:inter-session
```

Claude handles runtime dependency install automatically on first use — no
extra setup needed.

By default the monitor starts **lazily** — it spins up the first time
you invoke any `/inter-session:inter-session` command in a given Claude
Code session. To switch to always-on auto-start at every session open,
run `/inter-session:inter-session auto-start on` (then `/reload-plugins`).

## Quick example

Two Claude Code sessions on the same machine:

**Session A** (in `~/proj/auth`):
```
/inter-session:inter-session
→ Connecting as `auth-refactor`…
```

**Session B** (in `~/proj/payments`):
```
/inter-session:inter-session
→ Connecting as `payments-debug`…
```

Note: session B can also be in the same directory as A, but setting a name for each session is recommended to distinguish between sessions.

**Session A**:
```
send the bug you found to payments session and ask it to fix it.
```

**Session B** receives a notification, fixes the bug, and replies:
```
[inter-session msg=q7r8 from="auth-refactor"] null deref in checkout.py:42 — user.email is unchecked; please add a guard and verify with the existing tests
→ Edits checkout.py to add the null guard
→ Runs pytest — 47 tests pass
→ Bash: send.py --to auth-refactor --text 'done: guarded user.email at checkout.py:42; 47 tests pass'
```

**Session A** sees:
```
[inter-session msg=k2m9 from="payments-debug"] done: guarded user.email at checkout.py:42; 47 tests pass
```

The receiving agent applies guardrails before acting (see the Reaction
policy section of [SKILL.md](./skills/inter-session/SKILL.md)) —
destructive operations require explicit affirmative content; ambiguous
requests prompt a `question:` clarifier first.

## Slash commands

| Command                                                        | What it does                                                   |
| :------------------------------------------------------------- | :------------------------------------------------------------- |
| `/inter-session:inter-session`                                 | Connect (alias for `connect`).                                 |
| `/inter-session:inter-session connect [name]`                  | Connect to the bus; `name` proposed from context if omitted.   |
| `/inter-session:inter-session list`                            | List connected sessions.                                       |
| `/inter-session:inter-session send <name> <text>`              | Send a message to one session.                                 |
| `/inter-session:inter-session broadcast <text>`                | Send to all other sessions (≤ 256 KB).                         |
| `/inter-session:inter-session rename <new-name>`               | Rename — implemented as disconnect + reconnect.                |
| `/inter-session:inter-session status`                          | Heuristic connection state.                                    |
| `/inter-session:inter-session disconnect`                      | Stop the monitor.                                              |
| `/inter-session:inter-session auto-start [on\|off\|status]`    | Toggle auto-start. `on` = start at every session; `off` = lazy (default). Apply with `/reload-plugins`. |

## Plugin configuration

The WebSocket port and idle-shutdown timeout are configurable via
`/plugin config`:

| Key                       | Type   | Default | What it does                                              |
| :------------------------ | :----- | :------ | :-------------------------------------------------------- |
| `port`                    | number | `9473`  | Localhost WebSocket port for the bus.                     |
| `idle_shutdown_minutes`   | number | `10`    | Server exits after this many minutes with no connected clients. `0` = never. |

## Security

- Server binds `127.0.0.1` only.
- Bearer token at `~/.claude/data/inter-session/token` (mode `0600`,
  directory `0700`).
- Any process running as the same Unix user can read the token and
  connect. This is acceptable for single-user, single-machine.
- The token does **not** protect against malicious code running as your
  user. If you don't trust local code, don't enable inter-session.
- The receiving agent's reaction policy (see
  [SKILL.md](./skills/inter-session/SKILL.md)) treats peer messages as
  instructions but applies the same caution as user input —
  destructive ops need explicit affirmative content, ambiguous requests
  prompt a `question:` first, broadcasts are informational unless
  addressed via `@<your-name>`.

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
