from fastapi import APIRouter, UploadFile, File, HTTPException, Request, Form
from fastapi.responses import FileResponse, JSONResponse
from fastapi.concurrency import run_in_threadpool
from PIL import Image

import warnings
import os
import cv2
import json
import numpy as np
import hashlib
from datetime import datetime

from .config import logger, model, ALLOWED_EXTENSIONS, UPLOAD_DIR, STORAGE_BACKEND
from .utils import (
    load_metadata,
    save_metadata,
    save_image_and_get_url,
    get_image_url
)

router = APIRouter()

# =========================================================
# Serve Local Images
# =========================================================
@router.get("/uploads/{user_id}/{filename}")
async def serve_upload(user_id: str, filename: str):
    path = os.path.join(UPLOAD_DIR, "users", user_id, filename)
    if not os.path.exists(path):
        raise HTTPException(404, "File not found")
    return FileResponse(path)


# =========================================================
# Upload + Detect
# =========================================================
@router.post("/process-images")
async def process_images(
    request: Request,
    user_id: int = Form(...),
    images_batch: list[UploadFile] = File(...)
):
    if user_id <= 0:
        raise HTTPException(400, "Invalid user_id")

    base_url = str(request.base_url).rstrip("/")
    user_id_str = str(user_id)

    metadata = load_metadata(user_id_str)

    results_list = []
    grouped_results = {}
    seen_hashes = set()
    duplicates = []
    total_detections = 0

    for img in images_batch:
        file_bytes = await img.read()
        file_hash = hashlib.md5(file_bytes).hexdigest()

        if file_hash in seen_hashes:
            duplicates.append(img.filename)
            continue
        seen_hashes.add(file_hash)

        ext = os.path.splitext(img.filename)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(400, f"Unsupported type {ext}")

        np_arr = np.frombuffer(file_bytes, np.uint8)
        frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

        res = await run_in_threadpool(model.predict, frame, False)
        r = res[0]

        detections = []
        class_names = set()

        if r.boxes:
            for box in r.boxes:
                cls = int(box.cls[0])
                conf = float(box.conf[0])
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                name = model.names.get(cls, str(cls))

                detections.append({
                    "class": name,
                    "conf": round(conf, 4),
                    "bbox": [x1, y1, x2, y2]
                })
                class_names.add(name)
                total_detections += 1

        if not class_names:
            class_names.add("unknown")

        im_rgb = Image.fromarray(cv2.cvtColor(r.plot(), cv2.COLOR_BGR2RGB))
        out_name = f"{os.path.splitext(img.filename)[0]}_det.jpg"

        image_url = save_image_and_get_url(user_id_str, out_name, im_rgb, base_url)

        metadata[out_name] = {
            "tags": list(class_names),
            "objects": detections,
            "hash": file_hash,
            "timestamp": datetime.utcnow().isoformat()
        }

        for cname in class_names:
            grouped_results.setdefault(cname, []).append(image_url)

        results_list.append({
            "image_name": out_name,
            "image_url": image_url,
            "tags": list(class_names),
            "objects": detections
        })

    save_metadata(user_id_str, metadata)

    return JSONResponse({
        "status": "success",
        "user_id": user_id,
        "images_processed": len(results_list),
        "total_detections": total_detections,
        "duplicates": duplicates,
        "grouped_results": grouped_results,
        "results": results_list
    })


# =========================================================
# Results by class
# =========================================================
@router.get("/results")
async def get_results_by_class(
    request: Request,
    user_id: int,
    class_name: str
):
    if user_id <= 0:
        raise HTTPException(400, "Invalid user_id")

    base_url = str(request.base_url).rstrip("/")
    user_id_str = str(user_id)

    metadata = load_metadata(user_id_str)

    results = []

    for filename, data in metadata.items():
        if class_name in data.get("tags", []):
            url = get_image_url(user_id_str, filename, base_url)

            results.append({
                "image_name": filename,
                "image_url": url,
                "class": class_name,
                "timestamp": data.get("timestamp")
            })

    return JSONResponse({
        "status": "success",
        "user_id": user_id,
        "class": class_name,
        "count": len(results),
        "results": results
    })


# =========================================================
# All classes
# =========================================================
@router.get("/classes")
async def get_user_classes(user_id: int):
    user_id_str = str(user_id)
    metadata = load_metadata(user_id_str)

    classes = set()
    for data in metadata.values():
        for t in data.get("tags", []):
            classes.add(t)

    return {"classes": sorted(classes)}
