import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = PROJECT_ROOT / ".env"

load_dotenv(dotenv_path=ENV_PATH)

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
LLM_MODEL = "llama-3.3-70b-versatile"
FAST_MODEL = "llama-3.1-8b-instant"

# Storage
# - Local dev default: ./chroma_db
# - Hugging Face Spaces persistent storage: usually mounted at /data (enable in Space settings)
CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", "./chroma_db")
COHERENCE_THRESHOLD = 0.90

# Swarm configuration
SWARM_MODE = os.getenv("SWARM_MODE", "1").lower() in {"1", "true", "yes", "on"}
SWARM_RUNTIME = os.getenv("SWARM_RUNTIME", "autonomous")  # "autonomous" or "sequential"
AUTOGEN_MAX_TURNS = int(os.getenv("AUTOGEN_MAX_TURNS", "8"))
AUTOGEN_AGENT_TIMEOUT_S = int(os.getenv("AUTOGEN_AGENT_TIMEOUT_S", "45"))

# Autonomous swarm settings
SWARM_MAX_WORKERS = int(os.getenv("SWARM_MAX_WORKERS", "3"))
SWARM_CONSENSUS_THRESHOLD = float(os.getenv("SWARM_CONSENSUS_THRESHOLD", "0.6"))
SWARM_MAX_NEGOTIATION_ROUNDS = int(os.getenv("SWARM_MAX_NEGOTIATION_ROUNDS", "3"))
SWARM_ENABLE_VISUALIZATION = os.getenv("SWARM_ENABLE_VISUALIZATION", "1").lower() in {"1", "true", "yes", "on"}
SWARM_ENABLE_NEGOTIATION = os.getenv("SWARM_ENABLE_NEGOTIATION", "1").lower() in {"1", "true", "yes", "on"}
