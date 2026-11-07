"""Consistent JSON error responses.

Every error has the shape::

    {"error": {"code": "not_found", "message": "Student 999 not found", "details": [...]}}
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

from ml.schema import ValidationError as MLValidationError

log = logging.getLogger("backend")


class AppError(Exception):
    status_code = 400
    code = "bad_request"

    def __init__(self, message: str, details: list | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or []


class NotFound(AppError):
    status_code = 404
    code = "not_found"


class Invalid(AppError):
    status_code = 422
    code = "validation_error"


class InsufficientData(AppError):
    """The ML models cannot be trained from the data currently in the database."""
    status_code = 503
    code = "ml_insufficient_data"


class Unauthorized(AppError):
    """No valid session (missing, expired, revoked or wrong credentials)."""
    status_code = 401
    code = "not_authenticated"


class Forbidden(AppError):
    status_code = 403
    code = "forbidden"

    def __init__(self, message: str = "You do not have permission to do that", details: list | None = None,
                 code: str | None = None):
        super().__init__(message, details)
        if code:
            self.code = code


class TooManyRequests(AppError):
    status_code = 429
    code = "rate_limited"

    def __init__(self, message: str, retry_after: int = 60):
        super().__init__(message)
        self.retry_after = retry_after


class Conflict(AppError):
    status_code = 409
    code = "conflict"

    def __init__(self, message: str, details: list | None = None, code: str | None = None):
        super().__init__(message, details)
        if code:
            self.code = code


def _body(code: str, message: str, details: list | None = None) -> dict:
    return {"error": {"code": code, "message": message, "details": details or []}}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError):
        headers = {"Retry-After": str(exc.retry_after)} if isinstance(exc, TooManyRequests) else None
        return JSONResponse(_body(exc.code, exc.message, exc.details), status_code=exc.status_code,
                            headers=headers)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        details = [{"field": ".".join(str(p) for p in err["loc"] if p != "body"),
                    "message": err["msg"]} for err in exc.errors()]
        return JSONResponse(_body("validation_error", "Request validation failed", details),
                            status_code=422)

    @app.exception_handler(MLValidationError)
    async def _ml_validation(_: Request, exc: MLValidationError):
        return JSONResponse(_body("validation_error", str(exc)), status_code=422)

    @app.exception_handler(IntegrityError)
    async def _integrity(_: Request, exc: IntegrityError):
        log.warning("Integrity error: %s", exc.orig)
        return JSONResponse(_body("conflict", "The request conflicts with existing data"),
                            status_code=409)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException):
        code = {401: "not_authenticated", 403: "forbidden", 404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
        return JSONResponse(_body(code, str(exc.detail)), status_code=exc.status_code)

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception):
        log.exception("Unhandled error", exc_info=exc)
        return JSONResponse(_body("internal_error", "An unexpected error occurred"), status_code=500)
