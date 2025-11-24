from flask import Blueprint, request, jsonify
import json
import mysql.connector
from .config import logger,DB_CONFIG, SHOPIFY_STORE, SHOPIFY_ACCESS_TOKEN  # import from config

webhook_bp = Blueprint("webhook", __name__)

# ---------------- DB Connection ---------------- #
try:
    db = mysql.connector.connect(**DB_CONFIG)
    cursor = db.cursor()
    logger.info("Connected to MySQL database successfully.")
except Exception as e:
    logger.error(f"Database connection failed: {e}")
    raise


# ---------------- Webhook: New or updated customer ---------------- #
@webhook_bp.route("/customers", methods=["POST"])
def customers_webhook():
    try:
        data = request.get_json()
        logger.info(f"Webhook received: {json.dumps(data)}")

        #  Insert only the required fields
        sql = """
        INSERT INTO customers (shopify_id, email, first_name, last_name)
        VALUES (%s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            first_name = VALUES(first_name),
            last_name = VALUES(last_name),
            updated_at = CURRENT_TIMESTAMP
        """
        values = (
            data["id"],
            data.get("email"),
            data.get("first_name"),
            data.get("last_name"),
        )
        cursor.execute(sql, values)
        db.commit()
        logger.info(f"Customer {data.get('email')} added or updated successfully.") 
        return "ok", 200

    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        return jsonify({"error": str(e)}), 500