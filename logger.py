import logging
import os
import queue

from constants import LOG_FILE
log_queue = queue.Queue()

class QueueLogHandler(logging.Handler):
    def emit(self, record):
        msg = self.format(record)
        print("QUEUE:", msg)   # 👈 DEBUG
        log_queue.put(msg)

def configure_logging():

    os.makedirs("logs", exist_ok=True)

    logger = logging.getLogger()      # ROOT LOGGER
    logger.setLevel(logging.INFO)

    # 🔥 CRITICAL: remove existing handlers
    logger.handlers.clear()

    formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(message)s"
    )

    file_handler = logging.FileHandler("logs/app.log")
    file_handler.setFormatter(formatter)

    queue_handler = QueueLogHandler()
    queue_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(queue_handler)

def log_info(msg):
    logging.getLogger().info(msg)

def log_error(msg):
    logging.getLogger().error(msg)
