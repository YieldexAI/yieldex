import logging
import json
import time
import os
import random
import requests
from bs4 import BeautifulSoup
from supabase import create_client, Client
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager

# Загружаем переменные окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler()  # Вывод в консоль
    ],
)
logger = logging.getLogger("selenium_url_collector")

# Получаем переменные окружения
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")


def get_random_user_agent() -> str:
    """
    Генерирует случайный User-Agent для HTTP запросов

    Returns:
        Строка со случайным User-Agent
    """
    user_agents = [
        # Chrome на Windows
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/93.0.4577.63 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.81 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/99.0.4844.51 Safari/537.36",
        # Firefox на Windows
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:90.0) Gecko/20100101 Firefox/90.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:91.0) Gecko/20100101 Firefox/91.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:92.0) Gecko/20100101 Firefox/92.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:93.0) Gecko/20100101 Firefox/93.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:94.0) Gecko/20100101 Firefox/94.0",
        # Chrome на macOS
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.131 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/93.0.4577.63 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.81 Safari/537.36",
        # Safari на macOS
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.2 Safari/605.1.15",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Safari/605.1.15",
        # Edge на Windows
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36 Edg/91.0.864.59",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.131 Safari/537.36 Edg/92.0.902.73",
        # Chrome на Android
        "Mozilla/5.0 (Linux; Android 11; SM-G998B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.71 Mobile Safari/537.36",
        "Mozilla/5.0 (Linux; Android 10; SM-G973F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/93.0.4577.62 Mobile Safari/537.36",
        # Safari на iOS
        "Mozilla/5.0 (iPhone; CPU iPhone OS 14_7_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.2 Mobile/15E148 Safari/604.1",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1",
    ]

    return random.choice(user_agents)


def initialize_selenium_driver():
    """Инициализирует и возвращает webdriver для Selenium с Brave"""
    logger.info("Initializing Selenium WebDriver with Brave...")

    options = Options()

    # Указываем путь к Brave для Mac
    brave_path = "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"

    # Проверяем существование файла
    if os.path.exists(brave_path):
        logger.info(f"Brave browser found at: {brave_path}")
        options.binary_location = brave_path
    else:
        logger.error(f"Brave browser not found at: {brave_path}")
        raise FileNotFoundError(f"Brave browser not found at: {brave_path}")

    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument(f"user-agent={get_random_user_agent()}")
    options.add_argument("--disable-blink-features=AutomationControlled")

    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)

        driver.set_window_size(1920, 1080)

        driver.execute_script("""
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        })
        """)

        logger.info("WebDriver initialized successfully with Brave")
        return driver
    except Exception as e:
        logger.error(f"Error initializing WebDriver: {e}", exc_info=True)
        raise


def get_top_pools_from_db(supabase, limit=20):
    """Получает топ-N наиболее часто встречающихся pool_id из базы данных"""
    try:
        logger.info(f"Fetching pool_ids from database...")

        # Получаем все записи без pool_site_id
        response = (
            supabase.table("apy_history")
            .select("pool_id")
            .is_("pool_site_id", "null")
            .limit(5000)
            .execute()
        )

        if not response.data:
            logger.warning("No pools found in database")
            return []

        # Считаем частоту каждого pool_id
        pool_counts = {}
        for record in response.data:
            pool_id = record["pool_id"]
            if pool_id in pool_counts:
                pool_counts[pool_id] += 1
            else:
                pool_counts[pool_id] = 1

        # Сортируем по частоте и берем топ limit
        sorted_pools = sorted(pool_counts.items(), key=lambda x: x[1], reverse=True)
        top_pools = [pool_id for pool_id, count in sorted_pools[:limit]]

        logger.info(f"Found {len(top_pools)} pools to process")
        for i, pool_id in enumerate(top_pools):
            logger.info(f"Pool {i + 1}: {pool_id} (count: {pool_counts[pool_id]})")

        return top_pools
    except Exception as e:
        logger.error(f"Error fetching top pools from database: {e}", exc_info=True)
        return []


