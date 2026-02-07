import warnings
warnings.filterwarnings("ignore", message="Corrupt JPEG data")

import os
from dotenv import load_dotenv
from pyngrok import ngrok
import uvicorn

load_dotenv()
NGROK_AUTH_TOKEN = os.getenv("NGROK_AUTH_TOKEN")

if NGROK_AUTH_TOKEN:
    ngrok.set_auth_token(NGROK_AUTH_TOKEN)



if __name__ == "__main__":

    #     # Run FastAPI
    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=7860,
        reload=True,
        log_level="info"
    )
