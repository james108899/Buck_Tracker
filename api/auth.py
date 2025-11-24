from flask import Blueprint, jsonify

auth_bp = Blueprint("auth", __name__)

@auth_bp.route("/status", methods=["GET"])
def status():
    # Simple auth placeholder
    return jsonify({"status": "success", "message": "Auth blueprint active"}), 200
