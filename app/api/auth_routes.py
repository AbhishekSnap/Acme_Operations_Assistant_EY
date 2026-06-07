"""
Login helper endpoint: exchanges username/password for a Keycloak access token.
Exists purely for the demo UI — in production, use the Keycloak login page.
"""
import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from config import settings

router = APIRouter()


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/auth/token")
async def get_token(req: LoginRequest):
    token_url = (
        f"{settings.keycloak_url}/realms/{settings.keycloak_realm}"
        f"/protocol/openid-connect/token"
    )
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            token_url,
            data={
                "grant_type": "password",
                "client_id": settings.keycloak_client_id,
                "client_secret": settings.keycloak_client_secret,
                "username": req.username,
                "password": req.password,
                "scope": "openid",
            },
            timeout=15,
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return resp.json()
