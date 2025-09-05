from contextvars import ContextVar
from typing import Optional

# Context variable to hold the trace ID for a given request/task chain.
# The default value is None, indicating no trace ID is set.
trace_id_var: ContextVar[Optional[str]] = ContextVar("trace_id", default=None)
