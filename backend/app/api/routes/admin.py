from fastapi import APIRouter, Depends, Query

from app.dependencies import require_admin

router = APIRouter()


@router.get("/users")
async def list_users(
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    user: dict = Depends(require_admin),
):
    """List all users (admin only). (Phase 6)"""
    return {"message": "Not implemented yet - Phase 6", "users": []}


@router.post("/cache/clear")
async def clear_cache(user: dict = Depends(require_admin)):
    """Clear source cache (admin only). (Phase 6)"""
    return {"message": "Not implemented yet - Phase 6"}


@router.post("/cache/warm")
async def warm_cache(user: dict = Depends(require_admin)):
    """Warm source cache (admin only). (Phase 6)"""
    return {"message": "Not implemented yet - Phase 6"}


@router.get("/cache/status")
async def cache_status(user: dict = Depends(require_admin)):
    """Full cache status (admin only). (Phase 6)"""
    return {"message": "Not implemented yet - Phase 6"}
