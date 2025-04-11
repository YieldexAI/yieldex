"""
Модуль настройки логирования сервиса оптимизации доходности.

Предоставляет функции для создания и настройки логгеров,
которые будут использоваться в различных компонентах сервиса.
"""

import os
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional, Dict, Any, Union


def setup_logger(
    logger_name: str,
    log_level: Union[str, int] = logging.INFO,
    log_file: Optional[str] = None,
    console: bool = True,
    log_format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    max_bytes: int = 10485760,  # 10 MB
    backup_count: int = 5,
) -> logging.Logger:
    """
    Настраивает и возвращает логгер с указанными параметрами.

    Args:
        logger_name (str): Имя логгера.
        log_level (Union[str, int]): Уровень логирования (строка или константа из logging).
        log_file (Optional[str]): Путь к файлу логов. Если None, логи будут только в консоль.
        console (bool): Включить вывод логов в консоль.
        log_format (str): Формат логов.
        max_bytes (int): Максимальный размер файла логов в байтах.
        backup_count (int): Количество файлов для ротации.

    Returns:
        logging.Logger: Настроенный логгер.
    """
    # Преобразование строкового уровня логирования в константу
    if isinstance(log_level, str):
        log_level = getattr(logging, log_level.upper(), logging.INFO)

    logger = logging.getLogger(logger_name)
    logger.setLevel(log_level)

    # Очищаем предыдущие обработчики
    logger.handlers = []

    formatter = logging.Formatter(log_format)

    # Обработчик для файла (если указан)
    if log_file:
        # Создаем директорию для логов, если её нет
        log_dir = os.path.dirname(log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)

        file_handler = RotatingFileHandler(
            log_file, maxBytes=max_bytes, backupCount=backup_count
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    # Обработчик для консоли (если включен)
    if console:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    return logger


def setup_service_logger(config: Dict[str, Any]) -> logging.Logger:
    """
    Настраивает основной логгер сервиса на основе конфигурации.

    Args:
        config (Dict[str, Any]): Словарь конфигурации.

    Returns:
        logging.Logger: Настроенный логгер.
    """
    log_level = config.get("log_level", "INFO")
    log_file = config.get("log_file")

    # Если путь к файлу логов не указан, но указана директория логов
    if not log_file and "log_dir" in config:
        log_dir = config["log_dir"]
        # Создаем директорию, если её нет
        Path(log_dir).mkdir(parents=True, exist_ok=True)
        # Формируем путь к файлу логов
        log_file = os.path.join(log_dir, "yield_optimizer.log")

    return setup_logger(
        logger_name="yield_optimizer",
        log_level=log_level,
        log_file=log_file,
        console=config.get("console_logs", True),
        log_format=config.get(
            "log_format", "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        ),
        max_bytes=config.get("log_max_bytes", 10485760),
        backup_count=config.get("log_backup_count", 5),
    )
