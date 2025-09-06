"""
Custom Prometheus metrics for the application.
"""
from prometheus_client import Counter, Histogram

# A counter to track the total number of LLM calls, labeled by provider and outcome.
LLM_CALLS_TOTAL = Counter(
    "origin_llm_calls_total",
    "Total number of LLM calls",
    ["provider", "outcome"] # outcome can be "success" or "failure"
)

# A histogram to track the latency of LLM calls, labeled by provider.
LLM_LATENCY_SECONDS = Histogram(
    "origin_llm_latency_seconds",
    "Latency of LLM calls in seconds",
    ["provider"]
)

# A counter for total tokens used, labeled by provider and kind (prompt/completion).
LLM_TOKENS_TOTAL = Counter(
    "origin_tokens_total",
    "Total number of tokens used in LLM calls",
    ["provider", "kind"] # kind can be "prompt" or "completion"
)

# A histogram to track the latency of database queries.
DB_QUERY_DURATION = Histogram(
    "origin_db_query_duration_seconds",
    "Duration of database queries in seconds",
    ["query_type"] # e.g., "read", "write"
)

# A gauge to track process memory usage.
from prometheus_client import Gauge
MEMORY_USAGE = Gauge(
    "origin_memory_usage_bytes",
    "Memory usage of the application process in bytes"
)

# --- Conversation Feature Metrics ---

# A gauge for active SSE sessions
SSE_SESSIONS_ACTIVE = Gauge(
    "origin_sse_sessions_active",
    "Number of active SSE sessions"
)

# A counter for total conversation costs
CONVO_COST_USD_TOTAL = Counter(
    "origin_convo_cost_usd_total",
    "Total estimated cost of conversations in USD"
)
