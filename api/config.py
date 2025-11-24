import os
import logging
from ultralytics import YOLO
from dotenv import load_dotenv
from google.cloud import storage
import google.auth
import torch
import os

print("🧩 Checking credentials path:", os.getenv("PROD_GOOGLE_APPLICATION_CREDENTIALS"))
print("🧩 File exists:", os.path.exists(os.getenv("PROD_GOOGLE_APPLICATION_CREDENTIALS")))

# =========================================================
# Load environment variables
# =========================================================
load_dotenv(override=True)

# =========================================================
# Base directory
# =========================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# =========================================================
# Logger setup
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
ENV = os.getenv("ENV", "DEV").upper()
logger.info(f"Running in {ENV} environment")

# =========================================================
# Shopify & Ngrok config
# =========================================================
SHOPIFY_STORE = os.getenv("SHOPIFY_STORE")
SHOPIFY_ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")  # corrected variable name
NGROK_AUTH_TOKEN = os.getenv("NGROK_AUTH_TOKEN")

# =========================================================
# Database configuration
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
        "host": os.getenv("PROD_DB_HOST"),
        "port": int(os.getenv("PROD_DB_PORT", 3306)),
        "user": os.getenv("PROD_DB_USER"),
        "password": os.getenv("PROD_DB_PASSWORD"),
        "database": os.getenv("PROD_DB_NAME", "shopify_store"),
    }

logger.info(f"Database host: {DB_CONFIG.get('host')}")

# =========================================================
# File storage setup
# =========================================================
UPLOAD_DIR = os.path.join(BASE_DIR, "uploaded_images")
os.makedirs(UPLOAD_DIR, exist_ok=True)

STORAGE_BACKEND = None
gcs_client = None
gcs_bucket = None
GCS_UPLOAD_DIR = "uploaded_images/"

# =========================================================
# Storage Backend Selection
# =========================================================
if ENV == "DEV":
    STORAGE_BACKEND = os.getenv("DEV_STORAGE_BACKEND", "local").lower()
    logger.info(f"Using LOCAL storage backend. Files will be saved in: {UPLOAD_DIR}")

else:  # PRODUCTION
    STORAGE_BACKEND = os.getenv("PROD_STORAGE_BACKEND", "gcs").lower()
    GCS_BUCKET_NAME = os.getenv("PROD_GCS_BUCKET_NAME")

    # Prefer Cloud Run’s mounted secret path first
    GCS_KEY_PATH = (
        os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        or os.getenv("PROD_GOOGLE_APPLICATION_CREDENTIALS")
    )

    if STORAGE_BACKEND == "gcs":
        try:
            if not GCS_BUCKET_NAME:
                raise ValueError("Missing PROD_GCS_BUCKET_NAME environment variable")

            if os.getenv("GOOGLE_CLOUD_PROJECT"):
                # Inside Google Cloud (Cloud Run, etc.)
                credentials, project = google.auth.default()
                gcs_client = storage.Client(credentials=credentials, project=project)
                logger.info("Connected using Cloud Run default credentials")
            elif GCS_KEY_PATH and os.path.exists(GCS_KEY_PATH):
                # Local environment using key file
                gcs_client = storage.Client.from_service_account_json(GCS_KEY_PATH)
                logger.info(f"Connected using service account JSON at {GCS_KEY_PATH}")
            else:
                raise FileNotFoundError(
                    f"No valid GCS credentials found. Path tried: {GCS_KEY_PATH}"
                )

            gcs_bucket = gcs_client.bucket(GCS_BUCKET_NAME)
            logger.info(f"Connected to GCS bucket: {GCS_BUCKET_NAME}")

            # Ensure uploaded_images folder exists remotely
            blobs = list(gcs_bucket.list_blobs(prefix=GCS_UPLOAD_DIR))
            if not blobs:
                placeholder = gcs_bucket.blob(GCS_UPLOAD_DIR + ".keep")
                placeholder.upload_from_string("")
                logger.info(f"Created remote folder: {GCS_UPLOAD_DIR}")
            else:
                logger.info(
                    f"Remote folder '{GCS_UPLOAD_DIR}' already exists with {len(blobs)} file(s)."
                )

        except Exception as e:
            logger.error(f"Failed to connect to GCS: {e}")
            gcs_client, gcs_bucket = None, None

    else:
        logger.info(f"Using LOCAL storage backend. Files will be saved in: {UPLOAD_DIR}")

# =========================================================
# YOLO model setup
# =========================================================
MODEL_PATH = os.path.join(BASE_DIR, "walidlife_models","best.pt")
logger.info(f"Loading YOLO model from {MODEL_PATH}")

try:
    model = YOLO(MODEL_PATH, task="detect")
    logger.info("YOLO model loaded successfully.")
except Exception as e:
    logger.error(f"Failed to load YOLO model: {e}")
    model = None

# =========================================================
# Allowed image formats
# =========================================================
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp"}
