from flask import Flask, Blueprint
from flask_cors import CORS
from .detection import detection_bp
from .webhook import webhook_bp
from .analytics import analytics_bp
import logging

logger = logging.getLogger("ServerLogger")
logging.basicConfig(level=logging.INFO)

api_bp = Blueprint("api", __name__)  # main API blueprint

# Register sub-blueprints under the API blueprint
api_bp.register_blueprint(detection_bp, url_prefix="/detection")
api_bp.register_blueprint(webhook_bp, url_prefix="/webhook")
api_bp.register_blueprint(analytics_bp, url_prefix="/analytics")


def create_app():
    app = Flask(__name__)
    CORS(app,resources={r"/*": {"origins": [
    "https://www.daleandcompany.com",    # your Shopify store
    "http://127.0.0.1:5000"              # local Flask
]}})

    # Register main API blueprint
    app.register_blueprint(api_bp, url_prefix="/api")

    # Optional: check that auth is working
    from .auth import auth_bp
    app.register_blueprint(auth_bp, url_prefix="/auth")
    with app.test_client() as client:
        resp = client.get("/auth/status")
        if resp.status_code != 200:
            raise RuntimeError(f"Auth blueprint failed health check! Status: {resp.status_code}")
        else:
            logger.info("Auth blueprint is active. Server health check passed.")

    return app
