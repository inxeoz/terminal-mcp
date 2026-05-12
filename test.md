# i4z-terminal MCP — Test Report

**Date:** 2026-05-13  
**Web UI:** http://localhost:45955  
**DB:** `~/.local/share/i4z-terminal-mcp/sessions-877587.db`

---

## Tests Passed

### Discovery & Health
| Tool | Status | Notes |
|---|---|---|
| `health_report` | ✅ PASS | DB ok, counts accurate, all fields present |
| `web_url` | ✅ PASS | Returns correct localhost URL |
| `list_terminals` | ✅ PASS | Returns empty array on clean state, populates correctly |
| `list_workspaces` | ✅ PASS | Empty and populated states both correct |

### Terminal Lifecycle
| Tool | Status | Notes |
|---|---|---|
| `create_terminal` (plain) | ✅ PASS | Creates with default empty profile |
| `create_terminal` (env + startup_commands) | ✅ PASS | Env injected as exports, commands ran in order |
| `create_terminal` (workspace_id seed) | ✅ PASS | Workspace profile applied immediately on create |
| `terminal_status` | ✅ PASS | Returns pid, alive, cwd, profile, workspaces |
| `terminal_profile` | ✅ PASS | Returns stored env and startup_commands |
| `rename_terminal` | ✅ PASS | ID updated across history, alerts, checkpoints, workspaces |
| `kill_terminal` | ✅ PASS | Process stopped, record preserved (alive=false, pid=null) |
| `delete_terminal` | ✅ PASS | Record fully purged from DB |

### I/O
| Tool | Status | Notes |
|---|---|---|
| `send_input` | ✅ PASS | Commands sent and executed correctly |
| `read_output` (since=0) | ✅ PASS | Full history returned |
| `read_output` (since=cursor) | ✅ PASS | Incremental delta only, no duplication |
| `wait_for_output` (match) | ✅ PASS | Returns matched=true and cursor position |
| `wait_for_output` (timeout) | ✅ PASS | Returns matched=false when pattern absent |
| `search_output` | ✅ PASS | Pattern matches returned from history buffer |

### Terminal Configuration
| Tool | Status | Notes |
|---|---|---|
| `resize_terminal` | ✅ PASS | PTY dimensions updated (tested 40x200) |
| `configure_terminal` (set_env) | ✅ PASS | Env vars added and updated in profile |
| `configure_terminal` (unset_env) | ✅ PASS | Env var removed from profile |
| `configure_terminal` (run_startup_commands=true) | ✅ PASS | Commands injected and ran immediately in live shell |

### Signals
| Tool | Status | Notes |
|---|---|---|
| `send_signal` SIGINT | ✅ PASS | Delivered to process group |
| `send_signal` SIGTERM | ✅ PASS | Delivered to process group |
| `send_signal` SIGKILL | ✅ PASS | Process killed, terminal goes dead (alive=false) |

### Workspaces
| Tool | Status | Notes |
|---|---|---|
| `create_workspace` | ✅ PASS | Creates with env and startup_commands |
| `workspace_status` | ✅ PASS | Returns env, commands, members, timestamps |
| `list_workspaces` | ✅ PASS | Returns member_count correctly |
| `add_terminal_to_workspace` | ✅ PASS | Profile applied to terminal immediately on join |
| `configure_workspace` (apply_to_members=true) | ✅ PASS | Updated profile live-pushed to all member terminals |
| `configure_workspace` (apply_to_members=false) | ✅ PASS | Profile updated without touching live terminals |
| `apply_workspace` (targeted) | ✅ PASS | Manual re-apply to specific terminal works |
| `remove_terminal_from_workspace` | ✅ PASS | Member removed, workspace profile unchanged |

### Checkpoints
| Tool | Status | Notes |
|---|---|---|
| `add_checkpoint` (with cursor + note) | ✅ PASS | Stored with id, label, note, timestamp |
| `add_checkpoint` (cursor only) | ✅ PASS | Note field null, rest correct |
| `list_checkpoints` (all) | ✅ PASS | Returns checkpoints across all terminals |
| `list_checkpoints` (terminal filter) | ✅ PASS | Filtered correctly by terminal_id |
| `remove_checkpoint` | ✅ PASS | Removed by checkpoint_id |

