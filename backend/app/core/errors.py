from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class HydroShieldError(Exception):
    """Base exception for expected application-level errors."""

    status_code = 400
    code = "HYDROSHIELD_ERROR"

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class NotFoundError(HydroShieldError):
    status_code = 404
    code = "NOT_FOUND"


class ConflictError(HydroShieldError):
    status_code = 409
    code = "CONFLICT"


class InternalError(HydroShieldError):
    status_code = 500
    code = "INTERNAL_ERROR"


async def hydroshield_exception_handler(request: Request, exc: HydroShieldError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "path": request.url.path,
                "request_id": getattr(request.state, "request_id", None),
            }
        },
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Request validation failed.",
                "details": jsonable_encoder(exc.errors()),
                "path": request.url.path,
                "request_id": getattr(request.state, "request_id", None),
            }
        },
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    import logging

    logging.getLogger("hydroshield.request").exception(
        "Unhandled request exception", extra={"request_id": getattr(request.state, "request_id", None)}
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "Internal server error.",
                "path": request.url.path,
                "request_id": getattr(request.state, "request_id", None),
            }
        },
    )
