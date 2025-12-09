import os
import json
import cv2
import numpy as np
from datetime import timedelta

from .config import (
    gcs_bucket, GCS_UPLOAD_DIR, STORAGE_BACKEND, UPLOAD_DIR
)

# =========================================================
# PATH HELPERS
# =========================================================
def get_user_paths(user_id: str):
    local_root = os.path.join(UPLOAD_DIR, "users", user_id)
    local_metadata = os.path.join(local_root, "metadata.json")

    gcs_prefix = f"{GCS_UPLOAD_DIR}users/{user_id}/"
    gcs_metadata = f"{gcs_prefix}metadata.json"

    return local_root, local_metadata, gcs_prefix, gcs_metadata


# =========================================================
# METADATA HELPERS
# =========================================================
def load_metadata(user_id: str) -> dict:
    local_root, local_meta, gcs_prefix, gcs_meta = get_user_paths(user_id)

    if STORAGE_BACKEND == "local":
        if not os.path.exists(local_meta):
            return {}
        with open(local_meta, "r") as f:
            return json.load(f)

    elif STORAGE_BACKEND == "gcs" and gcs_bucket:
        blob = gcs_bucket.blob(gcs_meta)
        if not blob.exists():
            return {}
        return json.loads(blob.download_as_text())

    return {}


def save_metadata(user_id: str, metadata: dict):
    local_root, local_meta, gcs_prefix, gcs_meta = get_user_paths(user_id)

    if STORAGE_BACKEND == "local":
        os.makedirs(local_root, exist_ok=True)
        with open(local_meta, "w") as f:
            json.dump(metadata, f, indent=2)

    elif STORAGE_BACKEND == "gcs" and gcs_bucket:
        blob = gcs_bucket.blob(gcs_meta)
        blob.upload_from_string(
            json.dumps(metadata, indent=2),
            content_type="application/json"
        )


# =========================================================
# IMAGE SAVE + URL
# =========================================================
def save_image_and_get_url(user_id: str, filename: str, rgb_image, base_url: str):
    local_root, _, gcs_prefix, _ = get_user_paths(user_id)

    if STORAGE_BACKEND == "local":
        os.makedirs(local_root, exist_ok=True)
        save_path = os.path.join(local_root, filename)
        rgb_image.save(save_path)

        return f"{base_url}/api/detection/uploads/{user_id}/{filename}"

    elif STORAGE_BACKEND == "gcs" and gcs_bucket:
        _, buffer = cv2.imencode(".jpg", cv2.cvtColor(np.array(rgb_image), cv2.COLOR_RGB2BGR))
        blob_img = gcs_bucket.blob(gcs_prefix + filename)

        blob_img.upload_from_string(
            buffer.tobytes(),
            content_type="image/jpeg"
        )

        return blob_img.generate_signed_url(
            version="v2",
            expiration=timedelta(days=7),
            method="GET"
        )

    return None


# =========================================================
# IMAGE URL RESOLVE
# =========================================================
def get_image_url(user_id: str, filename: str, base_url: str):
    _, _, gcs_prefix, _ = get_user_paths(user_id)

    if STORAGE_BACKEND == "local":
        return f"{base_url}/api/detection/uploads/{user_id}/{filename}"

    elif STORAGE_BACKEND == "gcs" and gcs_bucket:
        blob_img = gcs_bucket.blob(gcs_prefix + filename)
        return blob_img.generate_signed_url(
            version="v2",
            expiration=timedelta(days=7),
            method="GET"
        )

    return None
