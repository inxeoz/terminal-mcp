use std::collections::VecDeque;
use std::os::unix::io::{AsRawFd, RawFd};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;

use bytes::Bytes;
use pty_process::Pty;
use regex::Regex;
use tokio::io::{AsyncReadExt, AsyncWriteExt, ReadHalf, WriteHalf};
use tokio::sync::{broadcast, mpsc, Mutex, Notify};

const BUFFER_MAX: usize = 5000;
const BCAST_CAP: usize = 256;

lazy_static::lazy_static! {
    static ref ANSI_RE: Regex = Regex::new(r"\x1b\[[0-9;?]*[a-zA-Z]|\x1b\][^\x07]*\x07").unwrap();
}

fn strip_ansi(text: &str) -> String {
    ANSI_RE.replace_all(text, "").replace('\r', "")
}

/// A single output entry: (cursor_offset, text)
#[derive(Debug, Clone)]
pub struct OutputEntry {
    pub cursor: usize,
    pub text: String,
}

pub struct Session {
    pub id: String,
    pub pid: u32,
    pub alive: Arc<AtomicBool>,
    pub created_at: i64,
    pub updated_at: Arc<Mutex<i64>>,
    pub write_tx: mpsc::Sender<Vec<u8>>,
    pub resize_tx: mpsc::Sender<(u16, u16)>,
    pub kill_tx: mpsc::Sender<()>,
    pub reader_handle: Arc<Mutex<Option<tokio::task::JoinHandle<()>>>>,
    /// Bounded output buffer: (cursor_offset, raw_data)
    pub output: Arc<Mutex<VecDeque<OutputEntry>>>,
    pub cursor: Arc<Mutex<usize>>,
    pub output_notify: Arc<Notify>,
    pub output_bcast: broadcast::Sender<Bytes>,
}

impl Session {
    pub fn is_alive(&self) -> bool {
        self.alive.load(Ordering::Relaxed)
    }

    pub async fn send_input(&self, data: Vec<u8>) {
        let _ = self.write_tx.send(data).await;
    }

    pub fn send_resize(&self, rows: u16, cols: u16) {
        let _ = self.resize_tx.try_send((rows, cols));
    }

    pub async fn kill(&self) {
        self.alive.store(false, Ordering::Relaxed);
        let _ = self.kill_tx.send(()).await;
        // Wait for reader task to finish
        if let Some(handle) = self.reader_handle.lock().await.take() {
            let _ = handle.await;
        }
    }

    pub fn get_cwd(&self) -> Option<String> {
        std::fs::read_link(format!("/proc/{}/cwd", self.pid)).ok()
            .and_then(|p| p.to_str().map(String::from))
    }

    pub async fn append_output(&self, text: String) {
        if text.is_empty() {
            return;
        }
        let mut buf = self.output.lock().await;
        let mut cursor = self.cursor.lock().await;
        let entry = OutputEntry {
            cursor: *cursor,
            text: text.clone(),
        };
        buf.push_back(entry);
        while buf.len() > BUFFER_MAX {
            buf.pop_front();
        }
        *cursor += text.len();
    }

    /// Read output since a byte cursor, optionally capped.
    /// Returns (text_output, new_cursor).
    pub async fn read_output(&self, since: usize, max_bytes: Option<usize>) -> (String, usize) {
        let buf = self.output.lock().await;
        let mut chunks: Vec<&str> = Vec::new();
        let mut total = 0usize;
        let mut next_cursor = since;

        for entry in buf.iter() {
            if entry.cursor + entry.text.len() <= since {
                continue;
            }
            let start = since.saturating_sub(entry.cursor);
            let chunk = &entry.text[start..];
            if let Some(max) = max_bytes {
                if total + chunk.len() > max {
                    let remaining = max - total;
                    if remaining > 0 {
                        let piece = &chunk[..remaining];
                        chunks.push(piece);
                        next_cursor = entry.cursor + start + piece.len();
                    }
                    break;
                }
            }
            chunks.push(chunk);
            total += chunk.len();
            next_cursor = entry.cursor + start + chunk.len();
        }

        (chunks.concat(), next_cursor)
    }

    pub async fn output_text(&self) -> String {
        let buf = self.output.lock().await;
        let mut s = String::new();
        for entry in buf.iter() {
            s.push_str(&entry.text);
        }
        s
    }

