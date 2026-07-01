import sys
from loguru import logger

from config.settings import settings

logger.remove()

logger.add(
    sys.stderr,
    level=settings.log_level,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}",
    colorize=True,
)

logger.add(
    "logs/freki_{time:YYYY-MM-DD}.log",
    level="DEBUG",
    rotation="00:00",
    retention="30 days",
    compression="gz",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{line} - {message}",
)

log = logger
