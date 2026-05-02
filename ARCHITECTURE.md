# Architecture

An agent-to-agent messaging bus for Claude Code. Multiple Claude Code
sessions on the same Unix machine connect to a shared localhost
WebSocket server and exchange messages that drive actions in receiving
sessions.

Single user, single machine. Unix-only (macOS / Linux / WSL2).

## Process model

Three process classes cooperate over a localhost WebSocket:

```
┌─────────────────────────────────────────────────────────────────┐
│                    Claude Code Session A                        │
│                                                                 │
│  ┌──────────────┐    stdout     ┌───────────────────────────┐  │
│  │  Claude Code  │◄────────────│  client.py (monitor)       │  │
│  │  (LLM host)   │             │  role=agent, long-lived    │  │
│  └──────┬───────┘              │  ppid-flock dedup          │  │
│         │ Bash/Monitor          └─────────┬─────────────────┘  │
│         │                                 │                     │
│  ┌──────▼───────┐                         │ WebSocket           │
│  │  send.py      │── role=control ──┐     │                     │
│  │  list.py      │                  │     │                     │
│  └──────────────┘                   │     │                     │
└─────────────────────────────────────│─────│─────────────────────┘
                                      │     │
                              ┌───────▼─────▼───────┐
                              │                      │
                              │     server.py        │
                              │  single instance     │
                              │  per port            │
                              │                      │
                              └───────┬─────┬────────┘
                                      │     │
┌─────────────────────────────────────│─────│─────────────────────┐
│                    Claude Code Session B   │                     │
│                                      │     │                     │
│  ┌──────────────┐                   │     │                     │
│  │  send.py      │── role=control ──┘     │                     │
│  │  list.py      │                        │                     │
│  └──────────────┘                         │                     │
│                                           │ WebSocket           │
│  ┌──────────────┐    stdout     ┌─────────┴─────────────────┐  │
│  │  Claude Code  │◄────────────│  client.py (monitor)       │  │
│  │  (LLM host)   │             │  role=agent, long-lived    │  │
│  └──────────────┘              └───────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### server.py — Message router

A single detached asyncio WebSocket server per port. Started by
whichever client wins the bind election (see below). Responsibilities:

- **Agent registry** — maps `session_id` to connection state (name,
  label, cwd, pid, nonce, websocket handle, join timestamp).
- **Message routing** — direct (point-to-point) and broadcast (fan-out
  to all agents except sender).
- **Message log** — JSONL at `~/.claude/data/inter-session/messages.log`,
  size-rotated, chmod 0600.
- **Idle shutdown** — exits after N minutes with zero agents connected
  (default 10 min, configurable).
- **Authentication** — bearer token stored at
  `~/.claude/data/inter-session/token`, verified on every `hello`.

### client.py — Per-session monitor

A long-lived WebSocket client, one per Claude Code session. Runs as a
Claude Code monitor task — each line it prints to stdout becomes a
notification the LLM sees.

- **Dedup** — exclusive flock on `<ppid>.lock` prevents two monitors
  for the same CC session. Duplicate spawns exit immediately.
- **Session state** — atomically writes identity (session_id, name,
  token, nonce, host, port) to `<ppid>.session` so helper CLIs can
  discover their owning listener.
- **Reconnect** — exponential backoff (0.25 s → 4 s) with 20% jitter.
  Resets on clean disconnect.
- **Name collision** — auto-retries with server-suggested names (up to
  3 attempts).
- **Notification format** —
  `[inter-session msg=<id> from="<name>"] <text>`. Messages over 256 KB
  are truncated with a pointer to `messages.log`.

### send.py / list.py — Ephemeral control CLIs

Short-lived helpers invoked by the LLM via Bash tool calls. Connect
with `role=control`, perform one operation, and disconnect. Control
connections never appear in the agent list.

- **send.py** — sends a direct message (`--to <name>`) or broadcast
  (`--all`). Discovers its owning listener via `discover.py`.
- **list.py** — queries connected agents. Has a `--self` mode that
  checks local state without connecting to the server.

## Server election

Race-free, bind-atomic. No external coordination needed.

```
Client A               Client B               Port 9473
   │                      │                       │
   ├── socket()           │                       │
   ├── bind(:9473) ──── wins ──────────────────►  │ (bound)
   │                      │                       │
   │                      ├── socket()            │
   │                      ├── bind(:9473) ─── EADDRINUSE
   │                      │   (becomes a client)  │
   │                                              │
   ├── Popen(server.py --fd=N, pass_fds=(N,))     │
   │   └── start_new_session=True (detached)      │
   │                                              │
   │               server.py                      │
   │                  ├── socket(fileno=N)         │
   │                  ├── listen()                 │
   │                  └── serving                  │
   │                                              │
   ├── (now connects as a normal client)          │
```

Key details:
- `SO_REUSEADDR=1` allows fast rebind after a SIGKILL'd server.
- `os.set_inheritable(fd, True)` is required — Python's PEP 446 sets
  `FD_CLOEXEC` by default, which would silently close the socket on
  `execvp`.
- The server writes its pidfile and `.meta` before calling `listen()`,
  closing the race where a TCP probe succeeds before identity files
  exist.

## Message protocol

All messages are JSON over WebSocket text frames.

### Connection lifecycle

```
Client                          Server
  │                                │
  ├── ws connect ─────────────────►│
  │                                │
  ├── hello ──────────────────────►│  (token, role, name,
  │   { token, role, session_id,   │   label, cwd, pid, nonce)
  │     name, label, cwd, pid,     │
  │     nonce, [for_session] }     │
  │                                │
  │◄────────────────── welcome ────┤  (session_id, assigned_name)
  │                                │
  │◄──────────── peer_joined ──────┤  (broadcast to others)
  │                                │
  │        ... messages ...        │
  │                                │
  ├── bye ────────────────────────►│
  │                                │
  │◄──────────── peer_left ────────┤  (broadcast to others)
