from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from pathlib import Path
import cv2
import numpy as np

from .config import UPLOAD_DIR
from .utils import (
    validate_form,
    process_image,
    save_image,
    load_json,
    save_json,
    validate_user_and_camera
)

router = APIRouter()
@router.post("/predict")
async def predict(
    user_id: str = Form(...),
    camera_name: str = Form(...),
    images: list[UploadFile] = File(...)
):
    images = validate_form(user_id, camera_name, images)
    validate_user_and_camera(user_id, camera_name)
    base = Path(UPLOAD_DIR) / user_id / camera_name
    base.mkdir(parents=True, exist_ok=True)     
    json_path = base / f"{camera_name}_detections.json"
    data = load_json(json_path)
    new_results = []
    for file in images:
        raw = await file.read()
        nparr = np.frombuffer(raw, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            raise HTTPException(400, f"Invalid image: {file.filename}")
        detections = process_image(img)
        url = save_image(user_id, camera_name, file.filename, raw)
        record = {
            "filename": file.filename,
            "image_url": url,
            "detections": detections
        }
        data.append(record)
        new_results.append(record)
    save_json(json_path, data)
    return {
        "message": "Images processed successfully",
        "camera": camera_name,
        "results": new_results
    }
