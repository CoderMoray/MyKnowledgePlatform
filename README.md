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
- **MCP native** — 18 tools for AI agents: navigate, read, write, rename, archive, share
- **Local first** — All data stays on your machine, optional cloud sync
- **Auto archive** — Completed / cancelled / abandoned projects move to `archive/` automatically
- **Web UI** — Alpine.js SPA with TipTap editor (in development)
- **Encrypted sharing** — `.mkpkg` packages with field-level encryption

## Quick Start

```bash
# Install
pip install myknowledge

# Initialize
myknowledge init                      # creates ~/.myknowledge/
myknowledge login your@email.com name # required for write operations

# Start web UI
myknowledge serve                     # → http://127.0.0.1:8080
```

## Usage

### AI Agent (MCP)

Configure in your MCP-compatible agent client (CodeBuddy, WorkBuddy, etc.):

```json
{
  "mcpServers": {
    "myknowledge": {
      "type": "stdio",
      "command": "myknowledge",
      "args": ["mcp"]
    }
  }
}
```

The agent acquires a lock, reads the knowledge base, writes changes, and releases the lock. The system automatically rebuilds indices, commits to git, and broadcasts updates via SSE.

### Web UI

```bash
myknowledge serve --port 8080
# Open http://127.0.0.1:8080
```

## Project Structure

```
myknowledge/
├── backend/
│   ├── cli.py               # CLI entry: init / mcp / serve / login
│   ├── mcp_server.py        # 18 MCP tools
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
git clone https://github.com/CoderMoray/MyKnowledgePlatform
cd MyKnowledgePlatform
pip install -e .
```

Run tests:

```bash
pytest tests/ -v
```

## Versioning

- **System version**: defined in `backend/__version__.py` (currently 0.5.0)
- **KB version**: git commit hash from `agent-commit.txt` checkpoint

## License

[Apache License 2.0](LICENSE) — Copyright 2026 Moray Liang

## Acknowledgments

**Designer & Creator**: [Moray Liang](https://github.com/CoderMoray)

Contributors are recorded in [`NOTICE`](NOTICE).
