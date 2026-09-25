"""Consistent RFC 7807 ``application/problem+json`` error responses. No stack traces or paths are ever returned."""
from __future__ import annotations

import logging
from typing import Any

from app.core.logging import request_id_var
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("app.errors")
PROBLEM = "application/problem+json"


class ApiError(Exception):
    """Raise from services/routers to return a structured problem response."""

    def __init__(self, status: int, code: str, title: str, detail: str = "", extra: dict[str, Any] | None = None,
                 headers: dict[str, str] | None = None) -> None:
        super().__init__(title)
        self.status, self.code, self.title, self.detail = status, code, title, detail
        self.extra, self.headers = extra or {}, headers or {}


def problem(status: int, code: str, title: str, detail: str = "", request_id: str | None = None,
            extra: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> JSONResponse:
    body: dict[str, Any] = {
        "type": f"https://errors.extreme-weather-ai/{code}", "title": title, "status": status, "code": code,
        "detail": detail, "request_id": request_id or request_id_var.get(),
    }
    body.update(extra or {})
    return JSONResponse(body, status_code=status, media_type=PROBLEM, headers=headers)


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return problem(exc.status, exc.code, exc.title, exc.detail, extra=exc.extra, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [{"loc": [str(x) for x in e["loc"]], "msg": e["msg"], "type": e["type"]} for e in exc.errors()]
        return problem(422, "VALIDATION_ERROR", "Request validation failed", "One or more parameters are invalid.",
                       extra={"errors": errors})

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        titles = {404: "Not found", 405: "Method not allowed", 401: "Authentication required", 403: "Forbidden"}
        return problem(exc.status_code, f"HTTP_{exc.status_code}", titles.get(exc.status_code, "HTTP error"),
                       str(exc.detail) if exc.status_code < 500 else "")

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        log.error("unhandled exception", extra={"exc_type": type(exc).__name__}, exc_info=True)
        return problem(500, "INTERNAL_ERROR", "Internal server error", "The request could not be completed.")
