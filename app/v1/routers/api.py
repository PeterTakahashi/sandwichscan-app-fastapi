from app.core.routers.api_router import APIRouter
from app.v1.routers.chains import router as chains_router

router = APIRouter()

router.include_router(chains_router)

api_router = router