    pub async fn search_output(&self, query: &str) -> Vec<String> {
        let buf = self.output.lock().await;
        let lower = query.to_lowercase();
        let mut matches = Vec::new();
        for entry in buf.iter() {
            for line in entry.text.lines() {
                if line.to_lowercase().contains(&lower) {
                    let trimmed = line.trim();
                    if !trimmed.is_empty() {
                        matches.push(trimmed.to_string());
                    }
                }
            }
        }
        matches
    }

    pub fn subscribe(&self) -> broadcast::Receiver<Bytes> {
        self.output_bcast.subscribe()
    }
}

pub struct SpawnOptions {
    pub id: String,
    pub env: Vec<(String, String)>,
    pub rows: u16,
    pub cols: u16,
    pub interactive: bool,
}

pub async fn spawn_session(
    opts: SpawnOptions,
    history: Arc<crate::history::History>,
    alerts: Arc<tokio::sync::RwLock<Vec<crate::manager::CompiledAlert>>>,
) -> anyhow::Result<Session> {
    let (pty, pts) = pty_process::open()?;
    pty.resize(pty_process::Size::new(opts.rows, opts.cols))?;

    let mut env_vars = opts.env.clone();
    if opts.interactive {
        env_vars.push(("TERM".into(), "xterm-256color".into()));
        env_vars.push(("COLORTERM".into(), "truecolor".into()));
        env_vars.push((
            "PS1".into(),
            r"\[\033[01;32m\]\u@\h\[\033[00m\]:\[\033[01;34m\]\w\[\033[00m\]\$ ".into(),
        ));
        env_vars.push(("PROMPT_COMMAND".into(), String::new()));
    } else {
        env_vars.push(("TERM".into(), "dumb".into()));
        env_vars.push(("NO_COLOR".into(), "1".into()));
        env_vars.push(("CLICOLOR".into(), "0".into()));
        env_vars.push(("LS_COLORS".into(), String::new()));
        env_vars.push(("PS1".into(), "$ ".into()));
        env_vars.push(("PROMPT_COMMAND".into(), String::new()));
    }

    let shell = opts.env.iter()
        .find(|(k, _)| k == "SHELL")
        .map(|(_, v)| v.as_str())
        .unwrap_or("/bin/bash")
        .to_string();
    let is_bash = shell.ends_with("bash");
    let child = if is_bash {
        pty_process::Command::new(&shell)
            .args(["--noprofile", "--norc"])
            .env_clear()
            .envs(env_vars)
            .spawn(pts)?
    } else {
        pty_process::Command::new(&shell)
            .env_clear()
            .envs(env_vars)
            .spawn(pts)?
    };
    let pid = child.id().unwrap_or(0);

    let resize_fd: RawFd = pty.as_raw_fd();

    let (read_half, write_half) = tokio::io::split(pty);

    let (write_tx, write_rx) = mpsc::channel::<Vec<u8>>(64);
    let (resize_tx, resize_rx) = mpsc::channel::<(u16, u16)>(8);
    let (kill_tx, kill_rx) = mpsc::channel::<()>(1);

    let output = Arc::new(Mutex::new(VecDeque::new()));
    let cursor = Arc::new(Mutex::new(0usize));
    let output_notify = Arc::new(Notify::new());
    let (output_bcast, _) = broadcast::channel::<Bytes>(BCAST_CAP);

    let alive = Arc::new(AtomicBool::new(true));
    let session_id = opts.id.clone();

    let handle = tokio::spawn(pty_task(
        session_id,
        read_half,
        write_half,
        write_rx,
        resize_rx,
        kill_rx,
        resize_fd,
        output.clone(),
        cursor.clone(),
        output_notify.clone(),
        output_bcast.clone(),
        alive.clone(),
        history,
        alerts,
        child,
    ));

    let now = chrono::Utc::now().timestamp();
    let reader_handle = Arc::new(Mutex::new(Some(handle)));

    Ok(Session {
        id: opts.id,
        pid,
        alive,
        created_at: now,
        updated_at: Arc::new(Mutex::new(now)),
        write_tx,
        resize_tx,
        kill_tx,
        reader_handle,
        output,
        cursor,
        output_notify,
        output_bcast,
    })
}

