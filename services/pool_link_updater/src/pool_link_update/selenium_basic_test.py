import time
import os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import random
import json
import requests
from supabase import create_client
import logging
from threading import Thread, Lock
from queue import Queue

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("selenium_basic_test")

results_lock = Lock()
task_queue = Queue()

def initialize_selenium_driver():
    """Инициализирует и возвращает webdriver для Selenium с Chrome"""
    logger.info("Initializing Selenium WebDriver with Chrome...")
    
    options = Options()
    
    # Указываем обнаруженный путь к Chrome
    chrome_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    
    # Проверяем существование файла
    if os.path.exists(chrome_path):
        logger.info(f"Chrome browser found at: {chrome_path}")
        options.binary_location = chrome_path
    else:
        logger.error(f"Chrome browser not found at: {chrome_path}")
        raise FileNotFoundError(f"Chrome browser not found at: {chrome_path}")
    
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    
    
    # Дополнительные настройки для маскировки автоматизации
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        
        driver.set_window_size(1920, 1080)
        
        # Скрипт для маскировки автоматизации
        driver.execute_script("""
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        })
        """)
        
        logger.info("WebDriver initialized successfully with Chrome")
        return driver
    except Exception as e:
        logger.error(f"Error initializing WebDriver: {e}", exc_info=True)
        raise

def basic_selenium_test():
    """Базовая проверка доступа к DeFiLlama через Selenium"""
    logger.info("Запуск базового теста Selenium")
    
    try:
        # Настраиваем опции Chrome
        options = Options()
        # НЕ используем headless режим, чтобы видеть, что происходит
        # options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        
        # Инициализируем драйвер Chrome
        logger.info("Инициализация Chrome WebDriver...")
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        
        # Устанавливаем размер окна
        driver.set_window_size(1920, 1080)
        
        # Открываем DeFiLlama
        url = "https://defillama.com/yields"
        logger.info(f"Переход на страницу: {url}")
        driver.get(url)
        
        # Делаем паузу, чтобы страница загрузилась
        time.sleep(5)
        
        # Получаем заголовок страницы
        page_title = driver.title
        logger.info(f"Заголовок страницы: {page_title}")
        
        # Проверяем доступность элементов на странице
        logger.info("Проверка доступности элементов на странице...")
        try:
            # Проверка наличия таблицы с пулами
            table = driver.find_element("css selector", "table.table-responsive")
            logger.info("Таблица пулов найдена")
            
            # Проверка наличия поля поиска
            search_input = driver.find_element("xpath", "//input[@placeholder='Search...']")
            logger.info("Поле поиска найдено")
            
            logger.info("Все основные элементы страницы доступны")
        except Exception as element_e:
            logger.warning(f"Не удалось найти элементы на странице: {element_e}")
        
        # Делаем еще одну паузу перед закрытием
        time.sleep(3)
        
        return True
        
    except Exception as e:
        logger.error(f"Ошибка базового теста: {e}", exc_info=True)
        return False
    
    finally:
        # Закрываем драйвер в любом случае
        if 'driver' in locals():
            logger.info("Закрытие WebDriver...")
            driver.quit()

def extract_urls_from_pool_page(driver):
    """Извлекает URL веб-сайта и Twitter со страницы пула"""
    logger.info("Извлечение URL со страницы пула")
    
    website_url = None
    twitter_url = None
    
    try:
        # Пытаемся найти контейнер с ссылками
        try:
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            
            # Ждем, пока загрузится контейнер со ссылками
            link_container = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.flex.items-center.gap-4.flex-wrap"))
            )
            
            # Ищем все ссылки в контейнере
            links = link_container.find_elements(By.TAG_NAME, "a")
            
            for link in links:
                try:
                    span = link.find_element(By.TAG_NAME, "span")
                    link_text = span.text.strip()
                    raw_href = link.get_attribute("href")
                    
                    logger.info(f"Найдена ссылка с текстом '{link_text}', href: {raw_href}")
                    
                    if link_text == "Website":
                        website_url = raw_href
                        logger.info(f"Найден полный URL веб-сайта: {website_url}")
                    elif link_text == "Twitter":
                        twitter_url = raw_href
                        logger.info(f"Найден полный URL Twitter: {twitter_url}")
                except Exception as e:
                    logger.warning(f"Ошибка при обработке ссылки: {e}")
                    continue
            
        except Exception as container_error:
            logger.warning(f"Не удалось найти контейнер с ссылками: {container_error}")
    
    except Exception as e:
        logger.error(f"Общая ошибка при извлечении URL: {e}")
    
    return website_url, twitter_url

