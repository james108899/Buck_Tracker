import os
import logging
from ultralytics import YOLO
from dotenv import load_dotenv
from google.cloud import storage
import torch

# =========================================================
# Load environment variables
# =========================================================
load_dotenv(override=True)

# =========================================================
# Base directory (api folder)
# =========================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# =========================================================
# Logger configuration
# =========================================================
LOG_FILE = os.path.join(BASE_DIR, "api.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("WildlifeLogger")
logger.setLevel(logging.INFO)

# =========================================================
# Environment selection
# =========================================================
ENV = os.getenv("ENV", "DEV").upper()  # DEV or PRODUCTION
logger.info("Running in %s environment", ENV)

# =========================================================
# Shopify config
# =========================================================
SHOPIFY_STORE = os.getenv("SHOPIFY_STORE")
SHOPIFY_ACCESS_TOKEN = os.getenv("SHOPIFY_ACCESS_TOKEN")
NGROK_AUTH_TOKEN = os.getenv("NGROK_AUTH_TOKEN")

# =========================================================
# Database config
# =========================================================
if ENV == "DEV":
    DB_CONFIG = {
        "host": os.getenv("DEV_DB_HOST", "localhost"),
        "user": os.getenv("DEV_DB_USER", "root"),
        "password": os.getenv("DEV_DB_PASSWORD", ""),
        "database": os.getenv("DEV_DB_NAME", "shopify_store"),
    }
else:  # PRODUCTION
    DB_CONFIG = {
        "host": os.getenv("PROD_DB_HOST", "localhost"),
        "user": os.getenv("PROD_DB_USER", "root"),
        "password": os.getenv("PROD_DB_PASSWORD", ""),
        "database": os.getenv("PROD_DB_NAME", "shopify_store"),
    }

logger.info("Database host: %s", DB_CONFIG["host"])

# =========================================================
# Storage configuration
# =========================================================
UPLOAD_DIR = os.path.join(BASE_DIR, "uploaded_images")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Define placeholders so imports don’t break
gcs_client = None
gcs_bucket = None
GCS_UPLOAD_DIR = "uploaded_images/"

if ENV == "DEV":
    STORAGE_BACKEND = os.getenv("DEV_STORAGE_BACKEND", "local").lower()
    logger.info("Using LOCAL storage backend. Files will be saved in: %s", UPLOAD_DIR)

else:  # PRODUCTION
    STORAGE_BACKEND = os.getenv("PROD_STORAGE_BACKEND", "gcs").lower()
    GCS_KEY_PATH = os.getenv("PROD_GOOGLE_APPLICATION_CREDENTIALS")
    GCS_BUCKET_NAME = os.getenv("PROD_GCS_BUCKET_NAME")

    if STORAGE_BACKEND == "gcs":
        logger.info("Using GCS backend")
        try:
            if not GCS_KEY_PATH or not os.path.exists(GCS_KEY_PATH):
                raise FileNotFoundError(f"Invalid GCS key path: {GCS_KEY_PATH}")
            if not GCS_BUCKET_NAME:
                raise ValueError("Missing PROD_GCS_BUCKET_NAME in .env")

            gcs_client = storage.Client.from_service_account_json(GCS_KEY_PATH)
            gcs_bucket = gcs_client.bucket(GCS_BUCKET_NAME)

            # Ensure uploaded_images/ exists remotely
            blobs = list(gcs_bucket.list_blobs(prefix=GCS_UPLOAD_DIR))
            if not blobs:
                placeholder = gcs_bucket.blob(GCS_UPLOAD_DIR + ".keep")
                placeholder.upload_from_string("")
                logger.info("Created remote folder: %s", GCS_UPLOAD_DIR)
            else:
                logger.info(
                    "Remote folder '%s' already exists with %d file(s).",
                    GCS_UPLOAD_DIR, len(blobs)
                )

            logger.info("Connected to GCS bucket: %s", GCS_BUCKET_NAME)

        except Exception as e:
            logger.error("Failed to connect to GCS: %s", e)
    else:
        logger.info("Using LOCAL storage backend. Files will be saved in: %s", UPLOAD_DIR)

# =========================================================
# YOLO model loading
# =========================================================
MODEL_PATH = os.path.join(BASE_DIR, "walidlife_models", "best_deer_detection_openvino_model")
logger.info("Loading YOLO model from %s", MODEL_PATH)

try:
    model = YOLO(MODEL_PATH, task="detect")
    # model.to("cpu")
    logger.info("YOLO model loaded successfully.")
except Exception as e:
    logger.error("Failed to load YOLO model: %s", e)
    model = None


# =========================================================image# Allowed image types
# =========================================================

# Allowed image types
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp"}
