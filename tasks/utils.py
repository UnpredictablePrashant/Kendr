import os
import logging
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv()

OUTPUT_DIR = "output"
os.makedirs(OUTPUT_DIR, exist_ok=True)
RUN_OUTPUT_ROOT = os.path.join(OUTPUT_DIR, "runs")
os.makedirs(RUN_OUTPUT_ROOT, exist_ok=True)
ACTIVE_OUTPUT_DIR = OUTPUT_DIR

llm = ChatOpenAI(model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"))

logger = logging.getLogger("multi_agent_workflow")
logger.setLevel(logging.INFO)
logger.handlers.clear()

file_handler = logging.FileHandler(
    os.path.join(ACTIVE_OUTPUT_DIR, "execution.log"),
    mode="w",
    encoding="utf-8",
)
file_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(logging.Formatter("%(message)s"))

logger.addHandler(file_handler)
logger.addHandler(console_handler)
logger.propagate = False


def get_output_dir() -> str:
    return ACTIVE_OUTPUT_DIR


def resolve_output_path(filename: str | os.PathLike[str]) -> str:
    path = Path(filename)
    if path.is_absolute():
        return str(path)
    return str(Path(get_output_dir()) / path)


def set_active_output_dir(path: str) -> str:
    global ACTIVE_OUTPUT_DIR, file_handler

    ACTIVE_OUTPUT_DIR = path
    os.makedirs(ACTIVE_OUTPUT_DIR, exist_ok=True)

    try:
        logger.removeHandler(file_handler)
        file_handler.close()
    except Exception:
        pass

    file_handler = logging.FileHandler(
        os.path.join(ACTIVE_OUTPUT_DIR, "execution.log"),
        mode="w",
        encoding="utf-8",
    )
    file_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    logger.addHandler(file_handler)
    return ACTIVE_OUTPUT_DIR


def create_run_output_dir(run_id: str) -> str:
    prefix = f"{run_id}_"
    run_dir = tempfile.mkdtemp(prefix=prefix, dir=RUN_OUTPUT_ROOT)
    return set_active_output_dir(run_dir)


def log_task_update(task_name: str, message: str, content: str | None = None):
    logger.info(f"[{task_name}] {message}")
    if content:
        logger.info(content.strip())


def write_text_file(filename: str, content: str):
    filepath = resolve_output_path(filename)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)


def write_binary_file(filename: str, content: bytes):
    filepath = resolve_output_path(filename)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "wb") as f:
        f.write(content)


def append_text_file(filename: str, content: str):
    filepath = resolve_output_path(filename)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "a", encoding="utf-8") as f:
        f.write(content)


def reset_text_file(filename: str, content: str = ""):
    filepath = resolve_output_path(filename)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)


def record_work_note(state: dict | None, actor: str, stage: str, details: str):
    filename = "agent_work_notes.txt"
    if state and state.get("work_notes_file"):
        filename = state["work_notes_file"]

    timestamp = datetime.now(UTC).isoformat()
    run_id = state.get("run_id", "no-run-id") if state else "no-run-id"
    note = (
        f"[{timestamp}] run={run_id} actor={actor} stage={stage}\n"
        f"{details.strip()}\n\n"
    )
    append_text_file(filename, note)