def get_pool_urls_by_direct_access(driver, pool_id):
    """
    Получает URL сайта и Twitter, напрямую переходя на страницу пула по ID
    
    Args:
        driver: Инициализированный Selenium WebDriver
        pool_id: ID пула в формате DeFiLlama (например, "93fb2190-0c2e-4265-a47a-99903c1d9bc9")
        
    Returns:
        Кортеж (website_url, twitter_url) или (None, None), если не удалось найти
    """
    try:
        # Формируем прямой URL страницы пула
        pool_page_url = f"https://defillama.com/yields/pool/{pool_id}"
        
        # Переходим на страницу пула
        logger.info(f"Переход на страницу пула: {pool_page_url}")
        driver.get(pool_page_url)
        
        # Даем время на загрузку страницы
        time.sleep(5)
        
        
        # Теперь ищем контейнер с ссылками
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        
        # Ждем, пока загрузится контейнер со ссылками
        link_container = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div.flex.items-center.gap-4.flex-wrap"))
        )
        
        website_url = None
        twitter_url = None
        
        # Ищем все ссылки в контейнере
        links = link_container.find_elements(By.TAG_NAME, "a")
        
        for link in links:
            try:
                span = link.find_element(By.TAG_NAME, "span")
                link_text = span.text.strip()
                raw_href = link.get_attribute("href")
                
                logger.info(f"Найдена ссылка с текстом '{link_text}', href: {raw_href}")
                
                if link_text == "Website":
                    website_url = raw_href
                    logger.info(f"Найден полный URL веб-сайта: {website_url}")
                elif link_text == "Twitter":
                    twitter_url = raw_href
                    logger.info(f"Найден полный URL Twitter: {twitter_url}")
            except Exception as e:
                logger.warning(f"Ошибка при обработке ссылки: {e}")
                continue
        
        return website_url, twitter_url
    
    except Exception as e:
        logger.error(f"Ошибка при доступе к странице пула {pool_id}: {e}")
        return None, None

def test_direct_pool_access():
    """Тест прямого доступа к пулу по ID"""
    logger.info("Запуск теста прямого доступа к пулу")
    
    # Инициализируем драйвер
    driver = None
    
    try:
        driver = initialize_selenium_driver()
        
        # ID пула для теста
        pool_id = "93fb2190-0c2e-4265-a47a-99903c1d9bc9"  # ID из примера
        
        # Получаем URL
        website_url, twitter_url = get_pool_urls_by_direct_access(driver, pool_id)
        
        if website_url or twitter_url:
            logger.info("Тест успешно завершен!")
            logger.info(f"Website URL: {website_url}")
            logger.info(f"Twitter URL: {twitter_url}")
            return True
        else:
            logger.warning("URL не найдены")
            return False
    
    except Exception as e:
        logger.error(f"Ошибка в тесте прямого доступа: {e}")
        return False
    
    finally:
        if driver:
            logger.info("Закрытие WebDriver")
            driver.quit()

def initialize_drivers_pool(num_drivers: int) -> list:
    """Создает пул из N драйверов"""
    drivers = []
    for i in range(num_drivers):
        try:
            driver = initialize_selenium_driver()
            driver.id = f"Driver-{i+1}"
            drivers.append(driver)
            logger.info(f"Инициализирован {driver.id}")
        except Exception as e:
            logger.error(f"Ошибка инициализации драйвера {i+1}: {e}")
    return drivers

