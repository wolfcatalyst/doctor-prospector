from fastapi import APIRouter

from app.api.routes import auth, hospitals, physicians, sources, exports, settings, feedback, admin, edwards, device_profiles

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(hospitals.router, prefix="/hospitals", tags=["hospitals"])
api_router.include_router(physicians.router, prefix="/physicians", tags=["physicians"])
api_router.include_router(sources.router, prefix="/sources", tags=["sources"])
api_router.include_router(edwards.router, prefix="/edwards", tags=["edwards"])
api_router.include_router(device_profiles.router, prefix="/device-profiles", tags=["device-profiles"])
api_router.include_router(exports.router, prefix="/exports", tags=["exports"])
api_router.include_router(settings.router, prefix="/settings", tags=["settings"])
api_router.include_router(feedback.router, prefix="/feedback", tags=["feedback"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
