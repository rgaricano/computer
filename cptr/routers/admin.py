"""Admin router for cptr. All endpoints require admin role."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional

from cptr.utils.config import AuthResult, check_access, hash_password, now_ms
from cptr.models import User, Auth, Config

router = APIRouter(prefix="/api/admin", tags=["admin"])

COOKIE_NAME = "cptr_session"


def require_admin(request: Request) -> AuthResult:
    """Extract auth from cookie, raise 403 if not admin."""
    token = request.cookies.get(COOKIE_NAME)
    client_host = request.client.host if request.client else "127.0.0.1"
    auth = check_access(client_host=client_host, jwt_token=token)
    if not auth or auth.role != "admin":
        raise HTTPException(403, "admin required")
    return auth


# ── Users ────────────────────────────────────────────────────


@router.get("/users")
async def list_users(request: Request):
    """List all users with their roles."""
    require_admin(request)
    return {"users": await User.list_all()}


@router.post("/users")
async def create_user(body: CreateUserRequest, request: Request):
    """Create a new user (admin only)."""
    require_admin(request)

    if not body.username or not body.username.strip():
        return JSONResponse({"error": "username required"}, 400)
    if not body.password or len(body.password.strip()) < 6:
        return JSONResponse({"error": "min 6 characters"}, 400)
    if body.role not in ("admin", "user", "pending"):
        return JSONResponse({"error": "role must be admin, user, or pending"}, 400)

    username = body.username.strip()
    if await Auth.username_exists(username):
        return JSONResponse({"error": "username taken"}, 409)

    user_id = await User.create(
        username=username,
        password_hash=hash_password(body.password.strip()),
        role=body.role,
        created_at=now_ms(),
    )
    return {"ok": True, "user_id": user_id}


@router.delete("/users/{user_id}")
async def delete_user(user_id: str, request: Request):
    """Delete a user. Cannot delete yourself."""
    auth = require_admin(request)
    if auth.user_id == user_id:
        return JSONResponse({"error": "cannot delete yourself"}, 400)
    await User.delete_user(user_id)
    return {"ok": True}


@router.put("/users/{user_id}/role")
async def update_role(user_id: str, body: RoleRequest, request: Request):
    """Update a user's role."""
    require_admin(request)
    if body.role not in ("admin", "user", "pending"):
        return JSONResponse({"error": "role must be admin, user, or pending"}, 400)
    if not await User.update_role(user_id, body.role):
        return JSONResponse({"error": "user not found"}, 404)
    return {"ok": True}


@router.put("/users/{user_id}/profile")
async def update_user_profile(user_id: str, body: UpdateUserProfileRequest, request: Request):
    """Update a user's display name (admin only)."""
    require_admin(request)
    await User.update_display_name(user_id, body.display_name)
    return {"ok": True, "display_name": body.display_name}


@router.put("/users/{user_id}/password")
async def reset_user_password(user_id: str, body: ResetPasswordRequest, request: Request):
    """Reset a user's password (admin only)."""
    require_admin(request)
    if not body.password or len(body.password.strip()) < 6:
        return JSONResponse({"error": "min 6 characters"}, 400)
    if not await Auth.update_password(user_id, hash_password(body.password.strip())):
        return JSONResponse({"error": "user not found"}, 404)
    return {"ok": True}


@router.put("/users/{user_id}/username")
async def update_username(user_id: str, body: UpdateUsernameRequest, request: Request):
    """Update a user's username (admin only)."""
    require_admin(request)
    if not body.username or not body.username.strip():
        return JSONResponse({"error": "username required"}, 400)
    if not await Auth.update_username(user_id, body.username.strip()):
        return JSONResponse({"error": "username taken or user not found"}, 400)
    return {"ok": True}


# ── Config ───────────────────────────────────────────────────


@router.get("/config")
async def get_all_config(request: Request):
    """Get all instance config."""
    require_admin(request)
    return {"config": await Config.get_all()}


@router.get("/config/{namespace}")
async def get_config_namespace(namespace: str, request: Request):
    """Get config keys for a namespace (e.g. 'auth' → all 'auth.*' keys)."""
    require_admin(request)
    return {"config": await Config.get_namespace(namespace)}


@router.put("/config")
async def put_config(body: ConfigUpdateRequest, request: Request):
    """Update config keys. Upserts each key."""
    require_admin(request)
    await Config.upsert(body.config)
    return {"ok": True}


# ── Connections ──────────────────────────────────────────────

from cptr.utils.crypto import encrypt_key, decrypt_key, mask_key
from cptr.utils.config import _get_jwt_secret
from cptr.routers.chat import invalidate_model_cache


async def _get_connections() -> list[dict]:
    """Get all connections from config store."""
    return await Config.get("chat.connections") or []


async def _save_connections(connections: list[dict]):
    """Save connections to config store."""
    await Config.upsert({"chat.connections": connections})


def _mask_connection(conn: dict) -> dict:
    """Return connection with masked API key (for list display)."""
    secret = _get_jwt_secret()
    masked = {**conn}
    if masked.get("api_key"):
        try:
            plain = decrypt_key(masked["api_key"], secret)
            masked["api_key"] = mask_key(plain)
        except Exception:
            masked["api_key"] = "****"
    return masked


@router.get("/connections")
async def list_connections(request: Request):
    """List all connections (API keys masked)."""
    require_admin(request)
    connections = await _get_connections()
    return {"connections": [_mask_connection(c) for c in connections]}


