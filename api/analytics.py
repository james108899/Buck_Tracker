from fastapi import APIRouter, Query, HTTPException
from .utils import get_user_dashboard, validate_user_and_camera

router = APIRouter()

@router.get("/user_dashboard")
def user_dashboard(
    user_id: str = Query(..., description="User ID for analytics"),
    camera_name: str = Query(None, description="Optional camera name to filter")
):
    """
    Return analytics for a user. 
    If camera_name is provided, validate camera and show stats for that camera only.
    """
    try:
        # Validate camera if specified
        if camera_name:
            validate_user_and_camera(user_id, camera_name)

        # Get dashboard (all cameras or specific)
        dashboard = get_user_dashboard(user_id, camera_name=camera_name)
        return {"success": True, "dashboard": dashboard}

    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")