def worker(driver, supabase, output_file: str):
    """Рабочий процесс для обработки задач из очереди"""
    while not task_queue.empty():
        pool_info = task_queue.get()
        our_pool_id = pool_info['our_pool_id']
        defillama_id = pool_info['defillama_id']
        
        try:
            website_url, twitter_url = get_pool_urls_by_direct_access(driver, defillama_id)
            
            if website_url or twitter_url:
                save_pool_site(supabase, our_pool_id, website_url, twitter_url)
            
            # Блокировка для записи результатов
            with results_lock:
                with open(output_file, 'r+') as f:
                    results = json.load(f)
                    results[our_pool_id] = (website_url, twitter_url)
                    f.seek(0)
                    json.dump(results, f, indent=2)
                    f.truncate()
            
            logger.info(f"[{driver.id}] Обработан пул {our_pool_id}")
            
        except Exception as e:
            logger.error(f"[{driver.id}] Ошибка обработки пула {our_pool_id}: {e}")
        finally:
            task_queue.task_done()
            time.sleep(random.uniform(3, 7))  # Случайная задержка

def process_multiple_pools(driver_pool, supabase, mapped_pools, output_file="pool_urls_results.json"):
    """Мультибраузерная обработка пулов"""
    # Очищаем очередь и заполняем новыми задачами
    global task_queue
    task_queue = Queue()
    for pool in mapped_pools:
        task_queue.put(pool)
    
    # Создаем и запускаем потоки
    threads = []
    for driver in driver_pool:
        thread = Thread(
            target=worker,
            args=(driver, supabase, output_file),
            daemon=True
        )
        thread.start()
        threads.append(thread)
    
    # Ожидаем завершения всех задач
    task_queue.join()
    
    # Закрываем драйверы
    for driver in driver_pool:
        driver.quit()
    logger.info("Все задачи завершены")

def process_failed_pools(driver, supabase, output_file="pool_urls_results.json"):
    """Обрабатывает только пулы с неудачными попытками"""
    try:
        # Загружаем существующие результаты
        with open(output_file, 'r') as f:
            results = json.load(f)
        
        # Фильтруем пулы с обоими null и удаляем их из результатов
        failed_pools = []
        valid_results = {}
        
        for pid, urls in results.items():
            if urls[0] is None and urls[1] is None:
                failed_pools.append(pid)
            else:
                valid_results[pid] = urls
                
        logger.info(f"Найдено {len(failed_pools)} пулов для повторной обработки")
        
        if not failed_pools:
            logger.info("Нет пулов для повторной обработки")
            return

        # Обновляем файл результатов, удаляя неудачные записи
        with open(output_file, 'w') as f:
            json.dump(valid_results, f, indent=2)
        
        # Загружаем оригинальные mapped_pools
        with open("mapped_pools.json", 'r') as f:
            original_mapped = json.load(f)
        
        # Фильтруем только нужные пулы
        pools_to_retry = [
            p for p in original_mapped 
            if p['our_pool_id'] in failed_pools
        ]
        
        if not pools_to_retry:
            logger.error("Не найдено соответствий в mapped_pools.json")
            return

        # Запускаем обработку с новым файлом прогресса
        process_multiple_pools(
            driver, 
            supabase, 
            pools_to_retry, 
            output_file=output_file,
            delay_between_requests=10  # Увеличиваем задержку
        )

    except Exception as e:
        logger.error(f"Ошибка при обработке failed pools: {e}")

def parse_multiple_pools(mapped_pools: list):
    """Тест обработки нескольких пулов"""
    logger.info("Запуск теста обработки нескольких пулов")
    
    try:
        num_drivers = int(input("Введите количество браузеров (1-5): ") or 1)
        num_drivers = max(1, min(5, num_drivers))
        
        supabase = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_KEY'))
        driver_pool = initialize_drivers_pool(num_drivers)
        
        if not driver_pool:
            logger.error("Не удалось инициализировать ни одного браузера")
            return False
        
        # Инициализируем файл результатов
        output_file = "pool_urls_results.json"
        if not os.path.exists(output_file):
            with open(output_file, 'w') as f:
                json.dump({}, f)
        
        process_multiple_pools(driver_pool, supabase, mapped_pools, output_file)
        return True
        
    except Exception as e:
        logger.error(f"Ошибка в тесте обработки нескольких пулов: {e}")
        return False

def create_pool_id(pool: dict) -> str:
    """Creates a composite pool ID from pool data"""
    base_id = f"{pool['symbol']}_{pool['chain']}_{pool['project']}"
    pool_id = f"{base_id}_{pool['poolMeta']}" if pool.get('poolMeta') else base_id
    return pool_id