async fn pty_task(
    terminal_id: String,
    mut read_half: ReadHalf<Pty>,
    mut write_half: WriteHalf<Pty>,
    mut write_rx: mpsc::Receiver<Vec<u8>>,
    mut resize_rx: mpsc::Receiver<(u16, u16)>,
    mut kill_rx: mpsc::Receiver<()>,
    resize_fd: RawFd,
    output: Arc<Mutex<VecDeque<OutputEntry>>>,
    cursor: Arc<Mutex<usize>>,
    output_notify: Arc<Notify>,
    output_bcast: broadcast::Sender<Bytes>,
    alive: Arc<AtomicBool>,
    history: Arc<crate::history::History>,
    alerts: Arc<tokio::sync::RwLock<Vec<crate::manager::CompiledAlert>>>,
    mut child: tokio::process::Child,
) {
    let mut buf = vec![0u8; 4096];

    loop {
        tokio::select! {
            biased;
            _ = kill_rx.recv() => break,

            result = read_half.read(&mut buf) => {
                match result {
                    Ok(0) | Err(_) => break,
                    Ok(n) => {
                        let raw_text = String::from_utf8_lossy(&buf[..n]).to_string();

                        // Append to bounded output buffer with cursor tracking
                        {
                            let mut out = output.lock().await;
                            let mut cur = cursor.lock().await;
                            let entry = OutputEntry { cursor: *cur, text: raw_text.clone() };
                            out.push_back(entry);
                            while out.len() > BUFFER_MAX {
                                out.pop_front();
                            }
                            *cur += raw_text.len();
                        }
                        output_notify.notify_waiters();
                        let _ = output_bcast.send(Bytes::from(raw_text.clone()));

                        // Record ANSI-stripped output to history DB
                        let clean = strip_ansi(&raw_text);
                        if !clean.is_empty() {
                            let _ = history.record_output(&terminal_id, &clean).await;
                        }

                        // Check alert patterns (on raw or stripped?)
                        let alert_list = alerts.read().await;
                        for alert in alert_list.iter() {
                            if alert.scope == "global"
                                || alert.terminal_id.as_deref() == Some(&terminal_id)
                            {
                                if alert.regex.is_match(&clean) {
                                    let _ = history
                                        .record_alert_event(
                                            &alert.id,
                                            &terminal_id,
                                            &alert.pattern,
                                            clean.trim(),
                                        )
                                        .await;
                                }
                            }
                        }
                    }
                }
            }

            Some(data) = write_rx.recv() => {
                let _ = write_half.write_all(&data).await;
            }

            Some((rows, cols)) = resize_rx.recv() => {
                resize_pty(resize_fd, rows, cols);
            }

            _ = child.wait() => break,
        }
    }

    alive.store(false, Ordering::Relaxed);
    output_notify.notify_waiters();
}

fn resize_pty(fd: RawFd, rows: u16, cols: u16) {
    unsafe {
        let ws = libc::winsize {
            ws_row: rows,
            ws_col: cols,
            ws_xpixel: 0,
            ws_ypixel: 0,
        };
        libc::ioctl(fd, libc::TIOCSWINSZ, &ws as *const libc::winsize);
    }
}

pub fn kill_pid(pid: u32, signal: &str) -> anyhow::Result<()> {
    let sig = match signal {
        "SIGINT" => libc::SIGINT,
        "SIGTERM" => libc::SIGTERM,
        "SIGKILL" => libc::SIGKILL,
        _ => return Err(anyhow::anyhow!("unknown signal: {signal}")),
    };
    unsafe {
        libc::kill(pid as libc::pid_t, sig);
    }
    Ok(())
}

/// Send environment changes to a running shell
pub async fn set_env_in_shell(session: &Session, key: &str, value: &str) {
    let cmd = format!("export {}={}\n", shell_quote(key), shell_quote(value));
    session.send_input(cmd.into_bytes()).await;
}

pub async fn unset_env_in_shell(session: &Session, key: &str) {
    let cmd = format!("unset {}\n", shell_quote(key));
    session.send_input(cmd.into_bytes()).await;
}

fn shell_quote(s: &str) -> String {
    // basic shell quoting: wrap in single quotes, escape internal single quotes
    let escaped = s.replace('\'', "'\\''");
    format!("'{escaped}'")
}
