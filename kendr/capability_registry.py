"""Capability Registry Service (Phase 0 skeleton).

Service wrapper over persistence helpers for unified capability management.
This intentionally focuses on stable CRUD + state transitions and does not yet
replace runtime routing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from kendr.persistence import (
    add_capability_relation,
    create_auth_profile,
    create_capability,
    create_policy_profile,
    get_capability,
    insert_capability_audit_event,
    list_auth_profiles,
    list_capability_audit_events,
    list_capability_health_runs,
    list_capabilities,
    list_policy_profiles,
    set_capability_health,
    update_capability,
)


@dataclass
class CapabilityRegistryService:
    db_path: str = ""
    _ALLOWED_TYPES = {"skill", "mcp_server", "api", "agent", "tool"}
    _ALLOWED_STATUS = {"draft", "verified", "active", "disabled", "error", "deprecated"}
    _ALLOWED_VISIBILITY = {"private", "workspace", "org"}
    _ALLOWED_HEALTH_STATUS = {"unknown", "healthy", "degraded", "down"}
    _STATUS_TRANSITIONS = {
        "draft": {"verified", "active", "disabled", "error"},
        "verified": {"active", "disabled", "error"},
        "active": {"disabled", "deprecated", "error"},
        "disabled": {"active", "deprecated", "error"},
        "error": {"draft", "verified", "disabled"},
        "deprecated": {"disabled"},
    }

    def _validate_type(self, capability_type: str) -> str:
        value = str(capability_type or "").strip().lower()
        if value not in self._ALLOWED_TYPES:
            raise ValueError(f"Unsupported capability type: {capability_type!r}")
        return value

    def _validate_status(self, status: str) -> str:
        value = str(status or "").strip().lower()
        if value not in self._ALLOWED_STATUS:
            raise ValueError(f"Unsupported capability status: {status!r}")
        return value

    def _validate_visibility(self, visibility: str) -> str:
        value = str(visibility or "").strip().lower()
        if value not in self._ALLOWED_VISIBILITY:
            raise ValueError(f"Unsupported capability visibility: {visibility!r}")
        return value

    def _assert_transition(self, current_status: str, next_status: str) -> None:
        current = self._validate_status(current_status)
        nxt = self._validate_status(next_status)
        if current == nxt:
            return
        allowed = self._STATUS_TRANSITIONS.get(current, set())
        if nxt not in allowed:
            raise ValueError(f"Invalid status transition: {current} -> {nxt}")

    def _validate_health_status(self, status: str) -> str:
        value = str(status or "").strip().lower()
        if value not in self._ALLOWED_HEALTH_STATUS:
            raise ValueError(f"Unsupported health status: {status!r}")
        return value

    def create(
        self,
        *,
        workspace_id: str,
        capability_type: str,
        key: str,
        name: str,
        description: str,
        owner_user_id: str,
        visibility: str = "workspace",
        status: str = "draft",
        version: int = 1,
        tags: list[str] | None = None,
        metadata: dict | None = None,
        schema_in: dict | None = None,
        schema_out: dict | None = None,
        auth_profile_id: str = "",
        policy_profile_id: str = "",
    ) -> dict:
        capability_type = self._validate_type(capability_type)
        status = self._validate_status(status)
        visibility = self._validate_visibility(visibility)
        capability = create_capability(
            workspace_id=workspace_id,
            capability_type=capability_type,
            key=key,
            name=name,
            description=description,
            owner_user_id=owner_user_id,
            visibility=visibility,
            status=status,
            version=version,
            tags=tags,
            metadata=metadata,
            schema_in=schema_in,
            schema_out=schema_out,
            auth_profile_id=auth_profile_id,
            policy_profile_id=policy_profile_id,
            db_path=self.db_path,
        )
        self.audit(
            workspace_id=workspace_id,
            actor_user_id=owner_user_id,
            action="capability.create",
            capability_id=capability.get("id", ""),
            payload={"type": capability_type, "key": key, "name": name},
        )
        return capability

    def get(self, capability_id: str) -> dict | None:
        return get_capability(capability_id, db_path=self.db_path)

    def list(
        self,
        *,
        workspace_id: str = "",
        capability_type: str = "",
        status: str = "",
        visibility: str = "",
        search: str = "",
        limit: int = 200,
    ) -> list[dict]:
        return list_capabilities(
            workspace_id=workspace_id,
            capability_type=capability_type,
            status=status,
            visibility=visibility,
            search=search,
            limit=limit,
            db_path=self.db_path,
        )

    def update(
        self,
        capability_id: str,
        *,
        actor_user_id: str,
        workspace_id: str,
        **updates: Any,
    ) -> dict | None:
        current = self.get(capability_id)
        if not current:
            return None
        if "status" in updates and updates.get("status") is not None:
            next_status = self._validate_status(str(updates.get("status", "")))
            self._assert_transition(str(current.get("status", "draft")), next_status)
            updates["status"] = next_status
        if "visibility" in updates and updates.get("visibility") is not None:
            updates["visibility"] = self._validate_visibility(str(updates.get("visibility", "")))
        result = update_capability(capability_id, db_path=self.db_path, **updates)
        if result:
            self.audit(
                workspace_id=workspace_id,
                actor_user_id=actor_user_id,
                action="capability.update",
                capability_id=capability_id,
                payload={"updates": sorted(updates.keys())},
            )
        return result

    def publish(self, capability_id: str, *, workspace_id: str, actor_user_id: str) -> dict | None:
        return self.update(
            capability_id,
            actor_user_id=actor_user_id,
            workspace_id=workspace_id,
            status="active",
        )

    def verify(self, capability_id: str, *, workspace_id: str, actor_user_id: str) -> dict | None:
        return self.update(
            capability_id,
            actor_user_id=actor_user_id,
            workspace_id=workspace_id,
            status="verified",
        )

    def disable(self, capability_id: str, *, workspace_id: str, actor_user_id: str) -> dict | None:
        return self.update(
            capability_id,
            actor_user_id=actor_user_id,
            workspace_id=workspace_id,
            status="disabled",
        )

    def record_health(
        self,
        capability_id: str,
        *,
        workspace_id: str,
        status: str,
        actor_user_id: str = "system:health",
        latency_ms: int | None = None,
        error: str = "",
    ) -> dict | None:
        health_status = self._validate_health_status(status)
        set_capability_health(
            capability_id,
            workspace_id=workspace_id,
            status=health_status,
            latency_ms=latency_ms,
            error=error,
            db_path=self.db_path,
        )
        self.audit(
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            action="capability.health",
            capability_id=capability_id,
            payload={
                "status": health_status,
                "latency_ms": latency_ms,
                "error": error,
            },
        )
        return self.get(capability_id)

    def link(
        self,
        *,
        workspace_id: str,
        parent_capability_id: str,
        child_capability_id: str,
        relation_type: str,
        actor_user_id: str,
    ) -> dict:
        relation = add_capability_relation(
            workspace_id=workspace_id,
            parent_capability_id=parent_capability_id,
            child_capability_id=child_capability_id,
            relation_type=relation_type,
            db_path=self.db_path,
        )
        self.audit(
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            action="capability.link",
            capability_id=parent_capability_id,
            payload={
                "child_capability_id": child_capability_id,
                "relation_type": relation_type,
            },
        )
        return relation

    def create_auth_profile(
        self,
        *,
        workspace_id: str,
        auth_type: str,
        provider: str,
        secret_ref: str,
        scopes: list[str] | None = None,
        metadata: dict | None = None,
    ) -> dict:
        return create_auth_profile(
            workspace_id=workspace_id,
            auth_type=auth_type,
            provider=provider,
            secret_ref=secret_ref,
            scopes=scopes,
            metadata=metadata,
            db_path=self.db_path,
        )

    def list_auth_profiles(
        self,
        *,
        workspace_id: str,
        provider: str = "",
        limit: int = 200,
    ) -> list[dict]:
        return list_auth_profiles(
            workspace_id=workspace_id,
            provider=provider,
            limit=limit,
            db_path=self.db_path,
        )

    def create_policy_profile(
        self,
        *,
        workspace_id: str,
        name: str,
        rules: dict,
    ) -> dict:
        return create_policy_profile(
            workspace_id=workspace_id,
            name=name,
            rules=rules,
            db_path=self.db_path,
        )

    def list_policy_profiles(
        self,
        *,
        workspace_id: str,
        limit: int = 200,
    ) -> list[dict]:
        return list_policy_profiles(
            workspace_id=workspace_id,
            limit=limit,
            db_path=self.db_path,
        )

    def list_health_runs(
        self,
        *,
        workspace_id: str,
        capability_id: str = "",
        limit: int = 50,
    ) -> list[dict]:
        return list_capability_health_runs(
            workspace_id=workspace_id,
            capability_id=capability_id,
            limit=limit,
            db_path=self.db_path,
        )

    def list_audit_events(
        self,
        *,
        workspace_id: str,
        capability_id: str = "",
        action: str = "",
        limit: int = 100,
    ) -> list[dict]:
        return list_capability_audit_events(
            workspace_id=workspace_id,
            capability_id=capability_id,
            action=action,
            limit=limit,
            db_path=self.db_path,
        )

    def audit(
        self,
        *,
        workspace_id: str,
        actor_user_id: str,
        action: str,
        payload: dict | None = None,
        capability_id: str = "",
    ) -> dict:
        return insert_capability_audit_event(
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            action=action,
            payload=payload,
            capability_id=capability_id,
            db_path=self.db_path,
        )