```

### Operations

| Operation   | Direction       | Purpose                              |
|:------------|:----------------|:-------------------------------------|
| `hello`     | client → server | Authenticate and register             |
| `welcome`   | server → client | Confirm registration                  |
| `send`      | client → server | Direct message to one agent           |
| `broadcast` | client → server | Message to all agents                 |
| `msg`       | server → client | Delivered message (direct or bcast)   |
| `list`      | client → server | Query connected agents                |
| `list_ok`   | server → client | Agent list response                   |
| `rename`    | client → server | Change display name                   |
| `renamed`   | server → client | Broadcast name change to peers        |
| `ping`      | client → server | Keep-alive                            |
| `pong`      | server → client | Keep-alive response                   |
| `bye`       | client → server | Graceful disconnect                   |
| `peer_joined` | server → client | Agent connected (broadcast)        |
| `peer_left`   | server → client | Agent disconnected (broadcast)     |
| `error`     | server → client | Error with code and message           |

### Target resolution (direct messages)

The `to` field in `send` is resolved through a four-tier cascade:

1. Exact `session_id` match
2. Exact `name` match
3. Name prefix match (ambiguous → error with candidates)
4. Session ID prefix match (minimum 4 characters)

### Message size limits

| Boundary               | Limit  |
|:-----------------------|:-------|
| WebSocket frame        | 16 MB  |
| Direct message text    | 10 MB  |
| Broadcast message text | 256 KB |
| Stdout notification    | 256 KB (truncated with log pointer) |

### Rate limiting

Broadcast only. 60 messages per minute per listener session. Keyed by
the listener's session_id (not per-connection) to prevent control-role
bypass. No rate limit on direct messages, list, or rename.

## Messaging model

This is a **message bus**, not pub/sub. The distinction matters:

- **No topics or channels.** There is one flat namespace of connected
  agents.
- **No subscriptions.** Every agent implicitly receives all broadcasts
  and peer lifecycle events.
- **Two routing modes:** direct (point-to-point, addressed by name or
  session ID) and broadcast (fan-out to all agents except sender).
- **No message persistence or replay.** Messages are delivered to
  currently connected agents only. The server logs messages to disk for
  large-message retrieval, not for replay.

## Security model

Defense-in-depth for a single-user localhost service:

- **Bearer token** — randomly generated 32-byte URL-safe token, stored
  chmod 0600. Required in every `hello` handshake.
- **Server identity verification** — before sending the token, clients
  verify the server process via pidfile + `.meta` (pid, cmdline, host,
  port). Blocks accidental token leakage to a port squatter.
- **Control nonce cross-check** — control connections must present
  `for_session` + `nonce` matching their owning listener's registered
  state. Prevents sibling processes from impersonating a session.
- **Name validation** — strict ASCII regex `^[a-z0-9][a-z0-9-]{0,39}$`.
  Labels are NFC-normalized Unicode with category restrictions (no
  control, format, surrogate, or whitespace characters).
- **Input sanitization** — ANSI escape stripping, newline replacement,
  control character removal on all user-supplied text.

## File layout

```
skills/inter-session/
├── SKILL.md              # LLM-facing skill definition & reaction policy
├── requirements.txt      # Runtime deps (websockets, psutil)
└── bin/
    ├── server.py         # WebSocket server (message router)
    ├── client.py         # Per-session monitor (long-lived)
    ├── send.py           # Send direct or broadcast message
    ├── list.py           # Query connected agents
    ├── spawn.py          # Server election + process spawn
    ├── discover.py       # Process-tree walk to find owning listener
    ├── shared.py         # Paths, validation, constants, token mgmt
    └── auto_start.py     # Toggle monitor launch mode (lazy ↔ always)
```

## Runtime data

All runtime state lives under `~/.claude/data/inter-session/`
(overridable via `INTER_SESSION_DATA_DIR`):

| File                    | Purpose                                |
|:------------------------|:---------------------------------------|
| `token`                 | Shared bearer token (chmod 0600)       |
| `server.<port>.pid`     | Server pidfile                         |
| `server.<port>.pid.meta`| Server identity metadata (JSON)        |
| `<ppid>.lock`           | Per-session flock (dedup)              |
| `<ppid>.session`        | Listener state for helper discovery    |
| `messages.log`          | JSONL message log (size-rotated)       |

## Install modes

**Plugin** (recommended): installed via Claude Code plugin system.
Adds `userConfig` for port and idle-shutdown tuning. Monitor configured
in `monitors/monitors.json` with lazy start by default
(`on-skill-invoke:inter-session`). User invokes as
`/inter-session:inter-session`.

**Standalone skill**: symlink or copy `skills/inter-session/` to
`~/.claude/skills/inter-session/`. Self-contained — no plugin manifest
needed. Override defaults via `INTER_SESSION_PORT` /
`INTER_SESSION_IDLE_MINUTES` env vars. User invokes as
`/inter-session`.

## Configuration

| Setting              | Plugin userConfig            | Env var                              | Default |
|:---------------------|:-----------------------------|:-------------------------------------|:--------|
| Server port          | `port`                       | `INTER_SESSION_PORT`                 | 9473    |
| Idle shutdown (min)  | `idle_shutdown_minutes`      | `INTER_SESSION_IDLE_MINUTES`         | 10      |

Plugin userConfig values are delivered as `CLAUDE_PLUGIN_OPTION_*` env
vars by Claude Code, not via CLI args in `monitors.json`. This is
intentional — hardcoding args in the monitor command would override user
config silently.
