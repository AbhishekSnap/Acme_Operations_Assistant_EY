"""
Keycloak JWT validation and RBAC helpers.
We fetch the realm's public key from Keycloak's JWKS endpoint and verify
every incoming bearer token locally - no introspection round-trip per request.
"""
import httpx
from jose import jwt, JWTError
from fastapi import HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from config import settings

_bearer = HTTPBearer()

ROLE_PERMISSIONS = {
    "sales_user": {"read"},
    "support_user": {"read", "update_issue"},
    "admin": {"read", "update_issue", "create_next_action"},
}


async def _get_jwks() -> dict:
    url = f"{settings.keycloak_url}/realms/{settings.keycloak_realm}/protocol/openid-connect/certs"
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, timeout=10)
        resp.raise_for_status()
        return resp.json()


async def decode_token(token: str) -> dict:
    jwks = await _get_jwks()
    try:
        payload = jwt.decode(
            token,
            jwks,
            algorithms=["RS256"],
            options={"verify_aud": False},
        )
        return payload
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {exc}",
        )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
) -> dict:
    payload = await decode_token(credentials.credentials)
    roles = payload.get("realm_access", {}).get("roles", [])
    known = [r for r in roles if r in ROLE_PERMISSIONS]
    if not known:
        raise HTTPException(status_code=403, detail="No recognised role on token")
    # Aggregate permissions across all roles the user holds
    perms: set[str] = set()
    for r in known:
        perms |= ROLE_PERMISSIONS[r]
    return {
        "sub": payload.get("sub"),
        "username": payload.get("preferred_username", payload.get("sub")),
        "email": payload.get("email"),
        "roles": known,
        "permissions": perms,
    }


def require_permission(permission: str):
    async def _check(user: dict = Security(get_current_user)):
        if permission not in user["permissions"]:
            raise HTTPException(
                status_code=403,
                detail=f"Role {user['roles']} does not have '{permission}' permission",
            )
        return user
    return _check
