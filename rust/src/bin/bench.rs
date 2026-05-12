/// Benchmark tool for i4z-terminal-mcp
/// Usage: cargo run --bin bench [--release]
use std::time::Instant;

#[tokio::main]
async fn main() {
    let state_dir = std::env::var("I4Z_TERMINAL_STATE_DIR")
        .unwrap_or_else(|_| "/tmp/i4z-bench".to_string());

    let _ = std::fs::remove_dir_all(&state_dir);

    eprintln!("=== i4z-terminal-mcp Rust Benchmark ===");
    eprintln!("State dir: {state_dir}");

    let start = Instant::now();
    let manager = std::sync::Arc::new(
        i4z_terminal_mcp::manager::Manager::new(&state_dir)
            .await
            .unwrap(),
    );
    let startup_ms = start.elapsed().as_millis();
    eprintln!("Startup: {startup_ms}ms");

    // Session creation
    let start = Instant::now();
    let mut handles = Vec::new();
    for i in 0..10 {
        let mgr = manager.clone();
        let name = format!("bench-{i}");
        handles.push(tokio::spawn(async move {
            mgr.create(&name, None, None, None, false, false).await.unwrap()
        }));
    }
    let mut sessions = Vec::new();
    for h in handles {
        sessions.push(h.await.unwrap());
    }
    let create_10_ms = start.elapsed().as_millis();
    eprintln!("Create 10 sessions: {create_10_ms}ms");

    // Send input throughput
    let start = Instant::now();
    let mut send_tasks = Vec::new();
    for (i, _session) in sessions.iter().enumerate() {
        let mgr = manager.clone();
        let name = format!("bench-{i}");
        send_tasks.push(tokio::spawn(async move {
            for j in 0..100 {
                mgr.send(&name, &format!("echo 'bench {i} iter {j}'\n")).await.ok();
            }
        }));
    }
    for task in send_tasks {
        task.await.unwrap();
    }
    let send_ms = start.elapsed().as_millis();
    eprintln!(
        "Send 1000 commands (10 sessions × 100): {send_ms}ms ({:.1} cmd/s)",
        (1000.0 / (send_ms as f64)) * 1000.0
    );

    // Output read
    tokio::time::sleep(tokio::time::Duration::from_millis(500)).await;
    let start = Instant::now();
    for session in &sessions {
        let (output, _) = session.read_output(0, None).await;
        let _len = output.len();
    }
    let read_ms = start.elapsed().as_millis();
    eprintln!("Read 10 sessions: {read_ms}ms");

    // List operations
    let start = Instant::now();
    for _ in 0..100 {
        let _ = manager.list_all().await;
    }
    let list_ms = start.elapsed().as_millis();
    eprintln!("List terminals ×100: {list_ms}ms");

    // Status operations
    let start = Instant::now();
    for i in 0..10 {
        let _ = manager.status(&format!("bench-{i}")).await;
    }
    let status_ms = start.elapsed().as_millis();
    eprintln!("Status ×10: {status_ms}ms");

    eprintln!("Active sessions: {}", manager.sessions.len());

    // Cleanup
    for session in &sessions {
        session.kill().await;
    }
    eprintln!("Cleanup complete");
}
