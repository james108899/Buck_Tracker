from flask import Blueprint, request, jsonify
import mysql.connector
from .config import DB_CONFIG, logger
from collections import defaultdict

analytics_bp = Blueprint("analytics", __name__)

# DB connection helper
def get_db():
    conn = mysql.connector.connect(**DB_CONFIG)
    return conn, conn.cursor(dictionary=True)
# ---------------- Per-user dashboard (with granularity filters) ---------------- #
@analytics_bp.route("/user/<user_id>/dashboard", methods=["GET"])
def user_dashboard(user_id):
    """
    Returns simplified dashboard analytics for a specific user:
    - Total images uploaded
    - Total detections
    - Detection distribution (by class)
    - Top 5 detection classes
    - 5 highest detections by location (camera from metadata)
    """

    try:
        conn, cursor = get_db()

        # ---------------- Totals ---------------- #
        cursor.execute("""
            SELECT COUNT(DISTINCT image_name) AS total_images,
                   COUNT(*) AS total_detections
            FROM user_detections
            WHERE user_id=%s
        """, (user_id,))
        totals = cursor.fetchone()

        # ---------------- Detection Distribution (all classes) ---------------- #
        cursor.execute("""
            SELECT detected_class, COUNT(*) AS count
            FROM user_detections
            WHERE user_id=%s
            GROUP BY detected_class
            ORDER BY count DESC
        """, (user_id,))
        detection_distribution = cursor.fetchall()

        # ---------------- Top 5 Class Detections ---------------- #
        cursor.execute("""
            SELECT detected_class, COUNT(*) AS count
            FROM user_detections
            WHERE user_id=%s
            GROUP BY detected_class
            ORDER BY count DESC
            LIMIT 5
        """, (user_id,))
        top_classes = cursor.fetchall()

        # ---------------- 5 Highest Detections by Location ---------------- #
        cursor.execute("""
            SELECT JSON_UNQUOTE(JSON_EXTRACT(metadata, '$.camera')) AS location,
                   COUNT(*) AS count
            FROM user_detections
            WHERE user_id=%s
              AND JSON_EXTRACT(metadata, '$.camera') IS NOT NULL
            GROUP BY location
            ORDER BY count DESC
            LIMIT 5
        """, (user_id,))
        top_locations = cursor.fetchall()

        cursor.close()
        conn.close()

        return jsonify({
            "user_id": user_id,
            "total_images": totals["total_images"],
            "total_detections": totals["total_detections"],
            "detection_distribution": detection_distribution,
            "top_classes": top_classes,
            "top_locations": top_locations
        }), 200

    except Exception as e:
        logger.error(f"Error building dashboard for user {user_id}: {e}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500
