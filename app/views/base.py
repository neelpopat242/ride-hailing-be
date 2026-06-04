import inspect
from dataclasses import dataclass, field
from typing import Callable, Optional, Type

from flask import Blueprint, request
from pydantic import ValidationError

from app.auth.jwt_auth import JWTAuth
from app.db import get_session
from app.utils.responses import error_response


@dataclass
class RouteInfo:
    method: str
    path: str
    action: str
    schema: Optional[Type] = field(default=None)
    auth: Optional[list[str]] = field(default=None)  # None = public, ["rider"] / ["driver"] / ["rider","driver"]


# Attribute name stamped onto decorated methods
_ROUTE_ATTR = "_route_info"


def route(
    method: str,
    path: str = "",
    schema: Optional[Type] = None,
    auth: Optional[list[str]] = None,
) -> Callable:
    """
    Decorator that registers a ViewSet method as an HTTP endpoint.

    Args:
        method:  HTTP method ("GET", "POST", etc.)
        path:    URL path relative to the ViewSet prefix.
        schema:  Pydantic schema class for request body validation.
        auth:    Allowed roles. None = public (no auth).
                 ["rider"] / ["driver"] / ["rider", "driver"]

    Usage:
        @route("POST", "/<string:driver_id>/accept",
               schema=DriverAcceptSchema, auth=["driver"])
        def accept(self, driver_id: str):
            ...
    """
    def decorator(func: Callable) -> Callable:
        setattr(func, _ROUTE_ATTR, RouteInfo(
            method=method,
            path=path,
            action=func.__name__,
            schema=schema,
            auth=auth,
        ))
        return func
    return decorator


class ViewSet:
    """
    Base class for class-based route grouping.

    Subclasses declare services in __init__:
        def __init__(self, session):
            super().__init__(session)
            self.ride_service = RideService(session)

    Declare endpoints with the @route decorator.
    Call ViewSet.register(blueprint, prefix) to wire all decorated
    methods onto a Flask blueprint automatically.

    Per-request state available in every action:
        self.session        — SQLAlchemy session (injected, committed on exit)
        self.validated_data — Pydantic-validated request payload (dict)
        self.headers        — Flask request headers
        self.actor          — JWT payload dict if auth was required, else None
    """

    def __init__(self, session):
        self.session = session
        self.validated_data: dict = {}
        self.headers = request.headers
        self.actor: Optional[dict] = None

    @classmethod
    def _collect_routes(cls) -> list[RouteInfo]:
        return [
            getattr(member, _ROUTE_ATTR)
            for _, member in inspect.getmembers(cls, predicate=inspect.isfunction)
            if hasattr(member, _ROUTE_ATTR)
        ]

    @classmethod
    def register(cls, blueprint: Blueprint, prefix: str = "") -> None:
        for route_info in cls._collect_routes():
            blueprint.add_url_rule(
                f"{prefix}{route_info.path}",
                endpoint=f"{cls.__name__}__{route_info.action}",
                view_func=cls._make_view(route_info),
                methods=[route_info.method],
            )

    @classmethod
    def _make_view(cls, route_info: RouteInfo) -> Callable:
        def view(*args, **kwargs):
            # Auth check — runs before session opens or payload is parsed
            actor = None
            if route_info.auth is not None:
                actor = JWTAuth.authenticate(allowed_roles=route_info.auth)

            # Payload validation
            validated_data = {}
            if route_info.schema:
                payload = request.get_json(silent=True) or {}
                try:
                    validated_data = route_info.schema(**payload).model_dump()
                except ValidationError as exc:
                    return error_response("VALIDATION_ERROR", exc.errors(), 400)

            with get_session() as session:
                instance = cls(session)
                instance.validated_data = validated_data
                instance.actor = actor
                return getattr(instance, route_info.action)(*args, **kwargs)

        # Flask requires a unique __name__ per endpoint across the entire app
        view.__name__ = f"{cls.__name__}__{route_info.action}"
        return view
