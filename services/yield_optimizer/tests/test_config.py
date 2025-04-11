"""
Тесты для модуля config.py из пакета yield_optimizer.
"""

import os
import tempfile
import unittest
import yaml

from src.yield_optimizer.config import ConfigManager


class TestConfigManager(unittest.TestCase):
    """Тесты для класса ConfigManager."""

    def setUp(self):
        """Подготовка к тестам."""
        # Создаем временный файл для конфигурации
        self.config_file = tempfile.NamedTemporaryFile(delete=False, suffix=".yaml")
        self.config_path = self.config_file.name

        # Тестовая конфигурация
        self.test_config = {
            "chain": "Arbitrum",
            "min_profit_threshold": 0.5,
            "check_interval_hours": 24,
            "max_recommendations_per_cycle": 1,
        }

        # Записываем тестовую конфигурацию во временный файл
        with open(self.config_path, "w") as f:
            yaml.dump(self.test_config, f)

        # Сохраняем текущие переменные окружения, которые могут влиять на тесты
        self.original_env = {
            key: os.environ.get(key)
            for key in ["YIELD_MIN_PROFIT", "YIELD_CHECK_INTERVAL", "YIELD_CHAIN"]
        }

    def tearDown(self):
        """Очистка после тестов."""
        # Удаляем временный файл
        os.unlink(self.config_path)

        # Восстанавливаем переменные окружения
        for key, value in self.original_env.items():
            if value is None:
                if key in os.environ:
                    del os.environ[key]
            else:
                os.environ[key] = value

    def test_load_from_file(self):
        """Тест загрузки конфигурации из файла."""
        config_manager = ConfigManager(self.config_path)

        # Проверяем, что все значения из файла загружены корректно
        self.assertEqual(config_manager.get("chain"), "Arbitrum")
        self.assertEqual(config_manager.get("min_profit_threshold"), 0.5)
        self.assertEqual(config_manager.get("check_interval_hours"), 24)
        self.assertEqual(config_manager.get("max_recommendations_per_cycle"), 1)

    def test_load_from_env(self):
        """Тест переопределения конфигурации через переменные окружения."""
        # Устанавливаем переменные окружения
        os.environ["YIELD_MIN_PROFIT"] = "1.0"
        os.environ["YIELD_CHECK_INTERVAL"] = "12"
        os.environ["YIELD_CHAIN"] = "Optimism"

        config_manager = ConfigManager(self.config_path)

        # Проверяем, что значения из переменных окружения переопределяют значения из файла
        self.assertEqual(config_manager.get("min_profit_threshold"), 1.0)
        self.assertEqual(config_manager.get("check_interval_hours"), 12)
        self.assertEqual(config_manager.get("chain"), "Optimism")

        # Значение, которое не было переопределено, должно остаться прежним
        self.assertEqual(config_manager.get("max_recommendations_per_cycle"), 1)

    def test_get_default(self):
        """Тест получения значения по умолчанию при отсутствии ключа."""
        config_manager = ConfigManager(self.config_path)

        # Получаем несуществующее значение с указанием значения по умолчанию
        self.assertEqual(
            config_manager.get("nonexistent_key", "default_value"), "default_value"
        )

        # Получаем несуществующее значение без указания значения по умолчанию
        self.assertIsNone(config_manager.get("another_nonexistent_key"))

    def test_set_get(self):
        """Тест установки и получения значения."""
        config_manager = ConfigManager(self.config_path)

        # Устанавливаем новое значение
        config_manager.set("new_key", "new_value")

        # Проверяем, что новое значение было установлено
        self.assertEqual(config_manager.get("new_key"), "new_value")

    def test_get_all(self):
        """Тест получения копии всей конфигурации."""
        config_manager = ConfigManager(self.config_path)

        # Получаем копию всей конфигурации
        config_copy = config_manager.get_all()

        # Проверяем, что копия содержит все ключи и значения
        for key, value in self.test_config.items():
            self.assertEqual(config_copy.get(key), value)

    def test_save(self):
        """Тест сохранения конфигурации в файл."""
        config_manager = ConfigManager(self.config_path)

        # Устанавливаем новое значение
        config_manager.set("new_key", "new_value")

        # Создаем новый временный файл для сохранения
        new_config_file = tempfile.NamedTemporaryFile(delete=False, suffix=".yaml")
        new_config_path = new_config_file.name
        new_config_file.close()

        try:
            # Сохраняем конфигурацию в новый файл
            config_manager.save(new_config_path)

            # Создаем новый ConfigManager для проверки сохраненной конфигурации
            new_config_manager = ConfigManager(new_config_path)

            # Проверяем, что исходные значения сохранены
            for key, value in self.test_config.items():
                self.assertEqual(new_config_manager.get(key), value)

            # Проверяем, что новое значение также сохранено
            self.assertEqual(new_config_manager.get("new_key"), "new_value")
        finally:
            # Удаляем временный файл
            if os.path.exists(new_config_path):
                os.unlink(new_config_path)


if __name__ == "__main__":
    unittest.main()