@router.post("/connections")
async def create_connection(body: CreateConnectionRequest, request: Request):
    """Add a new AI connection."""
    require_admin(request)
    import uuid as _uuid
    connections = await _get_connections()
    conn = {
        "id": str(_uuid.uuid4()),
        "name": body.name,
        "provider": body.provider,
        "api_type": body.api_type,  # "chat_completions" | "responses" (openai only)
        "prefix_id": body.prefix_id,
        "base_url": body.base_url,
        "api_key": encrypt_key(body.api_key, _get_jwt_secret()) if body.api_key else None,
        "enabled": body.enabled if body.enabled is not None else True,
        "data": {"models": body.models} if body.models else {},
    }
    connections.append(conn)
    await _save_connections(connections)
    invalidate_model_cache(request.app.state)
    return {"ok": True, "id": conn["id"]}


@router.put("/connections/{conn_id}")
async def update_connection(conn_id: str, body: UpdateConnectionRequest, request: Request):
    """Update an existing connection."""
    require_admin(request)
    connections = await _get_connections()
    conn = next((c for c in connections if c["id"] == conn_id), None)
    if not conn:
        raise HTTPException(404, "connection not found")

    if body.name is not None:
        conn["name"] = body.name
    if body.provider is not None:
        conn["provider"] = body.provider
    if body.api_type is not None:
        conn["api_type"] = body.api_type
    if body.prefix_id is not None:
        conn["prefix_id"] = body.prefix_id or None
    if body.base_url is not None:
        conn["base_url"] = body.base_url or None
    if body.api_key is not None and body.api_key != "":
        conn["api_key"] = encrypt_key(body.api_key, _get_jwt_secret())
    if body.enabled is not None:
        conn["enabled"] = body.enabled
    if body.models is not None:
        conn.setdefault("data", {})["models"] = body.models

    await _save_connections(connections)
    invalidate_model_cache(request.app.state)
    return {"ok": True}


@router.delete("/connections/{conn_id}")
async def delete_connection(conn_id: str, request: Request):
    """Delete a connection."""
    require_admin(request)
    connections = [c for c in await _get_connections() if c["id"] != conn_id]
    await _save_connections(connections)
    invalidate_model_cache(request.app.state)
    return {"ok": True}


@router.post("/connections/{conn_id}/verify")
async def verify_connection(conn_id: str, request: Request):
    """Test a connection by making a lightweight API call."""
    require_admin(request)
    connections = await _get_connections()
    conn = next((c for c in connections if c["id"] == conn_id), None)
    if not conn:
        raise HTTPException(404, "connection not found")

    secret = _get_jwt_secret()
    api_key = decrypt_key(conn.get("api_key", ""), secret) if conn.get("api_key") else None

    provider = conn.get("provider", "")
    base_url = conn.get("base_url")

    import httpx

    try:
        if provider == "anthropic":
            url = (base_url or "https://api.anthropic.com/v1") + "/messages"
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.post(url, headers={
                    "x-api-key": api_key or "",
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                }, json={"model": "claude-sonnet-4-20250514", "max_tokens": 1, "messages": [{"role": "user", "content": "hi"}]})
                if r.status_code in (200, 201):
                    return {"ok": True, "message": "Connected"}
                elif r.status_code == 401:
                    return JSONResponse({"ok": False, "message": "Invalid API key"}, 400)
                else:
                    return JSONResponse({"ok": False, "message": f"API returned {r.status_code}"}, 400)

        elif provider == "openai":
            url = (base_url or "https://api.openai.com/v1") + "/models"
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(url, headers={"Authorization": f"Bearer {api_key or ''}"})
                if r.status_code == 200:
                    return {"ok": True, "message": "Connected"}
                elif r.status_code == 401:
                    return JSONResponse({"ok": False, "message": "Invalid API key"}, 400)
                else:
                    return JSONResponse({"ok": False, "message": f"API returned {r.status_code}"}, 400)

        else:
            return JSONResponse({"ok": False, "message": f"Unknown provider: {provider}"}, 400)

    except httpx.TimeoutException:
        return JSONResponse({"ok": False, "message": "Connection timed out"}, 400)
    except Exception as e:
        return JSONResponse({"ok": False, "message": str(e)}, 400)


# ── Request Models ───────────────────────────────────────────


class CreateUserRequest(BaseModel):
    username: str
    password: str
    role: str = "user"


class RoleRequest(BaseModel):
    role: str


class UpdateUserProfileRequest(BaseModel):
    display_name: Optional[str] = None


class ResetPasswordRequest(BaseModel):
    password: str


class UpdateUsernameRequest(BaseModel):
    username: str


class ConfigUpdateRequest(BaseModel):
    config: dict


class CreateConnectionRequest(BaseModel):
    name: str
    provider: str  # "anthropic" | "openai"
    api_type: str = "chat_completions"  # "chat_completions" | "responses" (openai only)
    prefix_id: Optional[str] = None  # e.g. "openrouter" → "openrouter/model-id"
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    enabled: Optional[bool] = None  # defaults to True in handler
    models: Optional[list[str]] = None


class UpdateConnectionRequest(BaseModel):
    name: Optional[str] = None
    provider: Optional[str] = None
    api_type: Optional[str] = None
    prefix_id: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    enabled: Optional[bool] = None
    models: Optional[list[str]] = None
