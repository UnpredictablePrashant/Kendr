from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from urllib.parse import quote


_SECRET_LOCK = threading.Lock()
_SECRET_BACKEND_LOCK = threading.Lock()
_SECRET_STORE_FILENAME = "secret_store.json"
_SECRET_BACKEND_ENV = "KENDR_SECRET_BACKEND"
_SECRET_BACKEND: "_SecretBackend | None" = None
_OS_SECRET_LABEL = "Kendr Secret"
_SECRET_MISSING = object()


def _kendr_home() -> Path:
    root = str(os.getenv("KENDR_HOME", "")).strip()
    if root:
        return Path(root).expanduser().resolve()
    return (Path.home() / ".kendr").expanduser().resolve()


def secret_store_path() -> Path:
    # Legacy file-backed store retained for migration/fallback.
    return _kendr_home() / _SECRET_STORE_FILENAME


def is_secret_ref(value: object) -> bool:
    return isinstance(value, str) and value.startswith("vault://")


def build_secret_ref(namespace: str, *parts: str) -> str:
    encoded = [quote(str(namespace or "").strip() or "default", safe="._-")]
    encoded.extend(quote(str(part or "").strip() or "default", safe="._-") for part in parts)
    return "vault://local/" + "/".join(encoded)


def _serialize_secret_payload(value) -> str:
    payload = {
        "version": 1,
        "encoding": "json",
        "value": value,
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _deserialize_secret_payload(raw: str):
    text = str(raw or "")
    if not text:
        return ""
    try:
        payload = json.loads(text)
    except Exception:
        return text
    if not isinstance(payload, dict):
        return text
    if int(payload.get("version", 0) or 0) != 1:
        return text
    if str(payload.get("encoding", "") or "").strip().lower() != "json":
        return text
    return payload.get("value")


def _load_legacy_store_unlocked() -> dict:
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


def _write_legacy_store_unlocked(payload: dict) -> None:
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


def _legacy_get_secret_unlocked(ref: str):
    payload = _load_legacy_store_unlocked()
    return payload.get("secrets", {}).get(ref, _SECRET_MISSING)


def _legacy_put_secret_unlocked(ref: str, value) -> None:
    payload = _load_legacy_store_unlocked()
    payload.setdefault("secrets", {})[ref] = value
    _write_legacy_store_unlocked(payload)


def _legacy_delete_secret_unlocked(ref: str) -> bool:
    payload = _load_legacy_store_unlocked()
    secrets = payload.get("secrets", {})
    if ref not in secrets:
        return False
    secrets.pop(ref, None)
    payload["secrets"] = secrets
    if secrets:
        _write_legacy_store_unlocked(payload)
    else:
        path = secret_store_path()
        try:
            if path.exists():
                path.unlink()
        except Exception:
            _write_legacy_store_unlocked(payload)
    return True


class _SecretBackend:
    name = "unknown"

    def put(self, ref: str, value) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    def get(self, ref: str):  # pragma: no cover - interface
        raise NotImplementedError

    def delete(self, ref: str) -> bool:  # pragma: no cover - interface
        raise NotImplementedError


class _LegacyFileSecretBackend(_SecretBackend):
    name = "file"

    def put(self, ref: str, value) -> None:
        _legacy_put_secret_unlocked(ref, value)

    def get(self, ref: str):
        return _legacy_get_secret_unlocked(ref)

    def delete(self, ref: str) -> bool:
        return _legacy_delete_secret_unlocked(ref)


class _SerializedSecretBackend(_SecretBackend):
    def put(self, ref: str, value) -> None:
        self._put_text(ref, _serialize_secret_payload(value))

    def get(self, ref: str):
        raw = self._get_text(ref)
        if raw is _SECRET_MISSING:
            return _SECRET_MISSING
        return _deserialize_secret_payload(str(raw or ""))

    def delete(self, ref: str) -> bool:
        return self._delete_text(ref)

    def _put_text(self, ref: str, payload: str) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    def _get_text(self, ref: str):  # pragma: no cover - interface
        raise NotImplementedError

    def _delete_text(self, ref: str) -> bool:  # pragma: no cover - interface
        raise NotImplementedError


class _MacOSKeychainBackend(_SerializedSecretBackend):
    name = "macos-keychain"

    def _service_name(self) -> str:
        return "com.kendr.desktop"

    def _account_name(self, ref: str) -> str:
        return ref

    def _put_text(self, ref: str, payload: str) -> None:
        subprocess.run(
            [
                "security",
                "add-generic-password",
                "-U",
                "-a",
                self._account_name(ref),
                "-s",
                self._service_name(),
                "-l",
                _OS_SECRET_LABEL,
                "-w",
                payload,
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )

    def _get_text(self, ref: str):
        result = subprocess.run(
            [
                "security",
                "find-generic-password",
                "-a",
                self._account_name(ref),
                "-s",
                self._service_name(),
                "-w",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if result.returncode != 0:
            return _SECRET_MISSING
        return result.stdout

    def _delete_text(self, ref: str) -> bool:
        result = subprocess.run(
            [
                "security",
                "delete-generic-password",
                "-a",
                self._account_name(ref),
                "-s",
                self._service_name(),
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return result.returncode == 0


class _LinuxSecretToolBackend(_SerializedSecretBackend):
    name = "linux-secret-tool"

    def _attributes(self, ref: str) -> list[str]:
        return ["service", "kendr", "secret_ref", ref]

    def _put_text(self, ref: str, payload: str) -> None:
        subprocess.run(
            ["secret-tool", "store", "--label", _OS_SECRET_LABEL, *self._attributes(ref)],
            input=payload,
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )

    def _get_text(self, ref: str):
        result = subprocess.run(
            ["secret-tool", "lookup", *self._attributes(ref)],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if result.returncode != 0:
            return _SECRET_MISSING
        output = result.stdout
        return output.rstrip("\n")

    def _delete_text(self, ref: str) -> bool:
        result = subprocess.run(
            ["secret-tool", "clear", *self._attributes(ref)],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return result.returncode == 0


if sys.platform == "win32":  # pragma: no cover - Windows-only backend
    import ctypes
    from ctypes import wintypes

    ERROR_NOT_FOUND = 1168
    CRED_PERSIST_LOCAL_MACHINE = 2
    CRED_TYPE_GENERIC = 1
    LPBYTE = ctypes.POINTER(wintypes.BYTE)

    class FILETIME(ctypes.Structure):
        _fields_ = [("dwLowDateTime", wintypes.DWORD), ("dwHighDateTime", wintypes.DWORD)]

    class CREDENTIALW(ctypes.Structure):
        _fields_ = [
            ("Flags", wintypes.DWORD),
            ("Type", wintypes.DWORD),
            ("TargetName", wintypes.LPWSTR),
            ("Comment", wintypes.LPWSTR),
            ("LastWritten", FILETIME),
            ("CredentialBlobSize", wintypes.DWORD),
            ("CredentialBlob", LPBYTE),
            ("Persist", wintypes.DWORD),
            ("AttributeCount", wintypes.DWORD),
            ("Attributes", wintypes.LPVOID),
            ("TargetAlias", wintypes.LPWSTR),
            ("UserName", wintypes.LPWSTR),
        ]

    _CredWriteW = ctypes.windll.advapi32.CredWriteW
    _CredWriteW.argtypes = [ctypes.POINTER(CREDENTIALW), wintypes.DWORD]
    _CredWriteW.restype = wintypes.BOOL

    _CredReadW = ctypes.windll.advapi32.CredReadW
    _CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(ctypes.POINTER(CREDENTIALW))]
    _CredReadW.restype = wintypes.BOOL

    _CredDeleteW = ctypes.windll.advapi32.CredDeleteW
    _CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
    _CredDeleteW.restype = wintypes.BOOL

    _CredFree = ctypes.windll.advapi32.CredFree
    _CredFree.argtypes = [wintypes.LPVOID]
    _CredFree.restype = None


class _WindowsCredentialBackend(_SerializedSecretBackend):  # pragma: no cover - Windows-only backend
    name = "windows-credential-manager"

    def _target_name(self, ref: str) -> str:
        return f"Kendr:{ref}"

    def _put_text(self, ref: str, payload: str) -> None:
        blob = payload.encode("utf-8")
        buffer = ctypes.create_string_buffer(blob)
        credential = CREDENTIALW()
        credential.Type = CRED_TYPE_GENERIC
        credential.TargetName = self._target_name(ref)
        credential.CredentialBlobSize = len(blob)
        credential.CredentialBlob = ctypes.cast(buffer, LPBYTE)
        credential.Persist = CRED_PERSIST_LOCAL_MACHINE
        credential.UserName = ref
        if not _CredWriteW(ctypes.byref(credential), 0):
            raise OSError(ctypes.get_last_error(), "CredWriteW failed")

    def _get_text(self, ref: str):
        credential_ptr = ctypes.POINTER(CREDENTIALW)()
        if not _CredReadW(self._target_name(ref), CRED_TYPE_GENERIC, 0, ctypes.byref(credential_ptr)):
            if ctypes.get_last_error() == ERROR_NOT_FOUND:
                return _SECRET_MISSING
            raise OSError(ctypes.get_last_error(), "CredReadW failed")
        try:
            credential = credential_ptr.contents
            if not credential.CredentialBlob or not credential.CredentialBlobSize:
                return ""
            return ctypes.string_at(credential.CredentialBlob, credential.CredentialBlobSize).decode("utf-8")
        finally:
            _CredFree(credential_ptr)

    def _delete_text(self, ref: str) -> bool:
        if _CredDeleteW(self._target_name(ref), CRED_TYPE_GENERIC, 0):
            return True
        if ctypes.get_last_error() == ERROR_NOT_FOUND:
            return False
        raise OSError(ctypes.get_last_error(), "CredDeleteW failed")


def _build_secret_backend() -> _SecretBackend:
    override = str(os.getenv(_SECRET_BACKEND_ENV, "") or "").strip().lower()
    if override in {"file", "legacy"}:
        return _LegacyFileSecretBackend()

    if override in {"windows", "wincred"} and sys.platform == "win32":
        return _WindowsCredentialBackend()
    if override in {"macos", "keychain"} and sys.platform == "darwin":
        return _MacOSKeychainBackend()
    if override in {"linux", "secret-tool", "secret_tool"}:
        if shutil.which("secret-tool"):
            return _LinuxSecretToolBackend()
        return _LegacyFileSecretBackend()

    if sys.platform == "win32":
        return _WindowsCredentialBackend()
    if sys.platform == "darwin" and shutil.which("security"):
        return _MacOSKeychainBackend()
    if shutil.which("secret-tool"):
        return _LinuxSecretToolBackend()
    return _LegacyFileSecretBackend()


def _get_secret_backend() -> _SecretBackend:
    global _SECRET_BACKEND
    if _SECRET_BACKEND is not None:
        return _SECRET_BACKEND
    with _SECRET_BACKEND_LOCK:
        if _SECRET_BACKEND is None:
            _SECRET_BACKEND = _build_secret_backend()
    return _SECRET_BACKEND


def _reset_secret_backend_cache() -> None:
    global _SECRET_BACKEND
    with _SECRET_BACKEND_LOCK:
        _SECRET_BACKEND = None


def _put_with_backend(ref: str, value) -> str:
    backend = _get_secret_backend()
    try:
        backend.put(ref, value)
        if backend.name != "file":
            _legacy_delete_secret_unlocked(ref)
        return ref
    except Exception:
        file_backend = _LegacyFileSecretBackend()
        file_backend.put(ref, value)
        return ref


def put_secret(ref: str, value) -> str:
    if not is_secret_ref(ref):
        raise ValueError(f"Invalid secret ref: {ref!r}")
    with _SECRET_LOCK:
        return _put_with_backend(ref, value)


def get_secret(ref: str, default=None):
    if not is_secret_ref(ref):
        return default
    with _SECRET_LOCK:
        backend = _get_secret_backend()
        try:
            value = backend.get(ref)
        except Exception:
            value = _SECRET_MISSING
        if value is not _SECRET_MISSING:
            return value
        legacy_value = _legacy_get_secret_unlocked(ref)
        if legacy_value is _SECRET_MISSING:
            return default
        if backend.name != "file":
            try:
                backend.put(ref, legacy_value)
                _legacy_delete_secret_unlocked(ref)
            except Exception:
                pass
        return legacy_value


def delete_secret(ref: str) -> bool:
    if not is_secret_ref(ref):
        return False
    deleted = False
    with _SECRET_LOCK:
        backend = _get_secret_backend()
        try:
            deleted = bool(backend.delete(ref))
        except Exception:
            deleted = False
        if backend.name != "file":
            deleted = bool(_legacy_delete_secret_unlocked(ref) or deleted)
    return deleted
