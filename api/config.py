import os
import logging
from dotenv import load_dotenv
from ultralytics import YOLO
from google.cloud import storage
import google.auth

# ---------------- ENV ----------------
load_dotenv(override=True)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ---------------- LOGGER ----------------
LOG_FILE = os.path.join(BASE_DIR, "api.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()]
)

logger = logging.getLogger("WildlifeLogger")

ENV = os.getenv("ENV", "DEV").upper()
logger.info(f"Running in {ENV}")

# ---------------- STORAGE ----------------
UPLOAD_DIR = os.path.join(BASE_DIR, "user_data")
os.makedirs(UPLOAD_DIR, exist_ok=True)

STORAGE_BACKEND = "local"
gcs_client = None
gcs_bucket = None
GCS_UPLOAD_DIR = "uploaded_images/"

if ENV == "PROD":
    STORAGE_BACKEND = os.getenv("PROD_STORAGE_BACKEND", "gcs").lower()
    GCS_BUCKET_NAME = os.getenv("PROD_GCS_BUCKET_NAME")
    GCS_KEY_PATH = os.getenv("PROD_GOOGLE_APPLICATION_CREDENTIALS")

    if STORAGE_BACKEND == "gcs":
        try:
            if os.getenv("GOOGLE_CLOUD_PROJECT"):
                creds, project = google.auth.default()
                gcs_client = storage.Client(credentials=creds, project=project)
            else:
                gcs_client = storage.Client.from_service_account_json(GCS_KEY_PATH)

            gcs_bucket = gcs_client.bucket(GCS_BUCKET_NAME)
            logger.info(f"Connected to GCS bucket: {GCS_BUCKET_NAME}")

        except Exception as e:
            logger.error(f"GCS connection failed: {e}")
            STORAGE_BACKEND = "local"

# ---------------- UPLOAD RULES ----------------
MIN_IMAGES = 1
MAX_IMAGES = 1000
ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}

# ---------------- YOLO MODELS ----------------
try:
    logger.info("Loading YOLO models...")
    DETECT_MODEL = YOLO("api/walidlife_models/detect/deer.pt")
    BUCK_DOE_MODEL = YOLO("api/walidlife_models/classify/Buck_classificationt.pt", task="classify")
    BUCK_TYPE_MODEL = YOLO("api/walidlife_models/classify/mules_vs_whitetails.pt", task="classify")
    logger.info("YOLO models loaded")
except Exception as e:
    logger.error(f"YOLO load failed: {e}")
    DETECT_MODEL = BUCK_DOE_MODEL = BUCK_TYPE_MODEL = None
