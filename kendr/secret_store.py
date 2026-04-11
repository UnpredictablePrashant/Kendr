from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from urllib.parse import quote


_SECRET_LOCK = threading.Lock()
_SECRET_STORE_FILENAME = "secret_store.json"


def _kendr_home() -> Path:
    root = str(os.getenv("KENDR_HOME", "")).strip()
    if root:
        return Path(root).expanduser().resolve()
    return (Path.home() / ".kendr").expanduser().resolve()


def secret_store_path() -> Path:
    return _kendr_home() / _SECRET_STORE_FILENAME


def is_secret_ref(value: object) -> bool:
    return isinstance(value, str) and value.startswith("vault://")


def build_secret_ref(namespace: str, *parts: str) -> str:
    encoded = [quote(str(namespace or "").strip() or "default", safe="._-")]
    encoded.extend(quote(str(part or "").strip() or "default", safe="._-") for part in parts)
    return "vault://local/" + "/".join(encoded)


def _load_store_unlocked() -> dict:
    path = secret_store_path()
    if not path.exists():
        return {"version": 1, "secrets": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"version": 1, "secrets": {}}
    if not isinstance(payload, dict):
        return {"version": 1, "secrets": {}}
    secrets = payload.get("secrets", {})
    if not isinstance(secrets, dict):
        secrets = {}
    return {"version": 1, "secrets": secrets}


def _chmod_private(path: Path) -> None:
    try:
        os.chmod(path, 0o600)
    except Exception:
        pass


def _chmod_private_dir(path: Path) -> None:
    try:
        os.chmod(path, 0o700)
    except Exception:
        pass


def _write_store_unlocked(payload: dict) -> None:
    path = secret_store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    _chmod_private_dir(path.parent)
    fd, tmp_name = tempfile.mkstemp(prefix=".secret_store_", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        _chmod_private(Path(tmp_name))
        os.replace(tmp_name, path)
        _chmod_private(path)
    finally:
        if os.path.exists(tmp_name):
            try:
                os.remove(tmp_name)
            except Exception:
                pass


def put_secret(ref: str, value) -> str:
    if not is_secret_ref(ref):
        raise ValueError(f"Invalid secret ref: {ref!r}")
    with _SECRET_LOCK:
        payload = _load_store_unlocked()
        payload.setdefault("secrets", {})[ref] = value
        _write_store_unlocked(payload)
    return ref


def get_secret(ref: str, default=None):
    if not is_secret_ref(ref):
        return default
    with _SECRET_LOCK:
        payload = _load_store_unlocked()
        return payload.get("secrets", {}).get(ref, default)


def delete_secret(ref: str) -> bool:
    if not is_secret_ref(ref):
        return False
    with _SECRET_LOCK:
        payload = _load_store_unlocked()
        secrets = payload.get("secrets", {})
        if ref not in secrets:
            return False
        secrets.pop(ref, None)
        payload["secrets"] = secrets
        _write_store_unlocked(payload)
    return True