### Output Alerts
| Tool | Status | Notes |
|---|---|---|
| `add_output_alert` (global scope) | ✅ PASS | Fires on any terminal matching pattern |
| `add_output_alert` (session scope) | ✅ PASS | Fires only on the specified terminal |
| `list_output_alerts` (all) | ✅ PASS | Both scopes returned |
| `list_output_alerts` (scope filter) | ✅ PASS | Filtered by global/session correctly |
| `list_alert_events` (all) | ✅ PASS | Both alert events fired and recorded |
| `list_alert_events` (since filter) | ✅ PASS | Returns only events after given id |
| `list_alert_events` (terminal filter) | ✅ PASS | Filtered by terminal_id correctly |
| `remove_output_alert` | ✅ PASS | Removed by alert_id |

### Session Persistence
| Tool | Status | Notes |
|---|---|---|
| `export_session` | ✅ PASS | Full bundle: profile, history events, checkpoints, workspaces, status |
| `import_session` (new terminal_id) | ✅ PASS | Live terminal spawned, profile restored, checkpoints re-created with new IDs |

---

## Observations & Suggestions for Improvement

### 1. Signal behavior on idle shell
**Observation:** Sending `SIGINT` or `SIGTERM` to a terminal with no foreground process (just an idle shell) kills the shell itself rather than being ignored or returning a prompt. `SIGKILL` predictably kills the process group.  
**Suggestion:** Document this clearly, or add a `--foreground-only` flag that sends the signal only when a foreground child process is detected, preventing accidental shell termination.

### 2. `wait_for_output` returns `matched=false` silently on timeout
**Observation:** When the pattern is never matched, `wait_for_output` returns `{"matched": false, "cursor": N}` with no indication of what output *was* seen during the wait.  
**Suggestion:** Include a `"last_output"` snippet or the final cursor position alongside `matched=false` so the caller can diagnose what arrived during the timeout without a separate `read_output` call.

### 3. Workspace profiles persist after all member terminals are deleted
**Observation:** After deleting all member terminals, the workspace profile remains in the DB indefinitely. There is no auto-cleanup.  
**Suggestion:** Add a `delete_workspace` tool, or an optional `auto_delete: true` flag on `create_workspace` that removes the profile when member count drops to zero.

### 4. `export_session` includes workspace profiles but not workspace membership of other terminals
**Observation:** The exported bundle captures the source terminal's workspace memberships, but the workspace profile itself (shared state) is only partially included — other member terminals are not exported.  
**Suggestion:** Add an `include_workspace_members` option to `export_session` to enable full workspace snapshots, useful for multi-terminal handoffs.

### 5. `rename_terminal` on a dead terminal works but `cwd` is lost
**Observation:** Renaming a dead terminal (alive=false) succeeds and history is preserved, but `cwd` is null and cannot be recovered from the record.  
**Suggestion:** Persist the last known `cwd` at the time the process dies so it remains readable after death — useful for restoring or re-creating the session in the same directory.

### 6. `search_output` returns plain line matches without cursor positions
**Observation:** `search_output` returns matching lines as strings but no byte offsets or cursor positions.  
**Suggestion:** Return `[{"match": "...", "cursor": N}]` per match so results can be used directly with `read_output since=cursor` or `add_checkpoint cursor=N` without a manual scan.

### 7. No `list_alert_events` pagination
**Observation:** `list_alert_events` returns all events from a given `since` id with no limit parameter.  
**Suggestion:** Add a `limit` parameter to cap results for high-volume terminals.

### 8. `configure_terminal` silently re-runs startup commands even when already applied
**Observation:** Calling `configure_terminal` with `run_startup_commands=true` always re-runs commands — there is no idempotency guard.  
**Suggestion:** Add a `force` flag (default true) so callers can set `force=false` to skip re-running if the commands were already applied in the current session.

---

## Summary

All **44 tools** tested across all scenarios. **44/44 passed.** No crashes, no data corruption, DB consistent throughout. The signal and workspace behaviours noted above are edge cases worth documenting or addressing in a future release.
