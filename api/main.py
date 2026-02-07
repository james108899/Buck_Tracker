# main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import logging
from pathlib import Path

# ----------------- Import Routers -----------------
from .detection import router as detection_router
from .auth import router as auth_router
from .camera import router as camera_router  # Camera router
from .config import UPLOAD_DIR  # Folder where images are saved
from .analytics import router as analytics_router
from .view_image import router as view_images_router
# ---------------- Logging Setup -----------------
logger = logging.getLogger("ServerLogger")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)

# Ensure UPLOAD_DIR exists
Path(UPLOAD_DIR).mkdir(parents=True, exist_ok=True)

# ---------------- Create App -----------------
def create_app() -> FastAPI:
    app = FastAPI(title="Wildlife Detection & Camera API Server")

    # ---- CORS Configuration ----
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            'https://embroiderywala.myshopify.com',
            'https://www.daleandcompany.com','http://127.0.0.1:8080'
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ---- Mount static folder for uploaded images ----
    app.mount("/user_data", StaticFiles(directory=UPLOAD_DIR), name="user_data")
    logger.info(f"Static folder mounted at /user_data -> {UPLOAD_DIR}")

    # ---- Include Routers ----
    app.include_router(auth_router, prefix="/auth", tags=["Auth"])
    app.include_router(camera_router, prefix="/api", tags=["Camera"])
    app.include_router(detection_router, prefix="/api/detection", tags=["Detection"])
    app.include_router(analytics_router,prefix="/api", tags=["Analytics"])
    app.include_router(view_images_router, prefix="/api", tags=["Images"])

    # ---- Health Check / Startup Event ----
    @app.on_event("startup")
    async def startup_check():
        logger.info("Server started successfully. All routers are active.")

    # ---- Root Endpoint ----
    @app.get("/")
    def root():
        return {
            "message": "Wildlife Detection & Camera API Server is Running",
            "routes": {
                "auth": "/auth/...",
                "camera": "/api/camera/...",
                "detection": "/api/detection/...",
                "analytics": "/api/analytics/..."

            }
        }

    return app

app = create_app()
