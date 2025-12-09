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
    # Optional ngrok tunnel
    # public_url = ngrok.connect(8080)
    # print(f' * ngrok tunnel "{public_url}" -> "http://127.0.0.1:8080"')

    # Run FastAPI
    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=8080,
        reload=True,
        log_level="info"
    )
