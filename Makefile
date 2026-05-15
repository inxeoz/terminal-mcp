.PHONY: help frontend build release run run-release install-global inspect inspect-global stop-inspector test test-web bench stress check clean

# ── Default ────────────────────────────────────────────────────────────────────
help:
	@echo "i4z-terminal-mcp — Makefile"
	@echo ""
	@echo "  BUILD"
	@echo "    make frontend       trunk build frontend (WASM)"
	@echo "    make build          cargo build (debug)"
	@echo "    make release        cargo build --release"
	@echo "    make run            run server (debug)"
	@echo "    make run-release    run server (release)"
	@echo "    make install-global release build + copy to ~/.local/bin/"
	@echo ""
	@echo "  INSPECTOR"
	@echo "    make inspect        run MCP Inspector (local binary)"
	@echo "    make inspect-global run MCP Inspector (global binary)"
	@echo ""
	@echo "  TEST"
	@echo "    make test           cargo test"
	@echo "    make test-web       web integration test"
	@echo "    make bench          run benchmark"
	@echo "    make stress         run stress test (20 sessions)"
	@echo ""
	@echo "  UTILITY"
	@echo "    make check          cargo check"
	@echo "    make clean          clean build artifacts"

# ── Build ──────────────────────────────────────────────────────────────────────

frontend:
	cd crates/frontend && trunk build --release
	@echo "Frontend built → crates/frontend/dist/"

build:
	cargo build -p i4z-terminal-mcp

release:
	cargo build --release -p i4z-terminal-mcp

run: build
	cargo run -p i4z-terminal-mcp

run-release: release
	cargo run --release -p i4z-terminal-mcp

install-global: release
	@mkdir -p "$$HOME/.local/bin"
	cp target/release/i4z-terminal-mcp "$$HOME/.local/bin/i4z-terminal-mcp"
	@echo "Installed → ~/.local/bin/i4z-terminal-mcp"

# ── Inspector ──────────────────────────────────────────────────────────────────

inspect: release stop-inspector
	DANGEROUSLY_OMIT_AUTH=true bunx @modelcontextprotocol/inspector \
		./target/release/i4z-terminal-mcp

inspect-global: install-global stop-inspector
	DANGEROUSLY_OMIT_AUTH=true bunx @modelcontextprotocol/inspector i4z-terminal-mcp

# ── Test ───────────────────────────────────────────────────────────────────────

test:
	cargo test -p i4z-terminal-mcp -- --nocapture

test-web: release
	@echo "Starting server on port 9021 (fresh tmp DB)..."
	@I4Z_TERMINAL_WEB_PORT=9021 I4Z_TERMINAL_STATE_DIR=/tmp/i4z-test-$$$$ ./target/release/i4z-terminal-mcp &
	@sleep 1
	@BASE_URL=http://localhost:9021 bun test.mjs; \
	  STATUS=$$?; \
	  pkill -f "i4z-terminal-mcp" 2>/dev/null || true; \
	  exit $$STATUS

bench:
	cargo run --release -p i4z-terminal-mcp --bin bench

stress:
	cargo run --release -p i4z-terminal-mcp --bin stress

# ── Utility ────────────────────────────────────────────────────────────────────

stop-inspector:
	@fuser -k 6277/tcp 2>/dev/null || true
	@fuser -k 6274/tcp 2>/dev/null || true

check:
	cargo check -p i4z-terminal-mcp

clean:
	cargo clean
