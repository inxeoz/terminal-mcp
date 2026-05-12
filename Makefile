.PHONY: help py-install py-run py-run-dev rs-build rs-release rs-run rs-run-release rs-install-global inspect inspect-rust inspect-global stop-inspector check clean test bench stress rs-test-web

# ── Default ────────────────────────────────────────────────────────────────────
help:
	@echo "i4z-terminal-mcp — Makefile"
	@echo ""
	@echo "  PYTHON"
	@echo "    make py-install     pip install -e python/ (editable, development)"
	@echo "    make py-run         run Python MCP server"
	@echo "    make py-run-dev     run Python web server on port 9020 (no MCP)"
	@echo ""
	@echo "  RUST"
	@echo "    make rs-build       cargo build (debug)"
	@echo "    make rs-release     cargo build --release"
	@echo "    make rs-run         run Rust MCP server (debug)"
	@echo "    make rs-run-release run Rust MCP server (release)"
	@echo "    make rs-install-global build release + copy to ~/.local/bin/"
	@echo ""
	@echo "  INSPECTOR (via bunx)"
	@echo "    make inspect        py-install + bunx inspector (Python)"
	@echo "    make inspect-rust   rs-release + bunx inspector (Rust, local binary)"
	@echo "    make inspect-global rs-install-global + bunx inspector (Rust, global)"
	@echo ""
	@echo "  TEST & BENCH"
	@echo "    make test           cargo test (Rust)"
	@echo "    make bench          run Rust benchmark"
	@echo "    make stress         run Rust stress test (20 sessions)"
	@echo ""
	@echo "  UTILITY"
	@echo "    make check          lint+typecheck Python, cargo check Rust"
	@echo "    make clean          clean build artifacts, pycache, DB files"

# ── Python ─────────────────────────────────────────────────────────────────────

py-install:
	cd python && pip install -e .

py-run: py-install
	i4z-terminal-mcp

py-run-dev:
	cd python && I4Z_TERMINAL_WEB_PORT=9020 python -m terminal.server

# ── Rust ───────────────────────────────────────────────────────────────────────

rs-build:
	cd rust && cargo build

rs-release:
	cd rust && cargo build --release

rs-run: rs-build
	cd rust && cargo run --bin i4z-terminal-mcp

rs-run-release: rs-release
	cd rust && cargo run --release --bin i4z-terminal-mcp

rs-install-global: rs-release
	@mkdir -p "$$HOME/.local/bin"
	cp rust/target/release/i4z-terminal-mcp "$$HOME/.local/bin/i4z-terminal-mcp"
	@echo "Installed i4z-terminal-mcp → ~/.local/bin/i4z-terminal-mcp"
	@echo "Make sure ~/.local/bin is on your PATH"

# ── Inspector ──────────────────────────────────────────────────────────────────

inspect: py-install stop-inspector
	DANGEROUSLY_OMIT_AUTH=true bunx @modelcontextprotocol/inspector i4z-terminal-mcp

inspect-rust: rs-release stop-inspector
	DANGEROUSLY_OMIT_AUTH=true bunx @modelcontextprotocol/inspector \
		./rust/target/release/i4z-terminal-mcp

inspect-global: rs-install-global stop-inspector
	DANGEROUSLY_OMIT_AUTH=true bunx @modelcontextprotocol/inspector i4z-terminal-mcp

# ── Test & Benchmark ───────────────────────────────────────────────────────────

test:
	cd rust && cargo test -- --nocapture

rs-test-web: rs-release
	@echo "Starting Rust server on port 9021..."
	@I4Z_TERMINAL_WEB_PORT=9021 ./rust/target/release/i4z-terminal-mcp &
	@sleep 1
	@BASE_URL=http://localhost:9021 bunx playwright@latest --browser chromium node test.mjs; \
	  STATUS=$$?; \
	  pkill -f "i4z-terminal-mcp" 2>/dev/null || true; \
	  exit $$STATUS

bench:
	cd rust && cargo run --release --bin bench

stress:
	cd rust && cargo run --release --bin stress

# ── Utility ────────────────────────────────────────────────────────────────────

stop-inspector:
	@fuser -k 6277/tcp 2>/dev/null || true
	@fuser -k 6274/tcp 2>/dev/null || true

check:
	cd python && python -m py_compile terminal/*.py 2>&1 || true
	cd rust && cargo check 2>&1

clean:
	cd rust && cargo clean
	rm -rf python/build python/dist python/*.egg-info python/terminal/__pycache__
	find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
