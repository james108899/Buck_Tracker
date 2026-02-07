import os
import json
from pathlib import Path
from fastapi import HTTPException
import cv2
import numpy as np

# ---------------- CONFIG IMPORTS ----------------
from .config import (
    DETECT_MODEL,
    BUCK_DOE_MODEL,
    BUCK_TYPE_MODEL,
    ALLOWED_EXTENSIONS,
    MIN_IMAGES,
    MAX_IMAGES,
    UPLOAD_DIR,
    STORAGE_BACKEND,
    gcs_bucket,
    GCS_UPLOAD_DIR,
    logger
)

# ---------------- VALIDATION ----------------
def validate_form(user_id, camera_name, images):
    if not user_id or not user_id.strip():
        raise HTTPException(400, "user_id is required")

    if not camera_name or not camera_name.strip():
        raise HTTPException(400, "camera_name is required")

    if not images or len(images) == 0:
        raise HTTPException(400, "At least one image is required")

    images = [f for f in images if f.filename and f.filename.strip()]

    if len(images) < MIN_IMAGES:
        raise HTTPException(400, f"At least {MIN_IMAGES} image(s) required")

    if len(images) > MAX_IMAGES:
        raise HTTPException(400, f"Maximum {MAX_IMAGES} images allowed")

    for f in images:
        if "." not in f.filename:
            raise HTTPException(400, f"Invalid file: {f.filename}")

        ext = f.filename.rsplit(".", 1)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(400, f"Invalid file type: {f.filename}")

    return images

# ---------------- IMAGE PROCESSING ----------------
def process_image(image):
    """Run detection and classification on an image"""
    detections = []
    results = DETECT_MODEL(image)

    for r in results:
        for box in r.boxes:
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            crop = image[y1:y2, x1:x2]
            if crop.size == 0:
                continue

            buck_res = BUCK_DOE_MODEL(crop)
            buck_name = buck_res[0].names[buck_res[0].probs.top1]

            if buck_name.lower() == "buck":
                type_res = BUCK_TYPE_MODEL(crop)
                type_name = type_res[0].names[type_res[0].probs.top1]
                label = f"Deer | Buck | {type_name}"
            else:
                label = "Deer | Doe"

            detections.append({
                "label": label,
                "bbox": [x1, y1, x2, y2]
            })

    return detections



# ---------------- CAMERA VALIDATION ----------------
def validate_user_and_camera(user_id: str, camera_name: str):
    if not user_exists(user_id):
        raise HTTPException(404, "User not found")

    cameras = load_cameras(user_id)

    if not any(c["camera_name"] == camera_name for c in cameras):
        raise HTTPException(404, "Camera not registered")


# ---------------- IMAGE SAVE ----------------
def save_image(user_id, camera_name, filename, data):
    path = BASE_DIR / user_id / camera_name / "raw"
    path.mkdir(parents=True, exist_ok=True)

    local_path = path / filename
    with open(local_path, "wb") as f:
        f.write(data)

    if STORAGE_BACKEND == "gcs" and gcs_bucket:
        blob = gcs_bucket.blob(f"{GCS_UPLOAD_DIR}{user_id}/{camera_name}/{filename}")
        blob.upload_from_filename(local_path)
        return blob.public_url

    return f"/user_data/{user_id}/{camera_name}/raw/{filename}"


# ---------------- JSON ----------------
def load_json(path):
    if Path(path).exists():
        with open(path, "r") as f:
            return json.load(f)
    return []

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=4)

# ---------------- USER FOLDERS / CAMERAS ----------------
BASE_DIR = Path(UPLOAD_DIR)
BASE_DIR.mkdir(exist_ok=True)

def get_user_folder(user_id: str) -> Path:
    """Return path to user's folder WITHOUT creating it"""
    return BASE_DIR / f"{user_id}"

def get_user_file(user_id: str) -> Path:
    """Return path to user's cameras.json WITHOUT creating it"""
    return get_user_folder(user_id) / "cameras.json"

def user_exists(user_id: str) -> bool:
    return get_user_file(user_id).exists()

def load_cameras(user_id: str) -> list:
    path = get_user_file(user_id)

    if not path.exists():
        return []

    try:
        with open(path, "r") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return []

def save_cameras(user_id: str, cameras: list):
    # Folder only created when we are saving ( Add Camera)
    folder = get_user_folder(user_id)
    folder.mkdir(exist_ok=True)

    with open(folder / "cameras.json", "w") as f:
        json.dump(cameras, f, indent=2)



#>>>>>>>>dashboard>>>>>>>>>>>>
def get_user_dashboard(user_id: str, camera_name: str = None) -> dict:
    """Return analytics for a user or a specific camera"""
    user_folder = Path(UPLOAD_DIR) / user_id
    cameras_file = user_folder / "cameras.json"

    if not cameras_file.exists():
        raise HTTPException(404, f"User {user_id} not found")

    try:
        with open(cameras_file, "r") as f:
            cameras = json.load(f)
    except json.JSONDecodeError:
        cameras = []

    total_cameras = len(cameras)
    total_images = 0
    total_detections = 0
    buck_type_distribution = {}
    buck_doe_distribution = {"Buck": 0, "Doe": 0}

    for cam in cameras:
        cam_name = cam["camera_name"]

        # Skip cameras if a specific one is selected
        if camera_name and cam_name != camera_name:
            continue

        raw_folder = user_folder / cam_name / "raw"
        detections_file = user_folder / cam_name / f"{cam_name}_detections.json"

        # Count images
        if raw_folder.exists():
            total_images += len(list(raw_folder.glob("*.*")))
        # Count detections and distributions
        if detections_file.exists():
            try:
                dets = json.load(open(detections_file, "r"))
                for rec in dets:
                    for d in rec.get("detections", []):
                        total_detections += 1
                        label = d.get("label", "")
                        if "|" in label:
                            parts = [p.strip() for p in label.split("|")]
                            if len(parts) == 3:  # Buck with type
                                buck_doe_distribution["Buck"] += 1
                                buck_type_distribution[parts[2]] = buck_type_distribution.get(parts[2], 0) + 1
                            else:  # Doe
                                buck_doe_distribution["Doe"] += 1
            except json.JSONDecodeError:
                continue
    return {
        "user_id": user_id,
        "selected_camera": camera_name,
        "total_cameras": total_cameras,
        "images_uploaded": total_images,
        "total_detections": total_detections,
        "buck_type_distribution": buck_type_distribution,
        "buck_doe_distribution": buck_doe_distribution
    }
