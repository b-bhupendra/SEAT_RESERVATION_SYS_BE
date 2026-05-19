from fastapi import Depends, HTTPException, status, Response
from fastapi.security import OAuth2PasswordBearer
from .auth_utils import decode_access_token
from typing import List
from ..db_core import get_db
from sqlalchemy.orm import Session

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login")

ROLE_PERMISSIONS_CACHE = {}

def get_allowed_orgs(user_role: str, db: Session) -> List[str]:
    """Helper to extract allowed organizations for a role using the cache."""
    if user_role not in ROLE_PERMISSIONS_CACHE:
        from .model_users import DBRole
        role_record = db.query(DBRole).filter(DBRole.name == user_role).first()
        if not role_record:
            return []
        ROLE_PERMISSIONS_CACHE[user_role] = [p.strip() for p in role_record.permissions.split(",")]
    
    permissions = ROLE_PERMISSIONS_CACHE[user_role]
    if "*" in permissions or "all" in permissions or "org:all" in permissions or user_role == "admin":
        return ["*"]
        
    allowed = []
    for p in permissions:
        if p.startswith("org:"):
            allowed.append(p[4:])
    return allowed

def RoleChecker(allowed_roles: List[str]):
    """
    Dependency to check if the user has the required role by decoding the JWT access token.
    The expected header is 'Authorization: Bearer <token>'.
    """
    def check_role(token: str = Depends(oauth2_scheme)):
        payload = decode_access_token(token)
        if not payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        user_role = payload.get("role")
        if user_role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user_role}' does not have permission to perform this action."
            )
        return payload # Returns the full payload (sub, role, exp) if needed
        
    return check_role

def PermissionChecker(required_permission: str):
    """
    Dependency to check if the user has the required fine-grained permission/ability.
    Queries the database using the decoded user role to verify the role's assigned permissions.
    """
    def check_permission(
        response: Response,
        token: str = Depends(oauth2_scheme),
        db = Depends(get_db)
    ):
        # 1. Intercept during active Maintenance Lock / Ability configuration updates
        from api.settings.model_settings import DBSetting
        config_lock = db.query(DBSetting).filter(DBSetting.key == "is_updating_config").first()
        if config_lock and config_lock.value == "true":
            ROLE_PERMISSIONS_CACHE.clear()
            response.headers["X-Clear-Cache"] = "true"
            response.headers["X-Refresh-Capabilities"] = "true"
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="System under administrative updates. Refreshing user permissions."
            )

        payload = decode_access_token(token)
        if not payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        user_role = payload.get("role")
        if not user_role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Missing role payload"
            )
            
        if user_role not in ROLE_PERMISSIONS_CACHE:
            from .model_users import DBRole
            role_record = db.query(DBRole).filter(DBRole.name == user_role).first()
            if not role_record:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Role '{user_role}' is not configured in the system."
                )
            ROLE_PERMISSIONS_CACHE[user_role] = [p.strip() for p in role_record.permissions.split(",")]
            
        permissions_list = ROLE_PERMISSIONS_CACHE[user_role]
        if "*" in permissions_list or "all" in permissions_list or required_permission in permissions_list:
            return payload
            
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"User role '{user_role}' does not possess the required ability '{required_permission}'."
        )
        
    return check_permission
