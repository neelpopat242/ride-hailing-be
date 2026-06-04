import jwt
from flask import request

from app.config import Config
from app.exceptions import APIException


class JWTAuth:
    """
    Single JWT auth handler for both riders and drivers.

    Expected token payload:
        {
            "user_id": "<uuid>",
            "role":    "rider" | "driver"
        }

    Usage:
        actor = JWTAuth.authenticate(allowed_roles=["driver"])
        actor["user_id"]  # rider or driver id
        actor["role"]     # "rider" or "driver"
    """

    @staticmethod
    def authenticate(allowed_roles: list[str] | None = None) -> dict:
        raw = request.headers.get("Authorization", "")
        token = raw.removeprefix("Bearer ").strip()

        if not token:
            raise APIException("UNAUTHORIZED", "Authentication token is required.", 401)

        try:
            payload = jwt.decode(
                token,
                Config.JWT_SECRET_KEY,
                algorithms=[Config.JWT_ALGORITHM],
            )
        except jwt.ExpiredSignatureError:
            raise APIException("TOKEN_EXPIRED", "Token has expired.", 401)
        except jwt.InvalidTokenError:
            raise APIException("INVALID_TOKEN", "Invalid or malformed token.", 401)

        user_id = payload.get("user_id")
        role = payload.get("role")

        if not user_id or not role:
            raise APIException("INVALID_TOKEN", "Token must contain user_id and role.", 401)

        if allowed_roles and role not in allowed_roles:
            raise APIException(
                "FORBIDDEN",
                f"This action requires one of the following roles: {', '.join(allowed_roles)}.",
                403,
            )

        return {"user_id": user_id, "role": role}

    @staticmethod
    def generate_token(user_id: str, role: str) -> str:
        """
        Helper for tests and the driver/rider registration flow.
        """
        payload = {"user_id": user_id, "role": role}
        return jwt.encode(payload, Config.JWT_SECRET_KEY, algorithm=Config.JWT_ALGORITHM)
