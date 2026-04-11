"""Entrypoint — launches the FastAPI server."""

import os
import uvicorn

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("api.server:app", host="0.0.0.0", port=port)
