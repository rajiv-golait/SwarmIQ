import os
import time
import threading
import logging
from collections import deque

logger = logging.getLogger(__name__)


class TokenBucketRateLimiter:
    """Thread-safe token bucket for shared Groq API endpoint.

    All swarm agents share this singleton. Prevents cascading 429s
    when parallel branches hit the same rate limit simultaneously.
    """

    def __init__(self, rpm_limit: int, tpm_limit: int):
        self.rpm_limit = rpm_limit
        self.tpm_limit = tpm_limit
        self._request_times: deque = deque()
        self._token_counts:  deque = deque()
        self._lock = threading.Lock()

    def wait_if_needed(self, estimated_tokens: int = 1_500) -> None:
        with self._lock:
            now    = time.time()
            cutoff = now - 60.0

            while self._request_times and self._request_times[0] < cutoff:
                self._request_times.popleft()
                self._token_counts.popleft()

            if len(self._request_times) >= self.rpm_limit:
                wait = 60.0 - (now - self._request_times[0]) + 0.5
                if wait > 0:
                    logger.warning(f"RPM limit — waiting {wait:.1f}s")
                    time.sleep(wait)

            if sum(self._token_counts) + estimated_tokens > self.tpm_limit:
                logger.warning("TPM limit approaching — waiting 3s")
                time.sleep(3.0)

            self._request_times.append(time.time())
            self._token_counts.append(estimated_tokens)


def _make_limiter() -> TokenBucketRateLimiter:
    return TokenBucketRateLimiter(
        rpm_limit=int(os.getenv("GROQ_RPM_LIMIT", "25")),
        tpm_limit=int(os.getenv("GROQ_TPM_LIMIT", "10000")),
    )


# Module-level singleton — initialized on first import
groq_limiter: TokenBucketRateLimiter = _make_limiter()
