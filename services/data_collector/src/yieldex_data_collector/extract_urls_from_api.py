import requests
import json
import logging
import time
import os
import random
from typing import Dict, List, Optional, Tuple
from bs4 import BeautifulSoup
from supabase import create_client, Client
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from webdriver_manager.chrome import ChromeDriverManager

# Загружаем переменные окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()  # Вывод в консоль
    ]
)
logger = logging.getLogger("selenium_url_collector")

# Получаем переменные окружения
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Один экземпляр драйвера для всего скрипта
driver = None

def get_random_user_agent() -> str:
    """
    Генерирует случайный User-Agent для HTTP запросов
    
    Returns:
        Строка со случайным User-Agent
    """
    user_agents = [
        # Chrome на Windows
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/93.0.4577.63 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.81 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/99.0.4844.51 Safari/537.36',
        
        # Firefox на Windows
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:90.0) Gecko/20100101 Firefox/90.0',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:91.0) Gecko/20100101 Firefox/91.0',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:92.0) Gecko/20100101 Firefox/92.0',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:93.0) Gecko/20100101 Firefox/93.0',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:94.0) Gecko/20100101 Firefox/94.0',
        
        # Chrome на macOS
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.131 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/93.0.4577.63 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.81 Safari/537.36',
        
        # Safari на macOS
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.2 Safari/605.1.15',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Safari/605.1.15',
        
        # Edge на Windows
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36 Edg/91.0.864.59',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.131 Safari/537.36 Edg/92.0.902.73',
        
        # Chrome на Android
        'Mozilla/5.0 (Linux; Android 11; SM-G998B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.71 Mobile Safari/537.36',
        'Mozilla/5.0 (Linux; Android 10; SM-G973F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/93.0.4577.62 Mobile Safari/537.36',
        
        # Safari на iOS
        'Mozilla/5.0 (iPhone; CPU iPhone OS 14_7_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.2 Mobile/15E148 Safari/604.1',
        'Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1'
    ]
    
    return random.choice(user_agents)

def initialize_selenium_driver():
    """Инициализирует и возвращает webdriver для Selenium"""
    global driver
    
    if driver is not None:
        return driver
        
    logger.info("Initializing Selenium WebDriver...")
    
    options = Options()
    # Закомментируйте следующую строку, если хотите видеть браузер
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument(f"user-agent={get_random_user_agent()}")
    options.add_argument("--disable-blink-features=AutomationControlled")  # Скрыть, что браузер управляется Selenium
    
    # Дополнительные настройки для маскировки автоматизации
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        
        # Устанавливаем размер окна браузера как у обычного экрана
        driver.set_window_size(1920, 1080)
        
        # Скрипт для маскировки автоматизации
        driver.execute_script("""
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        })
        """)
        
        logger.info("WebDriver initialized successfully")
        return driver
    except Exception as e:
        logger.error(f"Error initializing WebDriver: {e}", exc_info=True)
        raise

def get_random_headers():
    """Генерирует случайные HTTP-заголовки для имитации реального браузера"""
    return {
        'User-Agent': get_random_user_agent(),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Referer': 'https://defillama.com/yields',
        'Connection': 'keep-alive',
        'Cache-Control': 'max-age=0',
    }

def get_white_lists():
    """Получает белые списки токенов и протоколов из переменных окружения"""
    return {
        'protocols': os.getenv('WHITE_LIST_PROTOCOLS', 'aave-v3,aave-v2').split(','),
        'tokens': os.getenv('WHITE_LIST_TOKENS', 'USDT,USDC').split(',')
    }

def fetch_pools() -> List[Dict]:
    """Fetch filtered pools data from DeFiLlama API using the same filter as in collector.py"""
    try:
        logger.info("Starting to fetch pools from DeFiLlama API...")
        response = requests.get("https://yields.llama.fi/pools", headers=get_random_headers(), timeout=10)
        response.raise_for_status()
        data = response.json()['data']
        logger.info(f"Successfully fetched {len(data)} pools from DeFiLlama")

        white_lists = get_white_lists()
        filtered_pools = [
            pool for pool in data
            if pool['symbol'] in white_lists['tokens']
        ]
        
        # Add detailed logging for found pools
        logger.info(f"Filtered to {len(filtered_pools)} relevant pools")
        for i, pool in enumerate(filtered_pools):  # Логируем только первые 10 пулов
            logger.info(f"Found pool {i+1}: {pool['symbol']} on {pool['chain']} in {pool['project']} - ID: {pool['pool']}")
        
        if len(filtered_pools) > 10:
            logger.info(f"... and {len(filtered_pools) - 10} more pools")

        return filtered_pools
    except requests.RequestException as e:
        logger.error(f"Network error while fetching pools: {e}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error while fetching pools: {e}", exc_info=True)
        return []

