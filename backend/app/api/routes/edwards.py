"""Edwards Connect routes - Edwards Lifesciences TAVR center directory."""

from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.dependencies import get_current_user
from app.services import edwards_service

router = APIRouter()

EDWARDS_SEARCH_URL = "https://treatheartvalvefailure.com/find-a-tavr-hospital"


@router.get("")
async def list_edwards_hospitals(
    state: Optional[str] = Query(None, description="Filter by state code (e.g. NJ)"),
    search: Optional[str] = Query(None, description="Search by hospital name, city, or doctor name"),
    user: dict = Depends(get_current_user),
):
    """List all Edwards TAVR center listings with optional filters."""
    hospitals = await edwards_service.get_all_edwards_hospitals(
        state=state,
        search=search,
    )
    return {
        "hospitals": hospitals,
        "total": len(hospitals),
        "edwards_search_url": EDWARDS_SEARCH_URL,
    }


@router.post("/refresh")
async def refresh_edwards_data(user: dict = Depends(get_current_user)):
    """Force refresh Edwards data from API."""
    hospitals = await edwards_service.get_all_edwards_hospitals(force_refresh=True)
    return {
        "message": f"Refreshed Edwards data: {len(hospitals)} hospitals",
        "total": len(hospitals),
    }


@router.get("/match")
async def match_edwards_hospital(
    name: str = Query(..., description="Hospital name to match"),
    city: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
):
    """Find an Edwards listing matching a hospital name."""
    match = await edwards_service.get_edwards_hospital_by_name(
        hospital_name=name,
        city=city,
        state=state,
    )
    return {
        "match": match,
        "edwards_search_url": EDWARDS_SEARCH_URL,
    }
