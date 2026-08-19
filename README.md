# MyKnowledge

[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-%3E%3D3.10-blue)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/MCP-ready-green)](https://modelcontextprotocol.io/)
[![PyPI](https://img.shields.io/pypi/v/myknowledge)](https://pypi.org/project/myknowledge/)

Local-first knowledge management platform. Markdown as source of truth, Git for versioning, MCP for AI agent integration.

Allows any MCP-compatible AI agent client to read and write your knowledge base — the more you use it, the richer it becomes.

---

## Features

- **Plain text storage** — Markdown files with YAML frontmatter, no lock-in
- **Git versioning** — Every write is automatically committed, fully traceable
- **MCP native** — 22 tools for AI agents: navigate, read, write, rename, move, delete, archive, share
- **CLI self-management** — `doctor` (health check), `version --check` (PyPI version), `upgrade` (one-command update), `mcp-config` (JSON output)
- **Local first** — All data stays on your machine, optional cloud sync
- **Auto archive** — Completed / cancelled / abandoned projects move to `archive/` automatically
- **Auto lock** — Each write operation auto-acquires and releases the write lock
- **Web UI** — Alpine.js SPA with TipTap editor (in development)
- **Encrypted sharing** — `.mkpkg` packages with field-level encryption

## Quick Start

```bash
# Install
pip install myknowledge

# Initialize
myknowledge init                      # creates ~/.myknowledge/
myknowledge doctor                     # verify everything is ready
myknowledge login your@email.com name  # required for write operations

# Start MCP server (for AI agents)
myknowledge mcp

# Or start web UI
myknowledge serve                     # → http://127.0.0.1:8080

# Self-diagnose and upgrade anytime
myknowledge doctor
myknowledge version --check
myknowledge upgrade
```

## Usage

### AI Agent (MCP)

Configure in your MCP-compatible agent client (CodeBuddy, Trae, WorkBuddy, etc.):

```json
{
  "mcpServers": {
    "MyKnowledge": {
      "command": "myknowledge",
      "args": ["mcp"]
    }
  }
}
```

> **Auto-lock**: Each write operation auto-acquires and releases the write lock. The system rebuilds indices, commits to git, and broadcasts updates via SSE.

Get your exact config with: `myknowledge mcp-config`

### Web UI

```bash
myknowledge serve --port 8080
# Open http://127.0.0.1:8080
```

## Project Structure

```
myknowledge/
├── backend/
│   ├── cli.py               # CLI: init / mcp / serve / login / doctor / upgrade / version / mcp-config
│   ├── mcp_server.py        # 22 MCP tools
│   ├── main.py              # FastAPI REST API
│   ├── storage.py           # Markdown I/O
│   ├── readme_generator.py  # Readme index generation
│   ├── git_manager.py       # Git operations
│   ├── events.py            # SSE real-time updates
│   ├── share.py             # .mkpkg encrypted sharing
│   └── config.py            # Identity + environment
├── frontend/                # Alpine.js SPA (WIP)
├── docs/                    # Design documents
└── tests/
```

## Knowledge Base Layout

```
~/.myknowledge/
├── readme.md                # Route index
├── common-knowledge/        # Documents (.md)
├── projects/                # Projects (recursive)
│   └── ProjectA/
│       ├── readme.md
│       ├── common-knowledge/
│       ├── projects/        # Sub-projects
│       └── archive/         # Archived sub-projects
├── archive/                 # Archived projects
├── project-status.md        # Project status overview
└── _templates/              # Readme templates
```

## Development

```bash
git clone https://github.com/CoderMoray/MyKnowledge_PlatForm
cd MyKnowledge_PlatForm
pip install -e .
```

Run tests:

```bash
pytest tests/ -v
```

## Self-Installation

MyKnowledge comes with a complete AI installation guide (`docs/AI-SETUP.md`). Copy it to any MCP-compatible AI agent, and it will:

1. Check prerequisites (Python, Git, pip)
2. Install via `pip install myknowledge`
3. Run health checks and initialize the KB
4. Guide you to set your identity
5. Configure MCP in your agent client
6. Set up automations for version checks and KB change summaries

## Versioning

- **System version**: defined in `backend/__version__.py` (currently 0.7.6)
- **KB version**: git commit hash from `agent-commit.txt` checkpoint

## License

[Apache License 2.0](LICENSE) — Copyright 2026 Moray Liang

## Acknowledgments

**Designer & Creator**: [Moray Liang](https://github.com/CoderMoray)

Contributors are recorded in [`NOTICE`](NOTICE).
