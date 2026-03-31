"""
FastMCP Server Example — kendr scaffolding starter.

This file shows you how to create your own MCP server that kendr can
connect to. Once running, add it in the kendr UI at /mcp.

Install dependencies:
    pip install fastmcp

Run this server:
    python mcp_servers/example_fastmcp_server.py

Then in kendr MCP Manager (http://localhost:5000/mcp):
    Name:       Example Server
    Type:       HTTP
    Connection: http://localhost:8000/mcp
    Click "Connect & Discover Tools"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
How MCP + kendr works
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  1.  You create an MCP server (like this file) using @mcp.tool decorators.
  2.  kendr acts as an MCP client (just like Cursor does).
  3.  kendr connects to your server, discovers all its tools, and makes
      them available to agents.
  4.  You can run as many MCP servers as you want — each on a different port.

Supported transports
━━━━━━━━━━━━━━━━━━━━
  HTTP/SSE  →  mcp.run(transport="http", host="...", port=..., path="/mcp")
  stdio     →  mcp.run(transport="stdio")   (connect via shell command)
"""

import os
import platform
import subprocess
import sys
from datetime import datetime, timezone

from fastmcp import FastMCP

# ── Create the server ────────────────────────────────────────────────────────
mcp = FastMCP(
    name="kendr-example-server",
    instructions=(
        "This is a kendr example MCP server. "
        "It demonstrates how to expose Python functions as tools."
    ),
)


# ── Tool 1: ping / echo ──────────────────────────────────────────────────────
@mcp.tool
def echo(message: str) -> str:
    """Return the message back unchanged. Useful for testing connectivity."""
    return f"Echo: {message}"


# ── Tool 2: arithmetic ───────────────────────────────────────────────────────
@mcp.tool
def add(a: float, b: float) -> float:
    """Add two numbers and return the sum."""
    return a + b


@mcp.tool
def multiply(a: float, b: float) -> float:
    """Multiply two numbers and return the product."""
    return a * b


# ── Tool 3: system info ──────────────────────────────────────────────────────
@mcp.tool
def system_info() -> dict:
    """Return basic information about the host machine and Python environment."""
    return {
        "platform": platform.system(),
        "platform_release": platform.release(),
        "python_version": sys.version,
        "python_executable": sys.executable,
        "cwd": os.getcwd(),
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }


# ── Tool 4: shell command (read-only example) ────────────────────────────────
@mcp.tool
def list_directory(path: str = ".") -> dict:
    """List files and directories at the given path.

    Args:
        path: Directory path to list. Defaults to current directory.
    """
    try:
        entries = os.listdir(path)
        files = [e for e in entries if os.path.isfile(os.path.join(path, e))]
        dirs = [e for e in entries if os.path.isdir(os.path.join(path, e))]
        return {
            "path": os.path.abspath(path),
            "files": sorted(files),
            "directories": sorted(dirs),
            "total": len(entries),
        }
    except Exception as exc:
        return {"error": str(exc), "path": path}


# ── Tool 5: returning structured data ────────────────────────────────────────
@mcp.tool
def summarize_text(text: str, max_words: int = 50) -> dict:
    """Produce a simple word-count summary of the provided text.

    Args:
        text: The input text to summarize.
        max_words: Maximum words to include in the excerpt (default 50).
    """
    words = text.split()
    word_count = len(words)
    char_count = len(text)
    sentences = [s.strip() for s in text.replace("!", ".").replace("?", ".").split(".") if s.strip()]
    excerpt = " ".join(words[:max_words]) + ("..." if word_count > max_words else "")
    return {
        "word_count": word_count,
        "char_count": char_count,
        "sentence_count": len(sentences),
        "excerpt": excerpt,
    }


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    host = os.getenv("MCP_HOST", "127.0.0.1")
    port = int(os.getenv("MCP_PORT", "8000"))
    print(f"Starting kendr example MCP server on http://{host}:{port}/mcp")
    print(f"Connect from kendr UI at /mcp using:")
    print(f"  Type:       HTTP")
    print(f"  Connection: http://{host}:{port}/mcp")
    mcp.run(transport="http", host=host, port=port, path="/mcp")
