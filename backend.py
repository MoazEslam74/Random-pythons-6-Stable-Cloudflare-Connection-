
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import dotenv_values
import os

app = FastAPI()

# Enable CORS so the frontend can connect
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_current_api_url():
    """Read the .env file to get the latest URL."""
    # Use dotenv_values to force reading the file from disk each time
    config = dotenv_values(".env")
    return config.get("API_URL", "http://localhost:8000")

@app.get("/")
def read_root():
    current_url = get_current_api_url()
    return {
        "status": "online",
        "message": "Welcome from the backend!",
        "current_cloudflare_url": current_url
    }

@app.get("/get-url")
def get_url():
    """Endpoint for the frontend to ask for the current URL."""
    return {"url": get_current_api_url()}

if __name__ == "__main__":
    import uvicorn
    # Make sure the port matches the one configured in the Cloudflare script
    uvicorn.run("backend:app", host="127.0.0.1", port=8000, reload=True)