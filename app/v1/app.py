from fastapi import FastAPI
from app.v1.routers import api as api_router
from app.core.config import settings

from fastapi.exceptions import RequestValidationError
from fastapi import HTTPException
from sqlalchemy.exc import NoResultFound
from scalar_fastapi import get_scalar_api_reference
from fastapi.responses import HTMLResponse

from app.lib.exception.api_exception import APIException
from app.core.exception_handlers.api_exception_handler import api_exception_handler
from app.core.exception_handlers.http_exception_handler import http_exception_handler
from app.core.exception_handlers.no_result_found_exception_handler import (
    no_result_found_exception_handler,
)
from app.core.exception_handlers.server_exception_handler import (
    server_exception_handler,
)
from app.core.exception_handlers.validation_exception_handler import (
    validation_exception_handler,
)

v1_app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Version 1 of the FastAPI Application",
    version="1.0.0",
)

v1_app.include_router(api_router.api_router)

v1_app.add_exception_handler(HTTPException, http_exception_handler)  # type: ignore
v1_app.add_exception_handler(Exception, server_exception_handler)  # type: ignore
v1_app.add_exception_handler(
    RequestValidationError, validation_exception_handler  # type: ignore
)

v1_app.add_exception_handler(NoResultFound, no_result_found_exception_handler)  # type: ignore

v1_app.add_exception_handler(APIException, api_exception_handler)  # type: ignore

@v1_app.get("/scalar", include_in_schema=False, response_class=HTMLResponse)
async def scalar_docs():
    return get_scalar_api_reference(
        openapi_url=f"/app/v1{v1_app.openapi_url}",
        title="SandwichScan Scalar API",
        scalar_proxy_url="https://proxy.scalar.com",
    )