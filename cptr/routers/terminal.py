"""Terminal API - WebSocket and REST endpoints for PTY sessions."""

from __future__ import annotations

import asyncio
import logging
import os
import select
from typing import List, Optional

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from cptr.utils.config import check_access, get_auth_mode, get_user_uid_gid, AuthMode
from cptr.utils.terminal import manager, IS_WINDOWS

logger = logging.getLogger("cptr.terminal")

router = APIRouter(prefix="/api/terminal", tags=["terminal"])


class CreateSessionRequest(BaseModel):
    rows: int = 24
    cols: int = 80
    cwd: Optional[str] = None


class SessionInfo(BaseModel):
    session_id: str
    cwd: str


@router.post("", response_model=SessionInfo)
async def create_session(req: CreateSessionRequest):
    """Create a new terminal session."""
    logger.info(f"Creating terminal session: cwd={req.cwd}, rows={req.rows}, cols={req.cols}")
    session = manager.create(rows=req.rows, cols=req.cols, cwd=req.cwd)
    logger.info(f"Created session {session.session_id} at {session.cwd}, fd={session._fd}, alive={session.is_alive()}")
    return SessionInfo(session_id=session.session_id, cwd=session.cwd)


@router.get("", response_model=List[SessionInfo])
async def list_sessions():
    """List active terminal sessions."""
    sessions = manager.list_sessions()
    logger.debug(f"Listing sessions: {len(sessions)} active")
    return [SessionInfo(**s) for s in sessions]


@router.delete("/{session_id}")
async def delete_session(session_id: str):
    """Kill a terminal session."""
    logger.info(f"Deleting session {session_id}")
    if not manager.close(session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    return {"status": "closed"}


@router.websocket("/{session_id}/ws")
async def terminal_ws(websocket: WebSocket, session_id: str):
    """WebSocket endpoint for terminal I/O.

    Binary protocol (same as ttyd/GoTTY):
    Client → Server:  byte[0] = type, byte[1:] = payload
        0x00 + raw input bytes
        0x02 + JSON resize {"cols": N, "rows": N}
    Server → Client:  raw PTY output bytes (no prefix)
    """
    # Auth check for WebSocket (middleware doesn't cover WebSocket upgrades)
    client_host = websocket.client.host if websocket.client else "127.0.0.1"
    token = websocket.cookies.get("cptr_session") or websocket.query_params.get("token")
    auth = check_access(client_host=client_host, jwt_token=token)
    if auth is None:
        await websocket.close(code=4001, reason="unauthorized")
        return

    session = manager.get(session_id)
    if not session:
        logger.warning(f"WebSocket: session {session_id} not found")
        await websocket.close(code=4004, reason="Session not found")
        return

    await websocket.accept()
    logger.info(f"WebSocket connected for session {session_id}, fd={session._fd}, alive={session.is_alive()}")

    # Replay scrollback buffer so reconnecting clients see history
    scrollback = session.get_scrollback()
    if scrollback:
        logger.info(f"Replaying {len(scrollback)} bytes of scrollback")
        await websocket.send_bytes(scrollback)

    # Message type constants (must match frontend)
    MSG_INPUT = 0
    MSG_RESIZE = 2

    async def read_pty():
        """Read from PTY and send to WebSocket.

        Adaptive loop: reads continuously when data is available (no sleep),
        only yields briefly when the PTY is idle. Batches consecutive reads
        into a single WebSocket message to reduce frame overhead.
        """
        try:
            while True:
                if not session.is_alive():
                    logger.info(f"Session {session_id} process died, stopping read loop")
                    break
                try:
                    if IS_WINDOWS:
                        data = session.read(16384)
                        if data:
                            await websocket.send_bytes(data)
                        else:
                            await asyncio.sleep(0.005)
                    else:
                        r, _, _ = select.select([session._fd], [], [], 0)
                        if r:
                            # Data available — read and batch without sleeping
                            chunks = []
                            total = 0
                            while total < 65536:
                                r2, _, _ = select.select([session._fd], [], [], 0)
                                if not r2:
                                    break
                                data = session.read(16384)
                                if not data:
                                    break
                                chunks.append(data)
                                total += len(data)
                            if chunks:
                                await websocket.send_bytes(b"".join(chunks))
                        else:
                            # No data — yield to event loop briefly
                            await asyncio.sleep(0.005)
                except (OSError, IOError) as e:
                    logger.error(f"PTY read error for {session_id}: {e}")
                    break
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"read_pty unexpected error for {session_id}: {e}")

    read_task = asyncio.create_task(read_pty())

    try:
        while True:
            raw = await websocket.receive_bytes()
            if len(raw) < 1:
                continue

            msg_type = raw[0]
            payload = raw[1:]

            if msg_type == MSG_INPUT:
                session.write(payload)
            elif msg_type == MSG_RESIZE:
                import json as _json
                try:
                    resize_data = _json.loads(payload)
                    cols = resize_data.get("cols", 80)
                    rows = resize_data.get("rows", 24)
                    logger.debug(f"Resize {session_id}: {cols}x{rows}")
                    session.resize(rows, cols)
                except (ValueError, KeyError) as e:
                    logger.warning(f"Invalid resize payload for {session_id}: {e}")
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for {session_id}")
    except Exception as e:
        logger.error(f"WebSocket error for {session_id}: {e}")
    finally:
        read_task.cancel()
        try:
            await read_task
        except asyncio.CancelledError:
            pass

