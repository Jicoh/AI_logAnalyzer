"""日志工具模块"""

import logging
import sys


def get_logger(name: str = 'ai_log_analyzer') -> logging.Logger:
    """
    获取日志器

    Args:
        name: 日志器名称，默认为 'ai_log_analyzer'

    Returns:
        logging.Logger: 配置好的日志器
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter('[%(levelname)s] %(asctime)s %(name)s: %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    return logger