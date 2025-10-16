from api import create_app
from pyngrok import ngrok
from dotenv import load_dotenv
import os
from flask_cors import CORS
# Load environment variables from .env
load_dotenv()
NGROK_AUTH_TOKEN = os.getenv("NGROK_AUTH_TOKEN")

# Set ngrok auth token correctly
if NGROK_AUTH_TOKEN:
    ngrok.set_auth_token(NGROK_AUTH_TOKEN)

app = create_app()


if __name__ == "__main__":
    # # Open a public ngrok tunnel to the Flask app
    # public_url = ngrok.connect(5000)
    # print(f" * ngrok tunnel \"{public_url}\" -> \"http://127.0.0.1:5000\"")

    # Run the Flask app
    app.run(host="0.0.0.0", port=5000, debug=False)
