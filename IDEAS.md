# Ideas

Possible improvements and extensions discussed during architecture
review. Nothing here is committed — these are seeds for future work.

## Summary

1. Fix message truncation
2. Universal client / open protocol spec
3. Tiered transport (Unix socket + WSS)
4. Self-signed TLS with fingerprint trust
5. RAM-backed message delivery
6. Message chunking for large payloads

---

## 1. Fix message truncation

**Problem:** The app truncates stdout notifications at 256 KB, but
Claude Code silently clips them at a much smaller (undocumented) size.
Messages between CC's limit and 256 KB arrive incomplete with no
recovery path — no `truncated=` marker, no `cont` pointer.

**Proposed fix (three changes):**

- Lower `STDOUT_CAP` in `shared.py` to 8 KB (safely under CC's clip
  threshold).
- Always emit a `cont` log pointer for messages above a lower
  threshold (~4 KB), not just when the app's own truncation fires.
- Update SKILL.md to instruct the LLM to always fetch from
  `messages.log` when `cont` appears or text looks incomplete.

**Alternative: message chunking.** Split large messages across
multiple stdout lines, each under the clip threshold. Each chunk
carries the same `msg_id` + a part number. No extra tool call needed
if CC faithfully delivers multiple rapid notifications. Needs
empirical testing to confirm CC's behavior.

**Open question:** What is CC's actual notification size limit? A
calibration test (send messages at increasing sizes, observe what
arrives) would determine this empirically.

## 2. Universal client / open protocol spec

**Goal:** Make the protocol usable by any AI coding agent framework,
not just Claude Code.

**Approach:**
- Publish the WebSocket protocol as an AsyncAPI spec (the event-driven
  counterpart to OpenAPI).
- The protocol (hello/welcome/send/msg/broadcast/list/bye) becomes the
  universal layer.
- Each framework implements its own adapter (how notifications reach
  the LLM, how the LLM invokes send/list).
- Fork this repo: the protocol + server become a standalone project;
  the Claude Code adapter becomes one client implementation.

**What stays universal:** server, protocol, routing, registry, auth.

**What becomes per-framework:** notification delivery, process
discovery, skill/plugin packaging, reaction policy.

## 3. Tiered transport

**Goal:** Optimal transport per deployment scenario.

```
Client connects
     │
     ├── same machine? → Unix socket (no TCP overhead)
     │                   /tmp/inter-session-<uid>.sock
     │
     └── remote?       → WSS (TLS-encrypted WebSocket)
                         wss://host:port
```

- Unix sockets work on both Linux and macOS.
- Server listens on both a Unix socket and a TCP port simultaneously.
- The protocol is identical over either transport.
- `bind()` election works the same way with Unix socket paths.

## 4. Self-signed TLS with fingerprint trust

**Goal:** Secure cross-machine communication without third-party
certificates.

- Server generates a self-signed cert on first start.
- Prints SHA256 fingerprint for user to verify.
- Client stores fingerprint on first connect (trust-on-first-use,
  like SSH `known_hosts`).
- Future connections auto-verify against stored fingerprint.
- No CA, no cert renewal, no Let's Encrypt dependency.

## 5. RAM-backed message delivery

**Goal:** Avoid disk I/O for ephemeral messages.

- Write per-message files to `/dev/shm` (Linux tmpfs) instead of
  disk.
- Fall back to `/tmp` on macOS (no `/dev/shm`).
- File naming: `<unix-timestamp>.<msg_id>.txt` for easy pruning.
- Prune aggressively: delete on read, or TTL-based cleanup.
- Keep `messages.log` as an optional audit trail on disk; use
  RAM-backed files for the delivery path.

## 6. Message chunking for large payloads

**Goal:** Deliver full message content without extra tool calls.

- Split messages exceeding a threshold into multiple stdout lines.
- Each chunk: `[inter-session msg=<id> from="<name>" <N>/<total>] ...`
- LLM receives all parts as separate notifications and reassembles.
- Avoids the file-read round-trip for large messages.
- Depends on CC faithfully delivering multiple rapid stdout lines
  (needs testing).
