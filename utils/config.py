import os
import sys
import logging
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(dotenv_path=PROJECT_ROOT / ".env")

# ── Required — fail at startup, not mid-request ─────────────────────────────
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
if not GROQ_API_KEY:
    raise EnvironmentError(
        "GROQ_API_KEY is not set. "
        "Add it to .env or set it as an environment variable."
    )

# ── Models ───────────────────────────────────────────────────────────────────
LLM_MODEL  = os.getenv("LLM_MODEL",  "llama-3.3-70b-versatile")
FAST_MODEL = os.getenv("FAST_MODEL", "llama-3.1-8b-instant")

# ── Storage ──────────────────────────────────────────────────────────────────
LANCE_PERSIST_DIR = os.getenv("LANCE_PERSIST_DIR", "./lance_db")

# ── Search ───────────────────────────────────────────────────────────────────
JINA_BASE_URL   = "https://r.jina.ai/"
DDG_MAX_RESULTS = int(os.getenv("DDG_MAX_RESULTS", "10"))
JINA_TIMEOUT_S  = int(os.getenv("JINA_TIMEOUT_S",  "20"))
# Delay between fetching each search result URL (politeness; lower = faster runs)
SEARCH_POLITE_DELAY_S = float(os.getenv("SEARCH_POLITE_DELAY_S", "0.15"))

# ── Swarm ────────────────────────────────────────────────────────────────────
SWARM_MAX_NEGOTIATION_ROUNDS = int(os.getenv("SWARM_MAX_NEGOTIATION_ROUNDS", "3"))
MAX_RESEARCH_ITERATIONS      = int(os.getenv("MAX_RESEARCH_ITERATIONS",      "2"))
MAX_CRITIQUE_REVISIONS       = int(os.getenv("MAX_CRITIQUE_REVISIONS",       "2"))
SWARM_ENABLE_VISUALIZATION   = os.getenv("SWARM_ENABLE_VISUALIZATION", "1").lower() in {"1", "true", "yes", "on"}
COHERENCE_THRESHOLD          = float(os.getenv("COHERENCE_THRESHOLD", "0.75"))
# See memory/models.py — skip CrossEncoder rerank when 1/true (low-RAM / small page file).
SWARMIQ_DISABLE_RERANK       = os.getenv("SWARMIQ_DISABLE_RERANK", "").lower() in {"1", "true", "yes", "on"}

# ── Rate limiting ─────────────────────────────────────────────────────────────
GROQ_RPM_LIMIT = int(os.getenv("GROQ_RPM_LIMIT", "25"))
GROQ_TPM_LIMIT = int(os.getenv("GROQ_TPM_LIMIT", "10000"))

# ── Logging ───────────────────────────────────────────────────────────────────
# Use stdout so PowerShell does not treat every log line as NativeCommandError when using 2>&1.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
    force=True,
)
