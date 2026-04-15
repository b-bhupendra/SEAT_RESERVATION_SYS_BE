from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from .auth_utils import decode_access_token
from typing import List

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login")

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