def get_mapped_pool_id_from_llama():
    """
    Fetches pools from DeFiLlama API and maps them to pool_ids in the database.
    Returns list of pool IDs that exist in both DeFiLlama and the database.
    """
    logger.info("Starting pool ID mapping process...")
    
    try:
        # 1. Fetch pools from DeFiLlama API
        response = requests.get("https://yields.llama.fi/pools")
        response.raise_for_status()
        llama_pools = response.json()['data']
        logger.info(f"Fetched {len(llama_pools)} pools from DeFiLlama")

        # 2. Fetch pool_ids from database with pagination
        supabase_url = os.getenv('SUPABASE_URL')
        supabase_key = os.getenv('SUPABASE_KEY')
        supabase = create_client(supabase_url, supabase_key)
        
        all_records = []
        page = 0
        page_size = 1000
        
        while True:
            logger.info(f"Fetching page {page}...")
            response = supabase.table('apy_history') \
                .select('pool_id') \
                .range(page * page_size, (page + 1) * page_size - 1) \
                .execute()
            
            if not response.data:
                break
            
            all_records.extend(response.data)
            page += 1
        
        db_pool_ids = {record['pool_id'] for record in all_records}
        logger.info(f"Found {len(db_pool_ids)} unique pool IDs in database")

        # 3. Create pool_ids from DeFiLlama data and filter matching ones
        mapped_pools = []
        for pool in llama_pools:
            our_pool_id = create_pool_id(pool)  # Это наш ID вида "USDC_Arbitrum_compound-v3"
            if our_pool_id in db_pool_ids:
                mapped_pools.append({
                    'defillama_id': pool['pool'],  # UUID из Defillama
                    'our_pool_id': our_pool_id     # Наш составной ID
                })

        logger.info(f"Successfully mapped {len(mapped_pools)} pools")
        return mapped_pools

    except requests.RequestException as e:
        logger.error(f"Network error while fetching data: {e}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        return []

def save_pool_site(supabase, pool_id: str, website_url: str, twitter_url: str):
    """Сохраняет или обновляет запись в таблице pool_sites"""
    try:
        # Проверяем существование записи
        existing = supabase.table('pool_sites') \
            .select('*') \
            .eq('pool_id', pool_id) \
            .execute()

        data = {
            "pool_id": pool_id,
            "site_url": website_url if website_url else (existing.data[0]['site_url'] if existing.data else None),
            "twitter_url": twitter_url if twitter_url else (existing.data[0]['twitter_url'] if existing.data else None),
        }

        # Если запись существует и данные не изменились - пропускаем
        if existing.data:
            current = existing.data[0]
            if current['site_url'] == data['site_url'] and current['twitter_url'] == data['twitter_url']:
                logger.info(f"Данные для {pool_id} не изменились, пропускаем обновление")
                return

        # Upsert запись
        response = supabase.table('pool_sites').upsert(data).execute()
        
        if len(response.data) > 0:
            logger.info(f"Успешно {'обновлено' if existing.data else 'сохранено'} в БД для {pool_id}")
        else:
            logger.error(f"Ошибка сохранения для {pool_id}")
            
    except Exception as e:
        logger.error(f"Ошибка при сохранении в БД: {e}")

def validate_pool_id_format(pool_id: str) -> bool:
    """Проверяет формат pool_id на соответствие нашему стандарту"""
    parts = pool_id.split('_')
    return len(parts) >= 3 and all(len(part) > 0 for part in parts)

if __name__ == "__main__":
    if os.path.exists("mapped_pools.json"):
        mapped_pools = json.load(open("mapped_pools.json"))
        
        # Добавляем проверку на необходимость повторной обработки
        retry_failed = input("Запустить в режиме повторной обработки неудач? (y/n): ").lower() == 'y'
        
        if retry_failed:
            driver = initialize_selenium_driver()
            supabase = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_KEY'))
            process_failed_pools(driver, supabase)
            driver.quit()
        else:
            parse_multiple_pools(mapped_pools)
    else:
        logger.error("Файл mapped_pools.json не найден. Сначала выполните маппинг пулов.")
