use anyhow::Result;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use sqlx::{sqlite::SqliteConnectOptions, FromRow, Row, SqlitePool};
use std::str::FromStr;

lazy_static::lazy_static! {
    static ref ANSI_RE: regex::Regex = regex::Regex::new(r"\x1b\[[0-9;?]*[a-zA-Z]|\x1b\][^\x07]*\x07").unwrap();
}

fn strip_ansi(text: &str) -> String {
    ANSI_RE.replace_all(text, "").replace('\r', "")
}

pub struct History {
    pool: SqlitePool,
}

#[derive(Debug, Serialize, Deserialize, FromRow)]
pub struct Event {
    pub id: i64,
    pub terminal_id: String,
    #[sqlx(rename = "type")]
    pub event_type: String,
    pub text: String,
    pub timestamp: String,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct Alert {
    pub id: String,
    pub scope: String,
    pub terminal_id: Option<String>,
    pub pattern: String,
    pub label: Option<String>,
    pub created_at: String,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct AlertEvent {
    pub id: i64,
    pub alert_id: String,
    pub terminal_id: String,
    pub pattern: String,
    pub matched_text: String,
    pub timestamp: String,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct Checkpoint {
    pub id: String,
    pub terminal_id: String,
    pub cursor: i64,
    pub label: String,
    pub note: Option<String>,
    pub created_at: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Profile {
    pub terminal_id: String,
    pub env: serde_json::Map<String, Value>,
    pub startup_commands: Vec<String>,
}

impl Profile {
    pub fn default_for(id: &str) -> Self {
        Self {
            terminal_id: id.to_string(),
            env: Default::default(),
            startup_commands: vec![],
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Workspace {
    pub id: String,
    pub env: serde_json::Map<String, Value>,
    pub startup_commands: Vec<String>,
    pub members: Vec<String>,
    pub created_at: String,
    pub updated_at: String,
    pub member_count: usize,
}

// Internal row types for sqlx
#[derive(FromRow)]
struct ProfileRow {
    terminal_id: String,
    env_json: String,
    startup_json: String,
}

#[derive(FromRow)]
struct AlertRow {
    id: String,
    scope: String,
    terminal_id: Option<String>,
    pattern: String,
    label: Option<String>,
    created_at: String,
}

#[derive(FromRow)]
struct AlertEventRow {
    id: i64,
    alert_id: String,
    terminal_id: String,
    pattern: String,
    matched_text: String,
    timestamp: String,
}

#[derive(FromRow)]
struct CheckpointRow {
    id: String,
    terminal_id: String,
    cursor: i64,
    label: String,
    note: Option<String>,
    created_at: String,
}

#[derive(FromRow)]
struct WorkspaceRow {
    id: String,
    env_json: String,
    startup_json: String,
    created_at: String,
    updated_at: String,
    members_csv: Option<String>,
}

impl History {
    pub async fn open(state_dir: &str) -> Result<Self> {
        std::fs::create_dir_all(state_dir)?;
        let db_path = format!("sqlite://{state_dir}/history.db");
        let opts = SqliteConnectOptions::from_str(&db_path)?
            .create_if_missing(true)
            .journal_mode(sqlx::sqlite::SqliteJournalMode::Wal);
        let pool = sqlx::sqlite::SqlitePoolOptions::new()
            .max_connections(5)
            .connect_with(opts)
            .await?;
        Self::migrate(&pool).await?;
        Ok(Self { pool })
    }

    async fn column_exists(pool: &SqlitePool, table: &str, col: &str) -> bool {
        sqlx::query(&format!("PRAGMA table_info({table})"))
            .fetch_all(pool)
            .await
            .ok()
            .is_some_and(|rows| {
                rows.iter().any(|r| {
                    r.try_get::<String, _>("name")
                        .is_ok_and(|n| n == col)
                })
            })
    }

    async fn rename_col_if_needed(pool: &SqlitePool, table: &str, from: &str, to: &str) -> Result<()> {
        if Self::column_exists(pool, table, from).await
            && !Self::column_exists(pool, table, to).await
        {
            sqlx::query(&format!("ALTER TABLE {table} RENAME COLUMN {from} TO {to}"))
                .execute(pool)
                .await?;
        }
        Ok(())
    }

    async fn add_col_if_missing(pool: &SqlitePool, table: &str, col: &str, definition: &str) -> Result<()> {
        if !Self::column_exists(pool, table, col).await {
            sqlx::query(&format!("ALTER TABLE {table} ADD COLUMN {col} {definition}"))
                .execute(pool)
                .await?;
        }
        Ok(())
    }

    /// Recreate `events` when old `kind` column coexists with new `type` column.
    /// SQLite cannot ALTER COLUMN constraints, so we copy-drop-rename.
    async fn repair_events_table(pool: &SqlitePool) -> Result<()> {
        if !Self::column_exists(pool, "events", "kind").await {
            return Ok(());
        }
        let mut tx = pool.begin().await?;
        sqlx::query("DROP TABLE IF EXISTS events_new").execute(&mut *tx).await?;
        sqlx::query(
            "CREATE TABLE events_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                terminal_id TEXT NOT NULL,
                type TEXT NOT NULL CHECK(type IN ('input','output')),
                text TEXT NOT NULL,
                timestamp TEXT NOT NULL
            )",
        ).execute(&mut *tx).await?;
        // `kind` exists alongside `type`; `timestamp` may be INTEGER (old ts column renamed)
        sqlx::query(
            "INSERT INTO events_new (id, terminal_id, type, text, timestamp)
            SELECT id, terminal_id,
                   COALESCE(type, kind, 'output'),
                   COALESCE(text, ''),
                   CASE WHEN typeof(timestamp) = 'integer'
                        THEN datetime(timestamp, 'unixepoch')
                        ELSE CAST(timestamp AS TEXT)
                   END
            FROM events",
        ).execute(&mut *tx).await?;
        sqlx::query("DROP TABLE events").execute(&mut *tx).await?;
        sqlx::query("ALTER TABLE events_new RENAME TO events").execute(&mut *tx).await?;
        tx.commit().await?;
        sqlx::query("CREATE INDEX IF NOT EXISTS idx_events_terminal ON events(terminal_id, id)")
            .execute(pool).await?;
        Ok(())
    }

    /// Recreate `alert_events` when the table still has the old schema
    /// (`matched`, `ts`) instead of the new one (`pattern`, `matched_text`, `timestamp`).
    async fn repair_alert_events_table(pool: &SqlitePool) -> Result<()> {
        if !Self::column_exists(pool, "alert_events", "ts").await {
            return Ok(());
        }
        let mut tx = pool.begin().await?;
        sqlx::query("DROP TABLE IF EXISTS alert_events_new").execute(&mut *tx).await?;
        sqlx::query(
            "CREATE TABLE alert_events_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alert_id TEXT NOT NULL,
                terminal_id TEXT NOT NULL,
                pattern TEXT NOT NULL,
                matched_text TEXT NOT NULL,
                timestamp TEXT NOT NULL
            )",
        ).execute(&mut *tx).await?;
        // Old schema: alert_id INTEGER, terminal_id, matched TEXT, ts INTEGER
        sqlx::query(
            "INSERT INTO alert_events_new (id, alert_id, terminal_id, pattern, matched_text, timestamp)
            SELECT id,
                   CAST(alert_id AS TEXT),
                   terminal_id,
                   '',
                   COALESCE(matched, ''),
                   datetime(ts, 'unixepoch')
            FROM alert_events",
        ).execute(&mut *tx).await?;
        sqlx::query("DROP TABLE alert_events").execute(&mut *tx).await?;
        sqlx::query("ALTER TABLE alert_events_new RENAME TO alert_events").execute(&mut *tx).await?;
        tx.commit().await?;
        sqlx::query("CREATE INDEX IF NOT EXISTS idx_alert_events_terminal ON alert_events(terminal_id, id)")
            .execute(pool).await?;
        Ok(())
    }

    async fn migrate(pool: &SqlitePool) -> Result<()> {
        sqlx::query(
            "CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                terminal_id TEXT NOT NULL,
                type TEXT NOT NULL CHECK(type IN ('input','output')),
                text TEXT NOT NULL,
                timestamp TEXT NOT NULL
            )",
        )
        .execute(pool)
        .await?;
        sqlx::query(
            "CREATE INDEX IF NOT EXISTS idx_events_terminal ON events(terminal_id, id)",
        )
        .execute(pool)
        .await?;
        sqlx::query(
            "CREATE TABLE IF NOT EXISTS session_profiles (
                terminal_id TEXT PRIMARY KEY,
                env_json TEXT NOT NULL,
                startup_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )",
        )
        .execute(pool)
        .await?;
        // Migrations: rename old schema columns (kind→type, data→text, ts→timestamp)
        Self::rename_col_if_needed(pool, "events", "kind", "type").await?;
        Self::rename_col_if_needed(pool, "events", "data", "text").await?;
        Self::rename_col_if_needed(pool, "events", "ts", "timestamp").await?;
        // Migrations: add columns that may be missing on older DBs
        Self::add_col_if_missing(pool, "events", "type", "TEXT NOT NULL DEFAULT 'output'").await?;
        Self::add_col_if_missing(pool, "events", "text", "TEXT NOT NULL DEFAULT ''").await?;
        Self::add_col_if_missing(pool, "events", "timestamp", "TEXT NOT NULL DEFAULT '1970-01-01T00:00:00Z'").await?;
        Self::add_col_if_missing(pool, "session_profiles", "startup_json", "TEXT NOT NULL DEFAULT '[]'").await?;
        Self::add_col_if_missing(pool, "session_profiles", "updated_at", "TEXT NOT NULL DEFAULT '1970-01-01T00:00:00Z'").await?;
        sqlx::query(
            "CREATE TABLE IF NOT EXISTS alerts (
                id TEXT PRIMARY KEY,
                scope TEXT NOT NULL CHECK(scope IN ('global','session')),
                terminal_id TEXT,
                pattern TEXT NOT NULL,
                label TEXT,
                created_at TEXT NOT NULL
            )",
        )
        .execute(pool)
        .await?;
        sqlx::query(
            "CREATE INDEX IF NOT EXISTS idx_alerts_scope ON alerts(scope, terminal_id)",
        )
        .execute(pool)
        .await?;
        sqlx::query(
            "CREATE TABLE IF NOT EXISTS alert_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alert_id TEXT NOT NULL,
                terminal_id TEXT NOT NULL,
                pattern TEXT NOT NULL,
                matched_text TEXT NOT NULL,
                timestamp TEXT NOT NULL
            )",
        )
        .execute(pool)
        .await?;
        sqlx::query(
            "CREATE INDEX IF NOT EXISTS idx_alert_events_terminal ON alert_events(terminal_id, id)",
        )
        .execute(pool)
        .await?;
        sqlx::query(
            "CREATE TABLE IF NOT EXISTS reader_errors (
                terminal_id TEXT PRIMARY KEY,
                message TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )",
        )
        .execute(pool)
        .await?;
        Self::add_col_if_missing(pool, "reader_errors", "updated_at", "TEXT NOT NULL DEFAULT '1970-01-01T00:00:00Z'").await?;
        sqlx::query(
            "CREATE TABLE IF NOT EXISTS bookmarks (
                id TEXT PRIMARY KEY,
                terminal_id TEXT NOT NULL,
                cursor INTEGER NOT NULL,
                label TEXT NOT NULL,
                note TEXT,
                created_at TEXT NOT NULL
            )",
        )
        .execute(pool)
        .await?;
        sqlx::query(
            "CREATE INDEX IF NOT EXISTS idx_bookmarks_terminal ON bookmarks(terminal_id, created_at)",
        )
        .execute(pool)
        .await?;
        sqlx::query(
            "CREATE TABLE IF NOT EXISTS workspaces (
                id TEXT PRIMARY KEY,
                env_json TEXT NOT NULL,
                startup_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )",
        )
        .execute(pool)
        .await?;
        // Migrations: add columns added after initial DB creation
        Self::add_col_if_missing(pool, "workspaces", "startup_json", "TEXT NOT NULL DEFAULT '[]'").await?;
        Self::add_col_if_missing(pool, "workspaces", "updated_at", "TEXT NOT NULL DEFAULT '1970-01-01T00:00:00Z'").await?;
        Self::add_col_if_missing(pool, "workspaces", "created_at", "TEXT NOT NULL DEFAULT '1970-01-01T00:00:00Z'").await?;
        sqlx::query(
            "CREATE TABLE IF NOT EXISTS workspace_members (
                workspace_id TEXT NOT NULL,
                terminal_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (workspace_id, terminal_id)
            )",
        )
        .execute(pool)
        .await?;
        sqlx::query(
            "CREATE INDEX IF NOT EXISTS idx_workspace_members_terminal ON workspace_members(terminal_id)",
        )
        .execute(pool)
        .await?;
        // Repair tables that ended up with mixed old+new columns due to partial prior migrations
        Self::repair_events_table(pool).await?;
        Self::repair_alert_events_table(pool).await?;
        sqlx::query(
            "CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )",
        )
        .execute(pool)
        .await?;
        Ok(())
    }

    fn now() -> String {
        chrono::Utc::now().to_rfc3339()
    }

    // ── events ────────────────────────────────────────────────────────────────

    pub async fn record_output(&self, terminal_id: &str, data: &str) -> Result<()> {
        let clean = strip_ansi(data);
        if clean.is_empty() {
            return Ok(());
        }
        sqlx::query(
            "INSERT INTO events (terminal_id, type, text, timestamp) VALUES (?, 'output', ?, ?)",
        )
        .bind(terminal_id)
        .bind(&clean)
        .bind(Self::now())
        .execute(&self.pool)
        .await?;
        Ok(())
    }

    pub async fn record_input(&self, terminal_id: &str, data: &str) -> Result<()> {
        if data.is_empty() {
            return Ok(());
        }
        sqlx::query(
            "INSERT INTO events (terminal_id, type, text, timestamp) VALUES (?, 'input', ?, ?)",
        )
        .bind(terminal_id)
        .bind(data)
        .bind(Self::now())
        .execute(&self.pool)
        .await?;
        Ok(())
    }

    pub async fn get_history(&self, terminal_id: &str, since: i64) -> Result<serde_json::Value> {
        let rows = sqlx::query_as::<_, Event>(
            "SELECT id, terminal_id, type, text, timestamp FROM events WHERE terminal_id = ? AND id > ? ORDER BY id",
        )
        .bind(terminal_id)
        .bind(since)
        .fetch_all(&self.pool)
        .await?;
        if rows.is_empty() {
            // Check if terminal has ANY events
            let exists: Option<(i64,)> = sqlx::query_as(
                "SELECT 1 FROM events WHERE terminal_id = ? LIMIT 1",
            )
            .bind(terminal_id)
            .fetch_optional(&self.pool)
            .await?;
            if exists.is_none() {
                return Err(anyhow::anyhow!("Terminal '{terminal_id}' not found"));
            }
        }
        let events: Vec<serde_json::Value> = rows
            .iter()
            .map(|r| {
                serde_json::json!({
                    "id": r.id,
                    "type": r.event_type,
                    "text": r.text,
                    "timestamp": r.timestamp,
                })
            })
            .collect();
        let cursor = events.last().map(|e| e["id"].as_i64().unwrap_or(since)).unwrap_or(since);
        Ok(serde_json::json!({ "events": events, "cursor": cursor }))
    }

    pub async fn search(&self, terminal_id: &str, query: &str) -> Result<serde_json::Value> {
        let exists: Option<(i64,)> = sqlx::query_as(
            "SELECT 1 FROM events WHERE terminal_id = ? LIMIT 1",
        )
        .bind(terminal_id)
        .fetch_optional(&self.pool)
        .await?;
        if exists.is_none() {
            return Err(anyhow::anyhow!("Terminal '{terminal_id}' not found"));
        }
        let like = format!("%{}%", query.to_lowercase());
        let rows = sqlx::query_as::<_, Event>(
            "SELECT id, terminal_id, type, text, timestamp FROM events WHERE terminal_id = ? AND LOWER(text) LIKE ? ORDER BY id",
        )
        .bind(terminal_id)
        .bind(&like)
        .fetch_all(&self.pool)
        .await?;
        let matches: Vec<String> = rows
            .iter()
            .filter_map(|r| {
                let trimmed = r.text.trim();
                if trimmed.is_empty() { None } else { Some(trimmed.to_string()) }
            })
            .collect();
        Ok(serde_json::json!({ "matches": matches }))
    }

    pub async fn delete_terminal(&self, id: &str) -> Result<()> {
        let mut tx = self.pool.begin().await?;
        sqlx::query("DELETE FROM events WHERE terminal_id = ?").bind(id).execute(&mut *tx).await?;
        sqlx::query("DELETE FROM session_profiles WHERE terminal_id = ?").bind(id).execute(&mut *tx).await?;
        sqlx::query("DELETE FROM alerts WHERE terminal_id = ? AND scope = 'session'").bind(id).execute(&mut *tx).await?;
        sqlx::query("DELETE FROM alert_events WHERE terminal_id = ?").bind(id).execute(&mut *tx).await?;
        sqlx::query("DELETE FROM reader_errors WHERE terminal_id = ?").bind(id).execute(&mut *tx).await?;
        sqlx::query("DELETE FROM bookmarks WHERE terminal_id = ?").bind(id).execute(&mut *tx).await?;
        sqlx::query("DELETE FROM workspace_members WHERE terminal_id = ?").bind(id).execute(&mut *tx).await?;
        tx.commit().await?;
        Ok(())
    }

    pub async fn rename_terminal(&self, old_id: &str, new_id: &str) -> Result<()> {
        let mut tx = self.pool.begin().await?;
        for table in &[
            "events",
            "session_profiles",
            "alerts",
            "alert_events",
            "bookmarks",
            "workspace_members",
            "reader_errors",
        ] {
            let q = format!("UPDATE {table} SET terminal_id = ? WHERE terminal_id = ?");
            sqlx::query(&q)
                .bind(new_id)
                .bind(old_id)
                .execute(&mut *tx)
                .await?;
        }
        tx.commit().await?;
        Ok(())
    }

    pub async fn list_terminal_ids(&self) -> Result<Vec<String>> {
        // Order by first recorded event timestamp so sidebar preserves creation order.
        // Terminals without any events yet fall back to alphabetical after the rest.
        let rows: Vec<(String,)> = sqlx::query_as(
            "SELECT tid FROM (
                -- sessions that have at least one event: ordered by first event
                SELECT terminal_id AS tid, MIN(timestamp) AS first_seen
                FROM events
                GROUP BY terminal_id
                UNION
                -- sessions known only via profiles or alerts, no events recorded yet
                SELECT terminal_id AS tid, '9999-99-99T00:00:00Z' AS first_seen
                FROM (
                    SELECT terminal_id FROM session_profiles
                    UNION
                    SELECT terminal_id FROM alerts WHERE terminal_id IS NOT NULL
                    UNION
                    SELECT terminal_id FROM reader_errors
                )
                WHERE terminal_id NOT IN (SELECT DISTINCT terminal_id FROM events)
            ) ORDER BY first_seen ASC, tid ASC",
        )
        .fetch_all(&self.pool)
        .await?;
        Ok(rows.into_iter().map(|r| r.0).collect())
    }

    pub async fn status(&self, terminal_id: &str) -> Result<serde_json::Value> {
        let first: Option<Event> = sqlx::query_as::<_, Event>(
            "SELECT id, terminal_id, type, text, timestamp FROM events WHERE terminal_id = ? ORDER BY id ASC LIMIT 1",
        )
        .bind(terminal_id)
        .fetch_optional(&self.pool)
        .await?;
        if first.is_none() {
            return Err(anyhow::anyhow!("Terminal '{terminal_id}' not found"));
        }
        let last: Option<Event> = sqlx::query_as::<_, Event>(
            "SELECT id, terminal_id, type, text, timestamp FROM events WHERE terminal_id = ? ORDER BY id DESC LIMIT 1",
        )
        .bind(terminal_id)
        .fetch_optional(&self.pool)
        .await?;
        let first = first.unwrap();
        let last_activity = last.as_ref().map(|r| r.timestamp.clone()).unwrap_or_else(|| first.timestamp.clone());
        Ok(serde_json::json!({
            "id": terminal_id,
            "alive": false,
            "pid": serde_json::Value::Null,
            "cwd": serde_json::Value::Null,
            "created_at": first.timestamp,
            "last_activity": last_activity,
            "reader_error": serde_json::Value::Null,
        }))
    }

    // ── profiles ──────────────────────────────────────────────────────────────

    pub async fn get_profile(&self, terminal_id: &str) -> Result<Profile> {
        let row = sqlx::query_as::<_, ProfileRow>(
            "SELECT terminal_id, env_json, startup_json FROM session_profiles WHERE terminal_id = ?",
        )
        .bind(terminal_id)
        .fetch_optional(&self.pool)
        .await?;
        if let Some(r) = row {
            let env = serde_json::from_str(&r.env_json).unwrap_or_default();
            let startup_commands = serde_json::from_str(&r.startup_json).unwrap_or_default();
            Ok(Profile { terminal_id: r.terminal_id, env, startup_commands })
        } else {
            Ok(Profile::default_for(terminal_id))
        }
    }

    pub async fn upsert_profile(&self, profile: &Profile) -> Result<()> {
        let env_json = serde_json::to_string(&profile.env)?;
        let cmds_json = serde_json::to_string(&profile.startup_commands)?;
        let now = Self::now();
        sqlx::query(
            "INSERT INTO session_profiles (terminal_id, env_json, startup_json, updated_at)
             VALUES (?, ?, ?, ?)
             ON CONFLICT(terminal_id) DO UPDATE
             SET env_json = excluded.env_json, startup_json = excluded.startup_json, updated_at = excluded.updated_at",
        )
        .bind(&profile.terminal_id)
        .bind(&env_json)
        .bind(&cmds_json)
        .bind(&now)
        .execute(&self.pool)
        .await?;
        Ok(())
    }

    // ── alerts ────────────────────────────────────────────────────────────────

    pub async fn add_alert(
        &self,
        scope: &str,
        pattern: &str,
        terminal_id: Option<&str>,
        label: Option<&str>,
    ) -> Result<String> {
        let id = uuid::Uuid::new_v4().to_string().replace('-', "");
        sqlx::query(
            "INSERT INTO alerts (id, scope, terminal_id, pattern, label, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        )
        .bind(&id)
        .bind(scope)
        .bind(terminal_id)
        .bind(pattern)
        .bind(label)
        .bind(Self::now())
        .execute(&self.pool)
        .await?;
        Ok(id)
    }

    pub async fn list_alerts(
        &self,
        scope: Option<&str>,
        terminal_id: Option<&str>,
    ) -> Result<Vec<Alert>> {
        let mut query = "SELECT id, scope, terminal_id, pattern, label, created_at FROM alerts".to_string();
        let mut conditions: Vec<&str> = vec![];
        if scope.is_some() {
            conditions.push("scope = ?");
        }
        if terminal_id.is_some() {
            conditions.push("(terminal_id = ? OR terminal_id IS NULL)");
        }
        if !conditions.is_empty() {
            query.push_str(" WHERE ");
            query.push_str(&conditions.join(" AND "));
        }
        query.push_str(" ORDER BY created_at, id");

        let mut q = sqlx::query_as::<_, AlertRow>(&query);
        if let Some(s) = scope {
            q = q.bind(s);
        }
        if let Some(t) = terminal_id {
            q = q.bind(t);
        }
        let rows = q.fetch_all(&self.pool).await?;
        Ok(rows.into_iter().map(|r| Alert {
            id: r.id,
            scope: r.scope,
            terminal_id: r.terminal_id,
            pattern: r.pattern,
            label: r.label,
            created_at: r.created_at,
        }).collect())
    }

    pub async fn remove_alert(&self, id: &str) -> Result<bool> {
        let res = sqlx::query("DELETE FROM alerts WHERE id = ?")
            .bind(id)
            .execute(&self.pool)
            .await?;
        Ok(res.rows_affected() > 0)
    }

    pub async fn record_alert_event(
        &self,
        alert_id: &str,
        terminal_id: &str,
        pattern: &str,
        matched_text: &str,
    ) -> Result<()> {
        sqlx::query(
            "INSERT INTO alert_events (alert_id, terminal_id, pattern, matched_text, timestamp) VALUES (?, ?, ?, ?, ?)",
        )
        .bind(alert_id)
        .bind(terminal_id)
        .bind(pattern)
        .bind(matched_text)
        .bind(Self::now())
        .execute(&self.pool)
        .await?;
        Ok(())
    }

    pub async fn list_alert_events(
        &self,
        terminal_id: Option<&str>,
        since: i64,
    ) -> Result<Vec<AlertEvent>> {
        let mut query = "SELECT id, alert_id, terminal_id, pattern, matched_text, timestamp FROM alert_events WHERE id > ?".to_string();
        if terminal_id.is_some() {
            query.push_str(" AND terminal_id = ?");
        }
        query.push_str(" ORDER BY id");

        let mut q = sqlx::query_as::<_, AlertEventRow>(&query).bind(since);
        if let Some(t) = terminal_id {
            q = q.bind(t);
        }
        let rows = q.fetch_all(&self.pool).await?;
        Ok(rows.into_iter().map(|r| AlertEvent {
            id: r.id,
            alert_id: r.alert_id,
            terminal_id: r.terminal_id,
            pattern: r.pattern,
            matched_text: r.matched_text,
            timestamp: r.timestamp,
        }).collect())
    }

    // ── reader errors ─────────────────────────────────────────────────────────

    pub async fn record_reader_error(&self, terminal_id: &str, message: &str) -> Result<()> {
        let now = Self::now();
        sqlx::query(
            "INSERT INTO reader_errors (terminal_id, message, updated_at) VALUES (?, ?, ?)
             ON CONFLICT(terminal_id) DO UPDATE SET message = excluded.message, updated_at = excluded.updated_at",
        )
        .bind(terminal_id)
        .bind(message)
        .bind(&now)
        .execute(&self.pool)
        .await?;
        Ok(())
    }

    pub async fn clear_reader_error(&self, terminal_id: &str) -> Result<()> {
        sqlx::query("DELETE FROM reader_errors WHERE terminal_id = ?")
            .bind(terminal_id)
            .execute(&self.pool)
            .await?;
        Ok(())
    }

    pub async fn get_reader_error(&self, terminal_id: &str) -> Result<Option<String>> {
        let row: Option<(String,)> = sqlx::query_as(
            "SELECT message FROM reader_errors WHERE terminal_id = ?",
        )
        .bind(terminal_id)
        .fetch_optional(&self.pool)
        .await?;
        Ok(row.map(|r| r.0))
    }

    // ── workspaces ────────────────────────────────────────────────────────────

    pub async fn create_workspace(
        &self,
        id: &str,
        env: &serde_json::Map<String, Value>,
        startup_commands: &[String],
    ) -> Result<()> {
        // Check exists first
        let exists: Option<(i64,)> = sqlx::query_as(
            "SELECT 1 FROM workspaces WHERE id = ?",
        )
        .bind(id)
        .fetch_optional(&self.pool)
        .await?;
        if exists.is_some() {
            return Err(anyhow::anyhow!("Workspace '{id}' already exists"));
        }
        let env_json = serde_json::to_string(env)?;
        let cmds_json = serde_json::to_string(startup_commands)?;
        let now = Self::now();
        sqlx::query(
            "INSERT INTO workspaces (id, env_json, startup_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        )
        .bind(id)
        .bind(&env_json)
        .bind(&cmds_json)
        .bind(&now)
        .bind(&now)
        .execute(&self.pool)
        .await?;
        Ok(())
    }

    pub async fn list_workspaces(&self) -> Result<Vec<Workspace>> {
        let rows = sqlx::query_as::<_, WorkspaceRow>(
            "SELECT w.id, w.env_json, w.startup_json, w.created_at, w.updated_at,
                    GROUP_CONCAT(wm.terminal_id) AS members_csv
             FROM workspaces w
             LEFT JOIN workspace_members wm ON wm.workspace_id = w.id
             GROUP BY w.id ORDER BY w.id",
        )
        .fetch_all(&self.pool)
        .await?;
        Ok(rows.into_iter().map(workspace_row_to_ws).collect())
    }

    pub async fn get_workspace(&self, id: &str) -> Result<Option<Workspace>> {
        let row = sqlx::query_as::<_, WorkspaceRow>(
            "SELECT w.id, w.env_json, w.startup_json, w.created_at, w.updated_at,
                    GROUP_CONCAT(wm.terminal_id) AS members_csv
             FROM workspaces w
             LEFT JOIN workspace_members wm ON wm.workspace_id = w.id
             WHERE w.id = ?
             GROUP BY w.id",
        )
        .bind(id)
        .fetch_optional(&self.pool)
        .await?;
        Ok(row.map(workspace_row_to_ws))
    }

    pub async fn update_workspace(
        &self,
        id: &str,
        env: &serde_json::Map<String, Value>,
        startup_commands: &[String],
    ) -> Result<()> {
        let env_json = serde_json::to_string(env)?;
        let cmds_json = serde_json::to_string(startup_commands)?;
        let now = Self::now();
        let res = sqlx::query(
            "UPDATE workspaces SET env_json = ?, startup_json = ?, updated_at = ? WHERE id = ?",
        )
        .bind(&env_json)
        .bind(&cmds_json)
        .bind(&now)
        .bind(id)
        .execute(&self.pool)
        .await?;
        if res.rows_affected() == 0 {
            return Err(anyhow::anyhow!("Workspace '{id}' not found"));
        }
        Ok(())
    }

    pub async fn add_workspace_member(&self, workspace_id: &str, terminal_id: &str) -> Result<()> {
        // Verify workspace exists
        let exists: Option<(i64,)> = sqlx::query_as(
            "SELECT 1 FROM workspaces WHERE id = ?",
        )
        .bind(workspace_id)
        .fetch_optional(&self.pool)
        .await?;
        if exists.is_none() {
            return Err(anyhow::anyhow!("Workspace '{workspace_id}' not found"));
        }
        let now = Self::now();
        sqlx::query(
            "INSERT OR IGNORE INTO workspace_members (workspace_id, terminal_id, created_at) VALUES (?, ?, ?)",
        )
        .bind(workspace_id)
        .bind(terminal_id)
        .bind(&now)
        .execute(&self.pool)
        .await?;
        Ok(())
    }

    pub async fn remove_workspace_member(
        &self,
        workspace_id: &str,
        terminal_id: &str,
    ) -> Result<()> {
        sqlx::query(
            "DELETE FROM workspace_members WHERE workspace_id = ? AND terminal_id = ?",
        )
        .bind(workspace_id)
        .bind(terminal_id)
        .execute(&self.pool)
        .await?;
        Ok(())
    }

    pub async fn list_workspace_ids_for_terminal(&self, terminal_id: &str) -> Result<Vec<String>> {
        let rows: Vec<(String,)> = sqlx::query_as(
            "SELECT workspace_id FROM workspace_members WHERE terminal_id = ? ORDER BY workspace_id",
        )
        .bind(terminal_id)
        .fetch_all(&self.pool)
        .await?;
        Ok(rows.into_iter().map(|r| r.0).collect())
    }

    pub async fn remove_workspace(&self, workspace_id: &str) -> Result<bool> {
        sqlx::query("DELETE FROM workspace_members WHERE workspace_id = ?")
            .bind(workspace_id)
            .execute(&self.pool)
            .await?;
        let res = sqlx::query("DELETE FROM workspaces WHERE id = ?")
            .bind(workspace_id)
            .execute(&self.pool)
            .await?;
        Ok(res.rows_affected() > 0)
    }

    // ── bookmarks / checkpoints ───────────────────────────────────────────────

    pub async fn add_checkpoint(
        &self,
        terminal_id: &str,
        label: &str,
        note: Option<&str>,
        cursor: Option<i64>,
    ) -> Result<String> {
        let id = uuid::Uuid::new_v4().to_string().replace('-', "");
        sqlx::query(
            "INSERT INTO bookmarks (id, terminal_id, cursor, label, note, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        )
        .bind(&id)
        .bind(terminal_id)
        .bind(cursor.unwrap_or(0))
        .bind(label)
        .bind(note)
        .bind(Self::now())
        .execute(&self.pool)
        .await?;
        Ok(id)
    }

    pub async fn list_checkpoints(&self, terminal_id: Option<&str>) -> Result<Vec<Checkpoint>> {
        let mut query = "SELECT id, terminal_id, cursor, label, note, created_at FROM bookmarks".to_string();
        if terminal_id.is_some() {
            query.push_str(" WHERE terminal_id = ?");
        }
        query.push_str(" ORDER BY created_at, id");
        let mut q = sqlx::query_as::<_, CheckpointRow>(&query);
        if let Some(t) = terminal_id {
            q = q.bind(t);
        }
        let rows = q.fetch_all(&self.pool).await?;
        Ok(rows.into_iter().map(|r| Checkpoint {
            id: r.id,
            terminal_id: r.terminal_id,
            cursor: r.cursor,
            label: r.label,
            note: r.note,
            created_at: r.created_at,
        }).collect())
    }

    pub async fn remove_checkpoint(&self, id: &str) -> Result<bool> {
        let res = sqlx::query("DELETE FROM bookmarks WHERE id = ?")
            .bind(id)
            .execute(&self.pool)
            .await?;
        Ok(res.rows_affected() > 0)
    }

    // ── health ────────────────────────────────────────────────────────────────

    pub async fn counts(&self) -> Result<serde_json::Value> {
        let events: i64 = sqlx::query_scalar("SELECT COUNT(*) FROM events")
            .fetch_one(&self.pool).await?;
        let profiles: i64 = sqlx::query_scalar("SELECT COUNT(*) FROM session_profiles")
            .fetch_one(&self.pool).await?;
        let alerts: i64 = sqlx::query_scalar("SELECT COUNT(*) FROM alerts")
            .fetch_one(&self.pool).await?;
        let alert_events: i64 = sqlx::query_scalar("SELECT COUNT(*) FROM alert_events")
            .fetch_one(&self.pool).await?;
        let reader_errors: i64 = sqlx::query_scalar("SELECT COUNT(*) FROM reader_errors")
            .fetch_one(&self.pool).await?;
        let bookmarks: i64 = sqlx::query_scalar("SELECT COUNT(*) FROM bookmarks")
            .fetch_one(&self.pool).await?;
        let workspaces: i64 = sqlx::query_scalar("SELECT COUNT(*) FROM workspaces")
            .fetch_one(&self.pool).await?;
        let workspace_members: i64 = sqlx::query_scalar("SELECT COUNT(*) FROM workspace_members")
            .fetch_one(&self.pool).await?;
        Ok(serde_json::json!({
            "events": events,
            "profiles": profiles,
            "alerts": alerts,
            "alert_events": alert_events,
            "reader_errors": reader_errors,
            "bookmarks": bookmarks,
            "workspaces": workspaces,
            "workspace_members": workspace_members,
        }))
    }

    // ── server config ─────────────────────────────────────────────────────────

    pub async fn get_config(&self, key: &str) -> Result<Option<String>> {
        let row: Option<(String,)> = sqlx::query_as("SELECT value FROM config WHERE key = ?")
            .bind(key)
            .fetch_optional(&self.pool)
            .await?;
        Ok(row.map(|(v,)| v))
    }

    pub async fn set_config(&self, key: &str, value: &str) -> Result<()> {
        sqlx::query("INSERT INTO config(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value")
            .bind(key)
            .bind(value)
            .execute(&self.pool)
            .await?;
        Ok(())
    }

    pub async fn all_config(&self) -> Result<std::collections::HashMap<String, String>> {
        let rows: Vec<(String, String)> = sqlx::query_as("SELECT key, value FROM config ORDER BY key")
            .fetch_all(&self.pool)
            .await?;
        Ok(rows.into_iter().collect())
    }
}

fn workspace_row_to_ws(r: WorkspaceRow) -> Workspace {
    let env = serde_json::from_str(&r.env_json).unwrap_or_default();
    let startup_commands = serde_json::from_str(&r.startup_json).unwrap_or_default();
    let members: Vec<String> = r
        .members_csv
        .unwrap_or_default()
        .split(',')
        .filter(|s| !s.is_empty())
        .map(String::from)
        .collect();
    let member_count = members.len();
    Workspace { id: r.id, env, startup_commands, members, created_at: r.created_at, updated_at: r.updated_at, member_count }
}
