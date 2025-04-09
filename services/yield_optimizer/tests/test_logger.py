"""
Тесты для модуля logger.py из пакета yield_optimizer.
"""

import os
import tempfile
import unittest
import logging
import shutil
from logging.handlers import RotatingFileHandler
from pathlib import Path

from src.yield_optimizer.logger import setup_logger, setup_service_logger

class TestLogger(unittest.TestCase):
    """Тесты для функций логирования."""
    
    def setUp(self):
        """Подготовка к тестам."""
        # Создаем временную директорию для логов
        self.log_dir = tempfile.mkdtemp()
        self.log_file = os.path.join(self.log_dir, 'test.log')
        
        # Запоминаем исходных логгеров, чтобы восстановить их после тестов
        self.root_handlers = logging.root.handlers.copy()
        self.logger_manager = {}
        for name in logging.root.manager.loggerDict.keys():
            logger = logging.getLogger(name)
            self.logger_manager[name] = logger.handlers.copy()
    
    def tearDown(self):
        """Очистка после тестов."""
        # Безопасно удаляем временную директорию со всем содержимым
        try:
            shutil.rmtree(self.log_dir)
        except Exception as e:
            print(f"Warning: Failed to remove temp directory: {e}")
        
        # Восстанавливаем исходных логгеров
        logging.root.handlers = self.root_handlers
        for name, handlers in self.logger_manager.items():
            logger = logging.getLogger(name)
            logger.handlers = handlers
    
    def test_setup_logger_file_only(self):
        """Тест настройки логгера только с выводом в файл."""
        logger_name = 'test_file_only'
        logger = setup_logger(logger_name, log_file=self.log_file, console=False)
        
        # Проверяем, что создан логгер с правильным именем
        self.assertEqual(logger.name, logger_name)
        
        # Проверяем, что у логгера один обработчик (файловый)
        self.assertEqual(len(logger.handlers), 1)
        self.assertIsInstance(logger.handlers[0], RotatingFileHandler)
        
        # Проверяем, что файл логов создан
        self.assertTrue(os.path.exists(self.log_file))
        
        # Пишем тестовое сообщение в лог
        test_message = 'Test message to file'
        logger.info(test_message)
        
        # Проверяем, что сообщение записано в файл
        with open(self.log_file, 'r') as f:
            log_content = f.read()
            self.assertIn(test_message, log_content)
    
    def test_setup_logger_console_only(self):
        """Тест настройки логгера только с выводом в консоль."""
        logger_name = 'test_console_only'
        logger = setup_logger(logger_name, log_file=None, console=True)
        
        # Проверяем, что создан логгер с правильным именем
        self.assertEqual(logger.name, logger_name)
        
        # Проверяем, что у логгера один обработчик (консольный)
        self.assertEqual(len(logger.handlers), 1)
        self.assertIsInstance(logger.handlers[0], logging.StreamHandler)
    
    def test_setup_logger_both(self):
        """Тест настройки логгера с выводом и в файл, и в консоль."""
        logger_name = 'test_both'
        logger = setup_logger(logger_name, log_file=self.log_file, console=True)
        
        # Проверяем, что создан логгер с правильным именем
        self.assertEqual(logger.name, logger_name)
        
        # Проверяем, что у логгера два обработчика
        self.assertEqual(len(logger.handlers), 2)
        
        # Проверяем типы обработчиков
        handler_types = [type(h) for h in logger.handlers]
        self.assertIn(RotatingFileHandler, handler_types)
        self.assertIn(logging.StreamHandler, handler_types)
    
    def test_setup_logger_level(self):
        """Тест настройки уровня логирования."""
        # Проверяем строковый уровень
        logger_name = 'test_level_string'
        logger = setup_logger(logger_name, log_level='ERROR')
        self.assertEqual(logger.level, logging.ERROR)
        
        # Проверяем константный уровень
        logger_name = 'test_level_const'
        logger = setup_logger(logger_name, log_level=logging.DEBUG)
        self.assertEqual(logger.level, logging.DEBUG)
    
    def test_setup_service_logger(self):
        """Тест настройки логгера сервиса на основе конфигурации."""
        # Создаем конфигурацию
        config = {
            'log_level': 'DEBUG',
            'log_file': self.log_file,
            'console_logs': True,
            'log_format': '%(levelname)s - %(message)s'  # Упрощенный формат для проверки
        }
        
        # Настраиваем логгер сервиса
        logger = setup_service_logger(config)
        
        # Проверяем, что создан логгер с правильным именем
        self.assertEqual(logger.name, 'yield_optimizer')
        
        # Проверяем, что у логгера два обработчика
        self.assertEqual(len(logger.handlers), 2)
        
        # Проверяем, что установлен правильный уровень логирования
        self.assertEqual(logger.level, logging.DEBUG)
        
        # Пишем тестовое сообщение в лог
        test_message = 'Test service logger message'
        logger.debug(test_message)
        
        # Проверяем, что сообщение записано в файл
        with open(self.log_file, 'r') as f:
            log_content = f.read()
            self.assertIn(test_message, log_content)
            # Проверяем формат
            self.assertIn(f'DEBUG - {test_message}', log_content)
    
    def test_setup_service_logger_log_dir(self):
        """Тест настройки логгера сервиса с использованием директории логов."""
        # Удаляем файл логов, если он есть
        if os.path.exists(self.log_file):
            os.unlink(self.log_file)
        
        # Создаем конфигурацию с директорией логов
        config = {
            'log_level': 'INFO',
            'log_dir': self.log_dir,
            'console_logs': False
        }
        
        # Настраиваем логгер сервиса
        logger = setup_service_logger(config)
        
        # Проверяем, что файл логов создан в указанной директории
        expected_log_file = os.path.join(self.log_dir, 'yield_optimizer.log')
        self.assertTrue(os.path.exists(expected_log_file))
        
        # Пишем тестовое сообщение в лог
        test_message = 'Test service logger with log_dir'
        logger.info(test_message)
        
        # Проверяем, что сообщение записано в файл
        with open(expected_log_file, 'r') as f:
            log_content = f.read()
            self.assertIn(test_message, log_content)

if __name__ == '__main__':
    unittest.main() 