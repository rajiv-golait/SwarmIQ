from datetime import datetime, timezone
from urllib.parse import urlparse

_TIER_1 = {
    ".gov", ".edu", "who.int", "un.org", "nature.com",
    "science.org", "pubmed.ncbi.nlm.nih.gov", "arxiv.org",
    "nih.gov", "worldbank.org", "imf.org",
}
_TIER_2 = {
    "reuters.com", "bbc.com", "apnews.com", "ft.com",
    "economist.com", "theguardian.com", "nytimes.com",
    "wsj.com", "bloomberg.com", "thehindu.com",
}
_TIER_3 = {".org"}


def authority_score(source_url: str) -> float:
    if not source_url:
        return 0.4
    try:
        domain = urlparse(source_url).netloc.lower()
        if any(t in domain for t in _TIER_1):
            return 0.9
        if any(t in domain for t in _TIER_2):
            return 0.8
        if any(t in domain for t in _TIER_3):
            return 0.7
        return 0.5
    except Exception:
        return 0.4


def recency_score(published_date: str) -> float:
    if not published_date:
        return 0.5
    try:
        pub = datetime.fromisoformat(
            published_date.replace("Z", "+00:00")
        ).replace(tzinfo=timezone.utc)
        age_days = (datetime.now(timezone.utc) - pub).days
        if age_days < 90:   return 1.0
        if age_days < 365:  return 0.8
        if age_days < 1095: return 0.6
        return 0.4
    except Exception:
        return 0.5


def compute_confidence(source_url: str, published_date: str) -> float:
    """Composite confidence from authority and recency only.

    Semantic score removed — was always a hardcoded 0.6 placeholder
    which made the function output meaningless. Honest 2-factor score
    is better than a fake 3-factor score.

    Weights: authority 60%, recency 40%
    """
    auth = authority_score(source_url)
    rec  = recency_score(published_date)
    return round(0.60 * auth + 0.40 * rec, 3)
