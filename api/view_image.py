from fastapi import APIRouter, HTTPException, Query, Request
from pathlib import Path
import json
from .config import UPLOAD_DIR

router = APIRouter()

@router.get("/view_images")
def view_images(
    request: Request, 
    user_id: str = Query(...), 
    camera_name: str = Query(...),
    filter_label: str = Query(None, description="Optional filter: Buck, Doe, Mule, Whitetail")
):
    """
    Get images and detection info for a user's camera.
    Returns clickable URLs for each image.
    Optionally filter images based on labels (Buck, Doe, Mule, Whitetail).
    """
    user_folder = Path(UPLOAD_DIR) / user_id
    if not user_folder.exists():
        raise HTTPException(status_code=404, detail="User not found")

    camera_folder = user_folder / camera_name
    raw_folder = camera_folder / "raw"
    detection_file = camera_folder / f"{camera_name}_detections.json"

    if not raw_folder.exists():
        raise HTTPException(status_code=404, detail="Camera raw folder not found")
    if not detection_file.exists():
        raise HTTPException(status_code=404, detail="Detection JSON not found")

    # Load detection JSON
    try:
        with open(detection_file, "r") as f:
            detections = json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read detection file: {e}")

    # Determine base URL (cloud-safe)
    base_url = str(request.base_url)
    if "0.0.0.0" in base_url or "127.0.0.1" in base_url:
        base_url = base_url.replace("0.0.0.0", "localhost").replace("127.0.0.1", "localhost")
    if not base_url.endswith("/"):
        base_url += "/"

    # List of labels to filter if provided
    valid_filters = {"buck", "doe", "mule", "whitetail"}
    filter_lower = filter_label.lower() if filter_label else None
    if filter_lower and filter_lower not in valid_filters:
        raise HTTPException(status_code=400, detail=f"Invalid filter_label. Must be one of {valid_filters}")

    images = []
    for item in detections:
        image_path = raw_folder / item["filename"]
        if image_path.exists():
            item["image_url"] = f"{base_url}user_data/{user_id}/{camera_name}/raw/{item['filename']}"
        else:
            item["missing"] = True
            item["image_url"] = None

        # Apply label filter if provided
        if filter_lower:
            filtered_detections = [
                det for det in item.get("detections", []) 
                if any(lbl.lower().find(filter_lower) != -1 for lbl in det["label"].split("|"))
            ]
            if filtered_detections:
                item["detections"] = filtered_detections
                images.append(item)
        else:
            images.append(item)

    return {
        "success": True,
        "user_id": user_id,
        "camera_name": camera_name,
        "filter_label": filter_label,
        "images": images
    }
