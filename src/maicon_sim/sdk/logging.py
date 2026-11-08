"""Keep credentials out of the HTTP transport's standard-library logs."""
import logging
import re


class MissionCodeFilter(logging.Filter):
    def filter(self, record):
        # httpx INFO messages include the complete URL. The public protocol
        # requires this query parameter, so redact it before handlers format it.
        message = record.getMessage()
        message = re.sub(r"(?i)(mission_code=)[^&\s\"']+", r"\1[REDACTED]", message)
        record.msg, record.args = message, ()
        return True


def protect_transport_logs():
    logger = logging.getLogger("httpx")
    if not any(isinstance(item, MissionCodeFilter) for item in logger.filters):
        logger.addFilter(MissionCodeFilter())