def get_pool_urls_by_direct_navigation(driver, pool_id):
    """
    Получает URL сайта и Twitter для пула путем прямого перехода
    на страницу пула в DeFiLlama
    """
    try:
        # Разбираем композитный ID пула для формирования поискового запроса
        parts = pool_id.split("_")
        if len(parts) < 3:
            logger.error(f"Invalid pool_id format: {pool_id}")
            return None, None

        symbol = parts[0]
        chain = parts[1]
        project = parts[2]

        # Добавляем meta-информацию, если она есть
        meta = ""
        if len(parts) > 3:
            meta = parts[3]

        # Формируем поисковый запрос для DeFiLlama
        search_query = f"{symbol} {chain} {project}"
        if meta:
            search_query += f" {meta}"

        logger.info(f"Search query: {search_query}")

        # Переходим на страницу со всеми пулами
        yields_url = "https://defillama.com/yields"
        logger.info(f"Navigating to yields page: {yields_url}")
        driver.get(yields_url)

        # Ждем загрузки страницы и JavaScript
        time.sleep(5)

        # Пытаемся найти поле поиска
        try:
            search_input = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located(
                    (By.XPATH, "//input[@placeholder='Search...']")
                )
            )

            # Вводим поисковый запрос
            search_input.clear()
            search_input.send_keys(search_query)

            # Даем время на фильтрацию результатов
            time.sleep(3)

            # Находим первую строку таблицы результатов
            try:
                first_row = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable(
                        (By.CSS_SELECTOR, "table.table-responsive tbody tr")
                    )
                )

                # Нажимаем на строку, чтобы перейти на страницу пула
                first_row.click()

                # Ждем загрузки страницы пула
                time.sleep(5)

                # Теперь ищем контейнер с ссылками
                try:
                    link_container = WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located(
                            (By.CSS_SELECTOR, "div.flex.items-center.gap-4.flex-wrap")
                        )
                    )

                    # Ищем все ссылки в контейнере
                    links = link_container.find_elements(By.TAG_NAME, "a")

                    website_url = None
                    twitter_url = None

                    for link in links:
                        try:
                            span = link.find_element(By.TAG_NAME, "span")
                            link_text = span.text.strip()

                            if link_text == "Website":
                                website_url = link.get_attribute("href")
                                logger.info(f"Found website URL: {website_url}")
                            elif link_text == "Twitter":
                                twitter_url = link.get_attribute("href")
                                logger.info(f"Found Twitter URL: {twitter_url}")
                        except Exception as e:
                            logger.warning(f"Error parsing link: {e}")
                            continue

                    return website_url, twitter_url

                except TimeoutException:
                    logger.warning(
                        f"Could not find link container on page for pool {pool_id}"
                    )
                    return None, None

            except TimeoutException:
                logger.warning(f"No results found for search query: {search_query}")
                return None, None

        except TimeoutException:
            logger.warning("Could not find search input")
            return None, None

    except Exception as e:
        logger.error(f"Error getting URLs for pool {pool_id}: {e}", exc_info=True)
        return None, None


def save_pool_site(supabase, pool_id, site_url, twitter_url):
    """Сохраняет данные о сайте пула в таблицу pool_sites"""
    try:
        # Проверяем, существует ли уже запись для этого pool_id
        response = (
            supabase.table("pool_sites").select("id").eq("pool_id", pool_id).execute()
        )

        if not response.data:
            # Добавляем новую запись
            logger.info(f"Adding new pool site record for {pool_id}")
            result = (
                supabase.table("pool_sites")
                .insert(
                    {
                        "pool_id": pool_id,
                        "site_url": site_url or "",
                        "twitter_url": twitter_url or "",
                    }
                )
                .execute()
            )
            record_id = result.data[0]["id"]
            logger.info(f"Added pool site for {pool_id}, id: {record_id}")
            return record_id
        else:
            # Обновляем существующую запись
            record_id = response.data[0]["id"]
            logger.info(f"Updating existing pool site record for {pool_id}")

            supabase.table("pool_sites").update(
                {
                    "site_url": site_url or "",
                    "twitter_url": twitter_url or "",
                    "updated_at": "NOW()",
                }
            ).eq("id", record_id).execute()
            logger.info(f"Updated pool site for {pool_id}")
            return record_id
    except Exception as e:
        logger.error(f"Error saving pool site for {pool_id}: {e}", exc_info=True)
        return None


