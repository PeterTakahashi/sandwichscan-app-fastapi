from fastapi import Depends, Request
from app.v1.schemas.defi_version import (
    DefiVersionListRead,
    DefiVersionRead,
    DefiVersionSearchParams,
)
from app.v1.dependencies.models.defi_version.get_defi_version_by_id import (
    get_defi_version_by_id,
)
from app.v1.dependencies.services.defi_version_service import get_defi_version_service
from app.v1.services.defi_version_service import DefiVersionService
from app.models.defi_version import DefiVersion

from app.core.routers.api_router import APIRouter

router = APIRouter(prefix="/defi_versions", tags=["Defi Versions"])


@router.get(
    "",
    response_model=DefiVersionListRead,
    name="defi_versions:list_defi_versions",
)
async def list_defi_versions(
    request: Request,
    search_params: DefiVersionSearchParams = Depends(),
    service: DefiVersionService = Depends(get_defi_version_service),
):
    """
    Retrieve a list of defi_versions with filtering, sorting, and pagination.
    """
    return await service.get_list(search_params=search_params)


@router.get(
    "/{defi_version_id}",
    response_model=DefiVersionRead,
    name="defi_versions:get_defi_version",
)
async def get_defi_version(
    defi_version: DefiVersion = Depends(get_defi_version_by_id),
):
    """
    Retrieve an defi_version by its ID.
    """
    return DefiVersionRead.model_validate(defi_version)