def get_pool_website_and_twitter_urls(pool_id: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Получает URL сайта пула и Twitter по ID пула с DeFiLlama.
    
    Args:
        pool_id: ID пула из API DeFiLlama
        
    Returns:
        Кортеж (website_url, twitter_url) или (None, None), если не удалось найти
    """
    try:
        # Формируем URL страницы пула
        pool_page_url = f"https://defillama.com/yields/pool/{pool_id}"
        
        # Получаем случайные заголовки
        headers = get_random_headers()
        logger.info(f"Using User-Agent for pool page: {headers['User-Agent']}")
        
        # Добавляем случайную задержку между запросами (1-5 секунд)
        delay = random.uniform(1.0, 5.0)
        logger.info(f"Waiting {delay:.2f} seconds before request...")
        time.sleep(delay)
        
        # Делаем запрос на страницу
        logger.info(f"Fetching pool page: {pool_page_url}")
        response = requests.get(pool_page_url, headers=headers)
        response.raise_for_status()
        
        # Парсим HTML
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Ищем div, содержащий ссылки
        link_container_div = soup.find('div', class_='flex items-center gap-4 flex-wrap')
        
        website_url = None
        twitter_url = None
        
        if link_container_div:
            # Ищем ссылки внутри div
            links = link_container_div.find_all('a')
            
            for link in links:
                # Проверяем текст внутри ссылки
                link_text = link.find('span')
                
                if link_text:
                    if link_text.text.strip() == 'Website':
                        # Получаем полный URL из атрибута href
                        website_url = link['href']
                        logger.info(f"Found website URL: {website_url}")
                    elif link_text.text.strip() == 'Twitter':
                        twitter_url = link['href']
                        logger.info(f"Found Twitter URL: {twitter_url}")
        
        return website_url, twitter_url
    
    except Exception as e:
        logger.error(f"Error fetching URL for pool {pool_id}: {e}", exc_info=True)
        return None, None

def create_pool_id(pool: Dict) -> str:
    """
    Создает композитный pool_id из данных пула
    
    Args:
        pool: Данные пула из DeFiLlama API
        
    Returns:
        Композитный pool_id в формате symbol_chain_project
    """
    symbol = pool.get('symbol', '')
    chain = pool.get('chain', '')
    project = pool.get('project', '')
    
    pool_id = f"{symbol}_{chain}_{project}"
    
    # Добавляем poolMeta, если она есть
    if pool.get('poolMeta'):
        pool_id += f"_{pool['poolMeta']}"
        
    return pool_id

def save_pool_site(supabase: Client, pool_id: str, site_url: str, twitter_url: str) -> None:
    """Сохраняет данные о сайте пула в таблицу pool_sites"""
    try:
        # Проверяем, существует ли уже запись для этого pool_id
        response = supabase.table('pool_sites').select('id').eq('pool_id', pool_id).execute()
        
        if not response.data:
            # Добавляем новую запись
            logger.info(f"Adding new pool site record for {pool_id}")
            supabase.table('pool_sites').insert({
                'pool_id': pool_id,
                'site_url': site_url or '',
                'twitter_url': twitter_url or ''
            }).execute()
            logger.info(f"Added pool site for {pool_id}")
        else:
            # Обновляем существующую запись
            record_id = response.data[0]['id']
            logger.info(f"Updating existing pool site record for {pool_id}")
            
            supabase.table('pool_sites').update({
                'site_url': site_url or '',
                'twitter_url': twitter_url or '',
                'updated_at': 'NOW()'
            }).eq('id', record_id).execute()
            logger.info(f"Updated pool site for {pool_id}")
            
    except Exception as e:
        logger.error(f"Error saving pool site for {pool_id}: {e}", exc_info=True)

def get_existing_pool_ids(supabase: Client) -> List[str]:
    """Получает список pool_id из таблицы apy_history"""
    try:
        logger.info("Fetching unique pool_ids from apy_history...")
        response = supabase.table('apy_history').select('pool_id').execute()
        
        # Извлекаем уникальные pool_id
        pool_ids = set()
        for record in response.data:
            pool_ids.add(record['pool_id'])
        
        logger.info(f"Found {len(pool_ids)} unique pool_ids in database")
        return list(pool_ids)
    except Exception as e:
        logger.error(f"Error fetching pool_ids from database: {e}", exc_info=True)
        return []

def link_apy_history_to_pool_sites(supabase: Client) -> None:
    """Связывает записи в таблице apy_history с записями в pool_sites"""
    try:
        logger.info("Linking apy_history records to pool_sites...")
        
        # Получаем все записи из pool_sites
        pool_sites_response = supabase.table('pool_sites').select('id,pool_id').execute()
        pool_sites = pool_sites_response.data
        
        logger.info(f"Found {len(pool_sites)} records in pool_sites table")
        
        # Получаем записи из apy_history, у которых нет связи с pool_sites
        apy_history_response = supabase.table('apy_history').select('id,pool_id').is_('pool_site_id', 'null').execute()
        apy_records = apy_history_response.data
        
        logger.info(f"Found {len(apy_records)} records in apy_history without pool_site_id")
        
        # Создаем словарь {pool_id: site_id} для быстрого доступа
        pool_id_to_site_id = {site['pool_id']: site['id'] for site in pool_sites}
        
        # Счетчики для статистики
        updated_count = 0
        not_found_count = 0
        
        # Обновляем каждую запись в apy_history
        for record in apy_records:
            apy_id = record['id']
            pool_id = record['pool_id']
            
            if pool_id in pool_id_to_site_id:
                site_id = pool_id_to_site_id[pool_id]
                
                # Обновляем запись
                supabase.table('apy_history').update({
                    'pool_site_id': site_id
                }).eq('id', apy_id).execute()
                
                updated_count += 1
                if updated_count % 100 == 0:
                    logger.info(f"Updated {updated_count} records so far")
            else:
                not_found_count += 1
        
        logger.info(f"Completed linking. Updated {updated_count} records, {not_found_count} records had no matching pool_site")
        
    except Exception as e:
        logger.error(f"Error linking apy_history to pool_sites: {e}", exc_info=True)

def parse_and_save_two_pools(supabase: Client, pools: List[Dict], existing_pool_ids: List[str]) -> None:
    """
    Парсит URL для двух пулов и сохраняет их в БД
    """
    # Берем два случайных пула из отфильтрованных
    sample_pools = random.sample(pools[:min(len(pools), 20)], min(len(pools), 10))
    
    for pool in sample_pools:
        defillama_pool_id = pool['pool']
        composite_pool_id = create_pool_id(pool)
        
        if composite_pool_id not in existing_pool_ids:
            logger.warning(f"Pool {composite_pool_id} not found in database, skipping")
            continue
        
        logger.info(f"Processing pool: {pool['symbol']} on {pool['chain']} in {pool['project']} - ID: {defillama_pool_id}")
        website_url, twitter_url = get_pool_website_and_twitter_urls(defillama_pool_id)
        
        if website_url or twitter_url:
            # Сохраняем данные в БД
            save_pool_site(supabase, composite_pool_id, website_url, twitter_url)
        else:
            logger.warning(f"No URLs found for pool {composite_pool_id}")
        
        # Добавляем продолжительную паузу между запросами
        time.sleep(random.uniform(3.0, 5.0))

def main():
    global driver
    
    try:
        logger.info("Starting Selenium URL collection process...")
        
        # Проверяем наличие переменных окружения
        if not SUPABASE_URL or not SUPABASE_KEY:
            logger.error("SUPABASE_URL or SUPABASE_KEY not set in environment")
            return
        
        # Создаем клиент Supabase
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        
        # Получаем все существующие pool_id из нашей БД
        existing_pool_ids = get_existing_pool_ids(supabase)
        
        # Получаем отфильтрованные пулы с DeFiLlama
        pools = fetch_pools()
        if not pools:
            logger.error("Failed to fetch pools from DeFiLlama")
            return
        
        # Парсим и сохраняем URL для двух пулов
        parse_and_save_two_pools(supabase, pools, existing_pool_ids)
        
        # Связываем записи в apy_history с pool_sites
        link_apy_history_to_pool_sites(supabase)
        
        logger.info("URL collection process completed successfully")
    finally:
        # Закрываем драйвер Selenium после завершения
        if driver is not None:
            logger.info("Closing Selenium WebDriver...")
            driver.quit()
            driver = None

if __name__ == "__main__":
    main() 