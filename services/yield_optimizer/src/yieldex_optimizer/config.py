"""
Модуль управления конфигурацией сервиса оптимизации доходности.

Включает:
- Загрузку конфигураций из YAML-файлов
- Переопределение настроек через переменные окружения
- Доступ к конфигурациям через единый интерфейс
"""

import os
import logging
import yaml
from typing import Any, Dict, Optional, Union

logger = logging.getLogger(__name__)

class ConfigManager:
    """
    Класс для управления конфигурацией сервиса.
    
    Позволяет загружать настройки из YAML-файлов и переменных окружения.
    """
    
    def __init__(self, config_path: str):
        """
        Инициализация менеджера конфигураций.
        
        Args:
            config_path (str): Путь к файлу конфигурации YAML.
        """
        self.config_path = config_path
        self.config: Dict[str, Any] = {}
        
        # Загружаем базовую конфигурацию из файла
        self._load_config_from_file()
        
        # Загружаем и приоритезируем переменные окружения
        self._load_from_env()
        
        logger.info(f"Configuration loaded from {config_path}")
        
    def _load_config_from_file(self) -> None:
        """Загружает конфигурацию из YAML-файла."""
        try:
            with open(self.config_path, 'r') as config_file:
                self.config = yaml.safe_load(config_file) or {}
            logger.debug(f"Loaded configuration from {self.config_path}")
        except FileNotFoundError:
            logger.warning(f"Configuration file not found: {self.config_path}")
            self.config = {}
        except yaml.YAMLError as e:
            logger.error(f"Error parsing configuration file: {e}")
            self.config = {}
        except Exception as e:
            logger.error(f"Unexpected error loading configuration: {e}")
            self.config = {}
            
    def _load_from_env(self) -> None:
        """Загружает конфигурацию из переменных окружения."""
        env_mapping = {
            'YIELD_MIN_PROFIT': 'min_profit_threshold',
            'YIELD_CHECK_INTERVAL': 'check_interval_hours',
            'YIELD_MAX_GAS': 'max_gas_gwei',
            'YIELD_CHAIN': 'chain',
            'YIELD_MAX_RECS': 'max_recommendations_per_cycle',
            'YIELD_SUGGEST_ENTRY': 'suggest_entry',
            'YIELD_MAX_SLIPPAGE': 'max_slippage_percent',
            'YIELD_LOG_LEVEL': 'log_level'
        }
        
        for env_var, config_key in env_mapping.items():
            if env_var in os.environ:
                value = os.environ[env_var]
                
                # Преобразуем типы соответствующим образом
                if config_key in ['min_profit_threshold', 'max_gas_gwei', 'max_slippage_percent']:
                    try:
                        self.config[config_key] = float(value)
                    except ValueError:
                        logger.error(f"Invalid float value for {env_var}: {value}")
                        continue
                elif config_key in ['check_interval_hours', 'max_recommendations_per_cycle']:
                    try:
                        self.config[config_key] = int(value)
                    except ValueError:
                        logger.error(f"Invalid integer value for {env_var}: {value}")
                        continue
                elif config_key in ['suggest_entry']:
                    self.config[config_key] = value.lower() in ['true', '1', 'yes', 'y', 'on']
                else:
                    self.config[config_key] = value
                    
                logger.debug(f"Overriding {config_key} from environment variable {env_var}")
                
    def get(self, key: str, default: Any = None) -> Any:
        """
        Получает значение из конфигурации.
        
        Args:
            key (str): Ключ настройки.
            default: Значение по умолчанию, если ключ не найден.
            
        Returns:
            Any: Значение настройки или значение по умолчанию.
        """
        return self.config.get(key, default)
    
    def set(self, key: str, value: Any) -> None:
        """
        Устанавливает значение в конфигурации.
        
        Args:
            key (str): Ключ настройки.
            value (Any): Значение настройки.
        """
        self.config[key] = value
        logger.debug(f"Set configuration {key} to {value}")
        
    def get_all(self) -> Dict[str, Any]:
        """
        Возвращает копию всей конфигурации.
        
        Returns:
            Dict[str, Any]: Копия всей конфигурации.
        """
        return self.config.copy()
    
    def save(self, path: Optional[str] = None) -> None:
        """
        Сохраняет текущую конфигурацию в файл.
        
        Args:
            path (Optional[str]): Путь к файлу для сохранения. 
                                 Если не указан, используется исходный путь.
        """
        save_path = path or self.config_path
        try:
            with open(save_path, 'w') as file:
                yaml.dump(self.config, file, default_flow_style=False)
            logger.info(f"Configuration saved to {save_path}")
        except Exception as e:
            logger.error(f"Error saving configuration to {save_path}: {e}") 