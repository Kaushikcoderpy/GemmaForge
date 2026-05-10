import logging
import logging.handlers
import queue
from typing import Any


# Global state to prevent redundant initialization
_logger_instance = None
_listener = None


class AsyncLoggerWrapper:
    """
    Standard library implementation of a non-blocking logger.
    Uses QueueHandler + QueueListener to offload I/O to a background thread.
    Maintains 'async' methods for compatibility with the GemmaForge pipeline.
    """

    def __init__(self, name: str, filename: str):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.INFO)

        # Prevent adding handlers multiple times if get_logger is called repeatedly
        if not self.logger.handlers:
            log_queue = queue.Queue(-1)
            queue_handler = logging.handlers.QueueHandler(log_queue)
            self.logger.addHandler(queue_handler)

            # File and Console output with UTF-8 encoding support
            file_handler = logging.FileHandler(filename, encoding='utf-8')
            stream_handler = logging.StreamHandler()
            
            # Ensure stream handler doesn't crash on Windows consoles with limited character sets
            stream_handler.setStream(open(1, 'w', encoding='utf-8', closefd=False))

            formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
            file_handler.setFormatter(formatter)
            stream_handler.setFormatter(formatter)

            global _listener
            _listener = logging.handlers.QueueListener(log_queue, file_handler, stream_handler)
            _listener.start()

    async def info(self, msg: Any): self.logger.info(msg)

    async def error(self, msg: Any): self.logger.error(msg)

    async def warning(self, msg: Any): self.logger.warning(msg)

    async def debug(self, msg: Any): self.logger.debug(msg)

    async def critical(self, msg: Any): self.logger.critical(msg)


async def get_logger() -> AsyncLoggerWrapper:
    """
    Returns a singleton-like wrapper for the async logger.
    Avoids 'aiologger' installation issues on Python 3.13/Windows.
    """
    global _logger_instance
    if _logger_instance is None:
        _logger_instance = AsyncLoggerWrapper("gemmaforge", "gemmaforge.log")
    return _logger_instance