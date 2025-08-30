import json
import logging
from datetime import datetime

class JSONFormatter(logging.Formatter):
    """
    Custom formatter to output log records as a JSON string.
    """
    def format(self, record: logging.LogRecord) -> str:
        log_object = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage(),
            "trace_id": getattr(record, 'trace_id', None),
        }
        # Add exception info if it exists
        if record.exc_info:
            log_object['exc_info'] = self.formatException(record.exc_info)

        return json.dumps(log_object)

LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "app.utils.logging_config.JSONFormatter",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
            "stream": "ext://sys.stdout",
        },
    },
    "root": {
        "level": "INFO",
        "handlers": ["console"],
    },
}
