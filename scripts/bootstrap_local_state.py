#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_WORKDIR = ROOT / "output" / "workspace"
DEFAULT_KENDR_HOME = ROOT / "output" / ".kendr"
DEFAULT_CHROMA_PATH = DEFAULT_KENDR_HOME / "rag" / "chroma"
DEFAULT_RAG_UPLOADS = DEFAULT_KENDR_HOME / "rag" / "uploads"


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _ensure_env_file() -> tuple[bool, Path]:
    env_path = ROOT / ".env"
    example_path = ROOT / ".env.example"
    if env_path.exists():
        return False, env_path
    if example_path.exists():
        text = example_path.read_text(encoding="utf-8")
        text = text.replace('KENDR_WORKING_DIR="C:/path/to/your/workdir"', f'KENDR_WORKING_DIR="{DEFAULT_WORKDIR.as_posix()}"')
        text = text.replace('KENDR_HOME="~/.kendr"', f'KENDR_HOME="{DEFAULT_KENDR_HOME.as_posix()}"\nKENDR_CHROMA_PATH="{DEFAULT_CHROMA_PATH.as_posix()}"')
        env_path.write_text(text, encoding="utf-8")
        return True, env_path
    env_path.write_text(
        (
            f'OPENAI_API_KEY=\n'
            f'KENDR_WORKING_DIR="{DEFAULT_WORKDIR.as_posix()}"\n'
            f'KENDR_HOME="{DEFAULT_KENDR_HOME.as_posix()}"\n'
            f'KENDR_CHROMA_PATH="{DEFAULT_CHROMA_PATH.as_posix()}"\n'
            'QDRANT_URL=""\n'
            'SERP_API_KEY=\n'
        ),
        encoding="utf-8",
    )
    return True, env_path


def main() -> int:
    _ensure_dir(ROOT / "output")
    _ensure_dir(ROOT / "logs")
    _ensure_dir(DEFAULT_WORKDIR)
    _ensure_dir(ROOT / "output" / "workspace_memory")
    _ensure_dir(ROOT / ".secrets")
    _ensure_dir(DEFAULT_KENDR_HOME)
    _ensure_dir(DEFAULT_CHROMA_PATH)
    _ensure_dir(DEFAULT_RAG_UPLOADS)

    created_env, env_path = _ensure_env_file()

    if created_env:
        print(f"[bootstrap] created local env file: {env_path}")
        print("[bootstrap] fill in credentials locally before running long/external tasks.")
    else:
        print(f"[bootstrap] local env file already exists: {env_path}")

    print(
        "[bootstrap] ensured local runtime folders: "
        "output/, output/workspace/, logs/, output/workspace_memory/, .secrets/, output/.kendr/rag/chroma/, output/.kendr/rag/uploads/"
    )
    print("[bootstrap] reminder: local credential files are ignored by .gitignore/.dockerignore.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
