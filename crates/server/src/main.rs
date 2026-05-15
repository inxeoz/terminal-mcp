use std::sync::Arc;

use i4z_terminal_mcp::manager::Manager;
use tokio::signal;

fn free_port() -> u16 {
    let listener = std::net::TcpListener::bind("0.0.0.0:0").expect("bind");
    listener.local_addr().unwrap().port()
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    tracing_subscriber::fmt()
        .with_writer(std::io::stderr)
        .with_env_filter(
            tracing_subscriber::EnvFilter::from_default_env()
                .add_directive("i4z_terminal_mcp=info".parse().unwrap())
                .add_directive("actix_web=warn".parse().unwrap()),
        )
        .init();

    let state_dir = std::env::var("I4Z_TERMINAL_STATE_DIR")
        .unwrap_or_else(|_| {
            dirs_or_home()
                .to_string_lossy()
                .to_string()
        });

    let web_port: u16 = std::env::var("I4Z_TERMINAL_WEB_PORT")
        .ok()
        .and_then(|v| v.parse().ok())
        .unwrap_or_else(free_port);

    let web_host = std::env::var("I4Z_TERMINAL_WEB_HOST")
        .unwrap_or_else(|_| "0.0.0.0".to_string());

    let manager = Arc::new(Manager::new(&state_dir).await?);

    let web_url = format!("http://localhost:{web_port}");
    *manager.web_url.write().await = web_url.clone();

    eprintln!("i4z-terminal-mcp v{} (Rust) — Ctrl+D to stop", env!("CARGO_PKG_VERSION"));
    eprintln!("  Web UI: {web_url}");

    let web_manager = manager.clone();
    let web_host_clone = web_host.clone();

    let shutdown_manager = manager.clone();

    // Run MCP server in background - it may exit when no client is connected
    // but the web server should continue running
    let mcp_manager = manager.clone();
    tokio::spawn(async move {
        if let Err(e) = i4z_terminal_mcp::tools::run_mcp_server(mcp_manager).await {
            tracing::info!("mcp server stopped: {e}");
        }
    });

    tokio::select! {
        res = i4z_terminal_mcp::web::run(web_manager, &web_host_clone, web_port) => {
            if let Err(e) = res { eprintln!("web server error: {e}"); }
        }
        _ = signal::ctrl_c() => {
            eprintln!("\nShutting down...");
        }
    }

    // Graceful shutdown: kill all sessions
    let _ = shutdown_manager.shutdown().await;
    eprintln!("i4z-terminal-mcp stopped");

    Ok(())
}

fn dirs_or_home() -> std::path::PathBuf {
    if let Some(data) = std::env::var_os("XDG_DATA_HOME") {
        std::path::PathBuf::from(data).join("i4z-terminal-mcp")
    } else if let Some(home) = std::env::var_os("HOME") {
        std::path::PathBuf::from(home)
            .join(".local/share/i4z-terminal-mcp")
    } else {
        std::path::PathBuf::from("/tmp/i4z-terminal-mcp")
    }
}