def link_apy_history_to_pool_sites(supabase, pool_id, site_id):
    """Связывает записи в таблице apy_history с записями в pool_sites для конкретного пула"""
    try:
        logger.info(
            f"Linking apy_history records for pool {pool_id} to pool_site {site_id}..."
        )

        # Получаем записи из apy_history для этого pool_id без связи с pool_sites
        apy_history_response = (
            supabase.table("apy_history")
            .select("id")
            .eq("pool_id", pool_id)
            .is_("pool_site_id", "null")
            .execute()
        )
        apy_records = apy_history_response.data

        if not apy_records:
            logger.info(f"No unlinked records found for pool {pool_id}")
            return 0

        logger.info(f"Found {len(apy_records)} unlinked records for pool {pool_id}")

        # Обновляем записи пакетом по 100 штук
        updated_count = 0
        batch_size = 100

        for i in range(0, len(apy_records), batch_size):
            batch = apy_records[i : i + batch_size]
            ids = [record["id"] for record in batch]

            # Обновляем записи
            supabase.table("apy_history").update({"pool_site_id": site_id}).in_(
                "id", ids
            ).execute()

            updated_count += len(batch)
            logger.info(f"Updated {updated_count}/{len(apy_records)} records")

        logger.info(
            f"Completed linking for pool {pool_id}. Updated {updated_count} records."
        )
        return updated_count

    except Exception as e:
        logger.error(
            f"Error linking apy_history to pool_sites for pool {pool_id}: {e}",
            exc_info=True,
        )
        return 0


def main():
    try:
        logger.info("Starting Selenium URL collection process...")

        # Проверяем наличие переменных окружения
        if not SUPABASE_URL or not SUPABASE_KEY:
            logger.error("SUPABASE_URL or SUPABASE_KEY not set in environment")
            return

        # Создаем клиент Supabase
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

        # Получаем топ-20 пулов
        top_pools = get_top_pools_from_db(supabase, limit=20)
        if not top_pools:
            logger.error("No pools to process")
            return

        # Инициализируем драйвер Selenium
        driver = initialize_selenium_driver()

        try:
            # Открываем DeFiLlama один раз, чтобы принять куки/условия
            driver.get("https://defillama.com")
            time.sleep(5)

            # Обрабатываем каждый пул
            for i, pool_id in enumerate(top_pools):
                logger.info(f"Processing pool {i + 1}/{len(top_pools)}: {pool_id}")

                # Получаем URL сайта и Twitter
                website_url, twitter_url = get_pool_urls_by_direct_navigation(
                    driver, pool_id
                )

                if not website_url and not twitter_url:
                    logger.warning(f"No URLs found for pool {pool_id}, skipping...")
                    continue

                # Сохраняем данные в БД
                site_id = save_pool_site(supabase, pool_id, website_url, twitter_url)
                if site_id:
                    # Связываем записи в apy_history с pool_sites
                    link_apy_history_to_pool_sites(supabase, pool_id, site_id)

                # Делаем большую паузу между пулами, чтобы избежать блокировки
                if i < len(top_pools) - 1:  # Если не последний пул
                    delay = random.uniform(10.0, 20.0)
                    logger.info(f"Waiting {delay:.2f} seconds before next pool...")
                    time.sleep(delay)

        finally:
            # Закрываем драйвер Selenium после завершения
            if driver:
                logger.info("Closing Selenium WebDriver...")
                driver.quit()

        logger.info("URL collection process completed successfully")

    except Exception as e:
        logger.error(f"Unexpected error in main process: {e}", exc_info=True)


if __name__ == "__main__":
    main()
