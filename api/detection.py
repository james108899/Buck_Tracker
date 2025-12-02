import warnings
warnings.filterwarnings("ignore", message="Corrupt JPEG data")
from flask_cors import cross_origin

from flask import Blueprint, request, jsonify,url_for,send_from_directory, make_response
import cv2, uuid, os
import numpy as np
from datetime import datetime,timedelta
import json ,hashlib ,mysql.connector
import google.auth

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
@cross_origin()

def serve_upload(filename):
    file_path = os.path.join(UPLOAD_DIR, filename)

    if not os.path.exists(file_path):
        return {"error": "File not found"}, 404

    response = make_response(send_from_directory(UPLOAD_DIR, filename))

    # Allow loading from ANY frontend (browser, local file, HTML page)
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    response.headers['Cache-Control'] = 'public, max-age=86400'

    # Required so <img src="..."> works
    response.headers['Content-Type'] = 'image/jpeg'

    return response

# ---------------- Image Upload & Detection ---------------- #
@detection_bp.route("/process-images", methods=["POST"])
def process_images():
    logger.info("New request to /process-images")

    try:
        if "images_batch" not in request.files:
            return {"status": "error", "message": "No images provided"}, 400

        images = request.files.getlist("images_batch")
        if not (1 <= len(images) <= 32):
            return {"status": "error", "message": "Upload between 1 and 32 images"}, 400

        results_list = []
        duplicates = []
        seen_hashes = set()
        total_detections = 0

        for img_file in images:
            file_bytes = img_file.read()
            file_hash = hashlib.md5(file_bytes).hexdigest()

            # Prevent duplicates inside same request
            if file_hash in seen_hashes:
                duplicates.append(img_file.filename)
                continue
            seen_hashes.add(file_hash)

            filename = img_file.filename
            ext = os.path.splitext(filename)[1].lower()
            if ext not in ALLOWED_EXTENSIONS:
                return {"status": "error",
                        "message": f"Unsupported file type '{ext}'"}, 400

            np_arr = np.frombuffer(file_bytes, np.uint8)
            frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

            # Run detection
            results = model.predict(frame, verbose=False)
            boxes = results[0].boxes

            detections = []
            txt_lines = []

            for box in boxes:
                cls = int(box.cls[0])
                conf = float(box.conf[0])
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                class_name = model.names.get(cls, str(cls))

                # For JSON response
                detections.append({
                    "class": class_name,
                    "conf": round(conf, 4),
                    "bbox": [x1, y1, x2, y2]
                })

                # --- TXT FILE CONTENT ---
                # CLASS NAME + BBOX ONLY
                txt_lines.append(f"{class_name} {x1} {y1} {x2} {y2}")

                # Draw bounding box on image
                cv2.rectangle(frame, (x1, y1), (x2, y2),
                              (0, 255, 0), 2)
                cv2.putText(frame, f"{class_name} {conf:.2f}",
                            (x1, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX,
                            0.6, (0, 255, 0), 2)

                total_detections += 1

            # Output filenames
            output_image_name = f"{os.path.splitext(filename)[0]}_det.jpg"
            txt_filename = f"{os.path.splitext(filename)[0]}.txt"

            # ===========================
            # LOCAL STORAGE
            # ===========================
            if STORAGE_BACKEND == "local":
                img_path = os.path.join(UPLOAD_DIR, output_image_name)
                cv2.imwrite(img_path, frame)

                # Save TXT only when detections exist
                if len(detections) > 0:
                    txt_path = os.path.join(UPLOAD_DIR, txt_filename)
                    with open(txt_path, "w") as f:
                        f.write("\n".join(txt_lines))

                full_url = url_for(f"{request.blueprint}.serve_upload",
                                   filename=output_image_name,
                                   _external=True)

            # ===========================
            # GOOGLE CLOUD STORAGE
            # ===========================
            elif STORAGE_BACKEND == "gcs" and gcs_bucket:
                credentials, _ = google.auth.default()

                # Upload image
                _, buffer = cv2.imencode(".jpg", frame)
                blob_img = gcs_bucket.blob(GCS_UPLOAD_DIR + output_image_name)
                blob_img.upload_from_string(buffer.tobytes(),
                                            content_type="image/jpeg")

                full_url = blob_img.generate_signed_url(
                    version="v2",
                    expiration=timedelta(days=7),
                    method="GET",
                    service_account_email="rizwan-deer-uploaded@deer-detection-system.iam.gserviceaccount.com",
                    credentials=credentials
                )

                # Upload TXT only if detections exist
                if len(detections) > 0:
                    blob_txt = gcs_bucket.blob(GCS_UPLOAD_DIR + txt_filename)
                    blob_txt.upload_from_string("\n".join(txt_lines),
                                                content_type="text/plain")

            # Final response object
            results_list.append({
                "image_name": output_image_name,
                "image_url": full_url,
                "objects": detections,
                "timestamp": datetime.utcnow().isoformat()
            })

        # Final JSON response
        response = {
            "status": "success",
            "images_processed": len(results_list),
            "total_detections": total_detections,
            "duplicates": duplicates,
            "results": results_list
        }

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
