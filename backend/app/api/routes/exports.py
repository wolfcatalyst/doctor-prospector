"""Export routes - generate and download export files."""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel

from app.dependencies import get_current_user, get_active_device_profile
from app.services import export_service

router = APIRouter()


class ExportRequest(BaseModel):
    """Request body for creating an export."""

    items: list[dict]  # [{hospitalId, hospitalName, physicianNpis}]
    options: dict = {}  # {format_type, include_trials, include_publications, ...}


@router.post("")
async def create_export(
    body: ExportRequest,
    user: dict = Depends(get_current_user),
    device_profile: dict = Depends(get_active_device_profile),
):
    """Generate an export file synchronously and return it as a download."""
    if not body.items:
        raise HTTPException(status_code=400, detail="Export queue is empty")

    # Default options
    options = {
        "format_type": "excel",
        "include_hospitals": True,
        "include_trials": True,
        "include_publications": True,
        "include_payments": True,
        "include_contact": True,
        "include_historical": False,
        **body.options,
    }

    # Same profile-aware hospital list the Hospitals pages use: for non-TAVR
    # profiles the hospitals (and their DRG volumes) only exist in this list
    from app.api.routes.hospitals import _get_enriched_hospitals
    hospitals = await _get_enriched_hospitals(device_profile)

    try:
        filename, file_bytes, mime_type, record = await export_service.generate_export(
            queue_items=body.items,
            options=options,
            hospital_list=hospitals,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export generation failed: {e}")

    return Response(
        content=file_bytes,
        media_type=mime_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Export-Id": record["export_id"],
            "X-Hospital-Count": str(record["hospital_count"]),
            "X-Physician-Count": str(record["physician_count"]),
        },
    )


@router.get("")
async def list_exports(
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    user: dict = Depends(get_current_user),
):
    """List user's export history."""
    history = export_service.get_export_history()
    total = len(history)
    start = (page - 1) * per_page
    page_items = history[start : start + per_page]

    return {
        "exports": page_items,
        "total": total,
        "page": page,
        "per_page": per_page,
    }


@router.get("/{export_id}")
async def get_export(export_id: str, user: dict = Depends(get_current_user)):
    """Get export job status/details."""
    record = export_service.get_export_by_id(export_id)
    if not record:
        raise HTTPException(status_code=404, detail="Export not found")
    return record


@router.get("/{export_id}/download")
async def download_export(export_id: str, user: dict = Depends(get_current_user)):
    """Download a previously generated export file."""
    result = export_service.get_export_file(export_id)
    if not result:
        raise HTTPException(status_code=404, detail="Export file not found")

    filename, file_bytes, mime_type = result
    return Response(
        content=file_bytes,
        media_type=mime_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )
