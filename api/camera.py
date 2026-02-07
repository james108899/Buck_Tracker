from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel, Field, validator
from typing import List, Optional
from .utils import save_cameras, load_cameras, get_user_file, user_exists
from .config import UPLOAD_DIR,GCS_UPLOAD_DIR
import os
import shutil

print(" CAMERA API LOADED ")

router = APIRouter(prefix="/camera", tags=["Camera"])

# ================= MODELS =================
class CameraData(BaseModel):
    user_id: str = Field(..., min_length=1)
    camera_name: str = Field(..., min_length=1)
    camera_loc: Optional[List[float]] = None

    @validator("camera_loc")
    def validate_loc(cls, loc):
        if loc is None:
            return loc
        if len(loc) != 2:
            raise ValueError("camera_loc must be [lat, lon]")
        lat, lon = loc
        if not (-90 <= lat <= 90):
            raise ValueError("Latitude must be between -90 and 90")
        if not (-180 <= lon <= 180):
            raise ValueError("Longitude must be between -180 and 180")
        return loc


class EditCameraData(BaseModel):
    user_id: str
    old_camera_name: str
    new_camera_name: str
    new_camera_loc: List[float]

    @validator("new_camera_loc")
    def validate_loc(cls, loc):
        if len(loc) != 2:
            raise ValueError("new_camera_loc must be [lat, lon]")
        lat, lon = loc
        if not (-90 <= lat <= 90):
            raise ValueError("Latitude must be between -90 and 90")
        if not (-180 <= lon <= 180):
            raise ValueError("Longitude must be between -180 and 180")
        return loc


# ================= ROUTES =================
@router.get("/")
def home():
    return {
        "message": "Camera API is Running",
        "endpoints": [
            "/camera/add_camera",
            "/camera/edit_camera",
            "/camera/delete_camera",
            "/camera/get_cameras?user_id=<id>"
        ]
    }


# ---------- GET CAMERAS ----------
@router.get("/get_cameras")
def get_cameras(user_id: str = Query(...)):
    if not user_exists(user_id):
        raise HTTPException(status_code=404, detail="User not found")

    cameras = load_cameras(user_id)
    return {"success": True, "user_id": user_id, "cameras": cameras, "count": len(cameras)}


# ---------- ADD CAMERA ----------
@router.post("/add_camera")
def add_camera(data: CameraData):
    cameras = load_cameras(data.user_id)

    if len(cameras) >= 2:
        raise HTTPException(status_code=400, detail="Only 2 cameras allowed")

    for cam in cameras:
        if cam["camera_name"].lower() == data.camera_name.lower():
            raise HTTPException(status_code=400, detail="Camera already exists")

    cameras.append({"camera_name": data.camera_name, "camera_loc": data.camera_loc})
    save_cameras(data.user_id, cameras)

    return {"success": True, "camera": data.camera_name}

@router.put("/edit_camera")
def edit_camera(data: EditCameraData):
    if not user_exists(data.user_id):
        raise HTTPException(status_code=404, detail="User not found")

    cameras = load_cameras(data.user_id)

    # Check if new camera name already exists (case-insensitive)
    if any(cam["camera_name"].lower() == data.new_camera_name.lower() for cam in cameras):
        raise HTTPException(status_code=400, detail=f"Camera name '{data.new_camera_name}' already exists")

    camera_found = False
    for cam in cameras:
        if cam["camera_name"].lower() == data.old_camera_name.lower():
            old_name = cam["camera_name"]
            cam["camera_name"] = data.new_camera_name
            cam["camera_loc"] = data.new_camera_loc
            camera_found = True

            # Rename camera folder
            old_folder = os.path.join(UPLOAD_DIR, data.user_id, old_name)
            new_folder = os.path.join(UPLOAD_DIR, data.user_id, data.new_camera_name)
            if os.path.exists(old_folder) and os.path.isdir(old_folder):
                try:
                    os.rename(old_folder, new_folder)
                except Exception as e:
                    raise HTTPException(status_code=500, detail=f"Failed to rename camera folder: {str(e)}")

                # Rename detection JSON
                for f in os.listdir(new_folder):
                    if f.endswith("_detections.json") and f.lower().startswith(old_name.lower()):
                        old_json = os.path.join(new_folder, f)
                        new_json_name = f.replace(old_name, data.new_camera_name)
                        new_json = os.path.join(new_folder, new_json_name)
                        try:
                            os.rename(old_json, new_json)
                        except Exception as e:
                            raise HTTPException(status_code=500, detail=f"Failed to rename detection JSON: {str(e)}")
                        break  # Only one detection JSON per camera

            save_cameras(data.user_id, cameras)
            return {"success": True, "updated": cam}

    if not camera_found:
        raise HTTPException(status_code=404, detail="Camera not found")

@router.delete("/delete_camera")
def delete_camera(user_id: str = Query(...), camera_name: str = Query(...)):
    if not user_exists(user_id):
        raise HTTPException(status_code=404, detail="User not found")
    cameras = load_cameras(user_id)
    new_list = [c for c in cameras if c["camera_name"].lower() != camera_name.lower()]
    if len(new_list) == len(cameras):
        raise HTTPException(status_code=404, detail="Camera not found")
    save_cameras(user_id, new_list)
    camera_folder = os.path.join(UPLOAD_DIR, user_id, camera_name)
    if os.path.exists(camera_folder) and os.path.isdir(camera_folder):
        try:
            shutil.rmtree(camera_folder)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to delete camera folder: {str(e)}")
    return {"success": True, "deleted": camera_name}
