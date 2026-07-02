from __future__ import annotations

from fastapi import APIRouter, Request, Response
from gabriel.api.auth import (
    DEV_PRINCIPALS,
    DevLoginRequest,
    dev_login as perform_dev_login,
    get_session as read_session,
)

router = APIRouter(prefix="/auth", tags=["Auth"])

# ── Dev Identity Provider ──────────────────────────────────────────────────

@router.get("/dev/principals")
async def list_dev_principals():
    return DEV_PRINCIPALS

@router.post("/dev/login")
async def login_dev(body: DevLoginRequest, response: Response):
    return await perform_dev_login(body, response)

@router.get("/session")
async def get_current_session(request: Request):
    return await read_session(request)

@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("gabriel_session")
    return {"ok": True}