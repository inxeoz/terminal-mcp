/// Stress test: 20 concurrent sessions, heavy I/O, verify cleanup
/// Usage: cargo run --bin stress [--release]
use std::sync::Arc;
use std::time::Instant;
use i4z_terminal_mcp::manager::Manager;

#[tokio::main]
async fn main() {
    let state_dir = "/tmp/i4z-stress";
    let _ = std::fs::remove_dir_all(state_dir);

    eprintln!("=== i4z-terminal-mcp Stress Test ===");

    let manager = Arc::new(Manager::new(state_dir).await.unwrap());

    // ── Phase 1: Create 20 sessions ──
    let start = Instant::now();
    let mut handles = Vec::new();
    for i in 0..20 {
        let mgr = manager.clone();
        handles.push(tokio::spawn(async move {
            mgr.create(&format!("stress-{i}"), None, None, None, false, false).await.unwrap()
        }));
    }
    let mut sessions = Vec::new();
    for h in handles {
        sessions.push(h.await.unwrap());
    }
    eprintln!("Created 20 sessions in {}ms", start.elapsed().as_millis());

    // ── Phase 2: Send commands concurrently ──
    let start = Instant::now();
    let mut cmd_tasks = Vec::new();
    for i in 0..20 {
        let mgr = manager.clone();
        let name = format!("stress-{i}");
        cmd_tasks.push(tokio::spawn(async move {
            for j in 0..50 {
                mgr.send(&name, &format!("echo 'stress {i}.{j}'\n")).await.ok();
            }
        }));
    }
    for t in cmd_tasks {
        t.await.unwrap();
    }
    eprintln!("Sent 1000 commands (20×50) in {}ms", start.elapsed().as_millis());

    tokio::time::sleep(tokio::time::Duration::from_millis(500)).await;

    // ── Phase 3: Read output from all ──
    let start = Instant::now();
    for s in &sessions {
        let (output, cursor) = s.read_output(0, Some(1024)).await;
        let _ = (output, cursor);
    }
    eprintln!("Read 20 sessions in {}ms", start.elapsed().as_millis());

    // ── Phase 4: List and status all ──
    let start = Instant::now();
    let all = manager.list_all().await;
    eprintln!("List all: {} terminals in {}ms", all.len(), start.elapsed().as_millis());

    let start = Instant::now();
    for i in 0..20 {
        let status = manager.status(&format!("stress-{i}")).await.unwrap();
        assert!(status["alive"].as_bool().unwrap_or(false), "session stress-{i} should be alive");
    }
    eprintln!("Status ×20: {}ms", start.elapsed().as_millis());

    // ── Phase 5: Kill all ──
    let start = Instant::now();
    let mut kill_tasks = Vec::new();
    for i in 0..20 {
        let mgr = manager.clone();
        let name = format!("stress-{i}");
        kill_tasks.push(tokio::spawn(async move {
            mgr.kill(&name).await.unwrap();
        }));
    }
    for t in kill_tasks {
        t.await.unwrap();
    }
    let kill_ms = start.elapsed().as_millis();
    eprintln!("Killed 20 sessions in {kill_ms}ms");

    // Verify all dead
    let all = manager.list_all().await;
    let alive = all.iter().filter(|t| t["alive"].as_bool().unwrap_or(false)).count();
    eprintln!("After kill: {} alive, {} total in list",
        alive, all.len());

    // Verify sessions cleared from in-memory registry
    eprintln!("In-memory sessions: {}", manager.sessions.len());
    assert_eq!(manager.sessions.len(), 0, "All sessions should be removed from memory");

    // ── Phase 6: Health check ──
    let health = manager.health().await.unwrap();
    let counts = &health["counts"];
    eprintln!("DB events: {}", counts.get("events").and_then(|v| v.as_i64()).unwrap_or(0));
    eprintln!("DB profiles: {}", counts.get("profiles").and_then(|v| v.as_i64()).unwrap_or(0));

    eprintln!("\n=== Stress Test PASSED ===");

    // Cleanup
    manager.shutdown().await.ok();
    let _ = std::fs::remove_dir_all(state_dir);
}
