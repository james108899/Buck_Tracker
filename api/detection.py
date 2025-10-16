from flask import Blueprint, request, jsonify,url_for,send_from_directory
import cv2, uuid, os
import numpy as np
from datetime import datetime
import json ,hashlib ,mysql.connector

from PIL import Image, ExifTags   # for metadata
from io import BytesIO
from .utils import extract_metadata

from .config import (
    logger, UPLOAD_DIR, model, DB_CONFIG,
    gcs_bucket, GCS_UPLOAD_DIR, STORAGE_BACKEND, ALLOWED_EXTENSIONS
)

detection_bp = Blueprint("detection", __name__)

# DB connection (allow optional buffered cursor)
def get_db(buffered=False):
    conn = mysql.connector.connect(**DB_CONFIG)
    return conn, conn.cursor(dictionary=True, buffered=buffered)


# Serve uploaded images
@detection_bp.route("/uploads/<filename>")
def serve_upload(filename):
    return send_from_directory(UPLOAD_DIR, filename)

# ---------------- Image Upload & Detection ---------------- #
@detection_bp.route("/process-images", methods=["POST"])
def process_images():
    logger.info("New request to /process-images")
    try:
        user_id = request.form.get("user_id")
        if not user_id:
            return {"status": "error", "message": "user_id is required"}, 400

        if "images_batch" not in request.files:
            return {"status": "error", "message": "No images provided"}, 400

        images = request.files.getlist("images_batch")
        if not (1 <= len(images) <= 32):
            return {"status": "error", "message": "Upload between 1 and 32 images"}, 400

        results_list = []
        duplicates = []
        total_detections = 0
        conn, cursor = get_db()

        for img_file in images:
            file_bytes = img_file.read()
            file_hash = hashlib.md5(file_bytes).hexdigest()

            # Check duplicates
            cursor.execute("SELECT COUNT(*) AS cnt FROM user_detections WHERE user_id=%s AND metadata LIKE %s",
                           (user_id, f'%{file_hash}%'))
            if cursor.fetchone()["cnt"] > 0:
                duplicates.append(img_file.filename)
                continue

            filename = img_file.filename
            ext = os.path.splitext(filename)[1].lower()
            if ext not in ALLOWED_EXTENSIONS:
                return {"status": "error", "message": f"Unsupported file type '{ext}'"}, 400

            np_arr = np.frombuffer(file_bytes, np.uint8)
            frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
            metadata = extract_metadata(file_bytes)
            metadata["file_hash"] = file_hash

            # Run model
            results = model.predict(frame, verbose=False)
            boxes = results[0].boxes
            detections = []

            for box in boxes:
                cls = int(box.cls[0]) if hasattr(box, "cls") else 0
                conf = float(box.conf[0]) if hasattr(box, "conf") else 0.0
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                detected_class = model.names.get(cls, str(cls))
                detections.append({
                    "class": detected_class,
                    "conf": round(conf, 4),
                    "bbox": [x1, y1, x2, y2]
                })

                cursor.execute("""
                    INSERT INTO user_detections (user_id, image_name, detected_class, confidence, bbox, metadata)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (user_id, filename, detected_class, conf, json.dumps([x1, y1, x2, y2]), json.dumps(metadata)))
                total_detections += 1

            # Save image and generate URL
            if STORAGE_BACKEND == "local":
                save_path = os.path.join(UPLOAD_DIR, filename)
                cv2.imwrite(save_path, frame)
                full_url = url_for(f"{request.blueprint}.serve_upload", filename=filename, _external=True)


            elif STORAGE_BACKEND == "gcs" and gcs_bucket:
                _, buffer = cv2.imencode(ext, frame)
                blob = gcs_bucket.blob(GCS_UPLOAD_DIR + filename)
                blob.upload_from_string(buffer.tobytes(), content_type=f"image/{ext.strip('.')}")
                blob.make_public()
                full_url = blob.public_url

            results_list.append({
                "image_name": filename,
                "image_url": full_url,  #  full browser-accessible URL
                "timestamp": datetime.utcnow().isoformat(),
                "objects": detections,
                "metadata": metadata
            })

        conn.commit()
        conn.close()

        response = {
            "status": "success",
            "user_id": user_id,
            "images_processed": len(results_list),
            "total_detections": total_detections,
            "duplicates": duplicates,
            "results": results_list
        }
        if duplicates:
            response["message"] = f"Skipped {len(duplicates)} duplicate file(s)"

        return jsonify(response), 200

    except Exception as e:
        logger.error("Error processing images: %s", str(e), exc_info=True)
        return {"status": "error", "message": str(e)}, 500

# ---------------- User Tagged Images ---------------- #



@detection_bp.route("/user/<user_id>/tagged-images", methods=["GET"])
def user_tagged_images(user_id):
    try:
        page, limit = int(request.args.get("page", 1)), int(request.args.get("limit", 50))
        cls, offset = request.args.get("class"), (page - 1) * limit

        conn, cur = get_db()
        query = "SELECT image_name, detected_class, confidence, bbox, timestamp FROM user_detections WHERE user_id=%s"
        params = [user_id]
        if cls:
            query += " AND detected_class=%s"
            params.append(cls)
        query += " ORDER BY timestamp DESC LIMIT %s OFFSET %s"
        params += [limit, offset]

        cur.execute(query, params)
        rows = cur.fetchall()
        cur.close()
        conn.close()

        images = {}
        for r in rows:
            n = r["image_name"]
            if n not in images:
                images[n] = {
                        "image_name": n,
                        "image_url": url_for(".serve_upload", filename=n, _external=True),
                        "timestamp": r["timestamp"].isoformat() if r["timestamp"] else None,
                        "detections": []
                    }

            images[n]["detections"].append({
                "class": r["detected_class"],
                "confidence": float(r["confidence"]),
                "bbox": json.loads(r["bbox"]) if r["bbox"] else None
            })

        return jsonify({
            "user_id": user_id,
            "page": page,
            "limit": limit,
            "images": list(images.values())
        }), 200

    except Exception as e:
        logger.error(f"Error fetching tagged images for user {user_id}: {e}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500




# ---------------- Update detection class/bbox ---------------- #
@detection_bp.route("/user/<user_id>/update-detection", methods=["PATCH"])
def update_detection(user_id):
    try:
        data = request.get_json()
        image_name = data.get("image_name")
        detections = data.get("detections", [])

        if not image_name or not detections:
            return jsonify({"status": "error", "message": "image_name and detections required"}), 400

        conn, cur = get_db()

        # Check if image exists
        cur.execute("SELECT COUNT(*) AS cnt FROM user_detections WHERE user_id=%s AND image_name=%s",
                    (user_id, image_name))
        if cur.fetchone()["cnt"] == 0:
            cur.close(); conn.close()
            return jsonify({"status": "error", "message": "Image not found"}), 404

        # Update detections
        for det in detections:
            old_cls = det.get("old_class")
            new_cls = det.get("new_class", old_cls)
            bbox = det.get("bbox")

            cur.execute("""
                UPDATE user_detections
                SET detected_class=%s, bbox=%s
                WHERE user_id=%s AND image_name=%s AND detected_class=%s
            """, (new_cls, json.dumps(bbox), user_id, image_name, old_cls))

        conn.commit()
        cur.close(); conn.close()
        return jsonify({"status": "success", "message": "Detections updated"}), 200

    except Exception as e:
        logger.error(f"Error updating detection: {e}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500

# ---------------- Delete image ---------------- #
@detection_bp.route("/user/<user_id>/delete-image", methods=["DELETE"])
def delete_image(user_id):
    data = request.get_json()
    image_name = data.get("image_name")
    if not image_name:
        return jsonify({"status": "error", "message": "image_name is required"}), 400

    try:
        conn, cur = get_db(buffered=True)  # <-- buffered cursor
        # Check if image exists
        cur.execute("SELECT id FROM user_detections WHERE user_id=%s AND image_name=%s", (user_id, image_name))
        if not cur.fetchone():
            cur.close(); conn.close()
            return jsonify({"status": "error", "message": "Image not found"}), 404

        # Delete all records for that image
        cur.execute("DELETE FROM user_detections WHERE user_id=%s AND image_name=%s", (user_id, image_name))
        conn.commit()
        cur.close(); conn.close()

        # Optionally delete file if local storage
        file_path = os.path.join(UPLOAD_DIR, image_name)
        if os.path.exists(file_path):
            os.remove(file_path)

        return jsonify({"status": "success", "message": f"{image_name} deleted"}), 200

    except Exception as e:
        logger.error(f"Error deleting image {image_name}: {e}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500
