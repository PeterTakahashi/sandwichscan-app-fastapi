from app.core.routers.api_router import APIRouter
from app.v1.routers.chains import router as chains_router
from app.v1.routers.defis import router as defis_router
from app.v1.routers.defi_versions import router as defi_versions_router
from app.v1.routers.defi_pools import router as defi_pools_router
from app.v1.routers.tokens import router as tokens_router
from app.v1.routers.sandwich_attacks import router as sandwich_attacks_router

router = APIRouter()

router.include_router(chains_router)
router.include_router(defis_router)
router.include_router(defi_versions_router)
router.include_router(defi_pools_router)
router.include_router(tokens_router)
router.include_router(sandwich_attacks_router)

api_router = router
