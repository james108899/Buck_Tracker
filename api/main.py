from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

from .detection import router as detection_router
from .auth import router as auth_router

logger = logging.getLogger("ServerLogger")
logging.basicConfig(level=logging.INFO)

def create_app() -> FastAPI:
    app = FastAPI(title="Your API Server")

    # ---- CORS Configuration ----
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "https://www.daleandcompany.com",
            "http://127.0.0.1:8000",
            "null"
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ---- Include Routers (Blueprint equivalents) ----
    app.include_router(detection_router, prefix="/api/detection", tags=["Detection"])
    app.include_router(auth_router, prefix="/auth", tags=["Auth"])

    # ---- Health Check  ----
    @app.on_event("startup")
    async def startup_check():
        logger.info("Auth router is active. Server health check passed.")

    return app

# Used by uvicorn
app = create_app()
