import logging
import os
from supabase import create_client, Client
from dotenv import load_dotenv

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
logger = logging.getLogger("demo_pool_sites")

# Получаем переменные окружения
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Демо-данные для записей pool_sites
DEMO_RECORDS = [
    {
        "pool_id": "DAI_Polygon_aave-v3",
        "site_url": "https://app.aave.com/markets/",
        "twitter_url": "https://twitter.com/aave",
    },
    {
        "pool_id": "USDC_BSC_venus-core-pool",
        "site_url": "https://app.venus.io/",
        "twitter_url": "https://twitter.com/VenusProtocol",
    },
    {
        "pool_id": "USDT_Ethereum_aave-v3",
        "site_url": "https://app.aave.com/markets/",
        "twitter_url": "https://twitter.com/aave",
    },
    {
        "pool_id": "USDC_Arbitrum_compound-v3",
        "site_url": "https://app.compound.finance/",
        "twitter_url": "https://twitter.com/compoundfinance",
    },
]


def save_pool_site(supabase: Client, pool_data: dict) -> str:
    """
    Сохраняет или обновляет данные о сайте пула в таблице pool_sites

    Args:
        supabase: Клиент Supabase
        pool_data: Данные о пуле (pool_id, site_url, twitter_url)

    Returns:
        ID добавленной или обновленной записи
    """
    try:
        pool_id = pool_data["pool_id"]
        site_url = pool_data["site_url"]
        twitter_url = pool_data["twitter_url"]

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
                        "site_url": site_url,
                        "twitter_url": twitter_url,
                    }
                )
                .execute()
            )
            record_id = result.data[0]["id"]
            logger.info(f"Added pool site for {pool_id}, id: {record_id}")
        else:
            # Обновляем существующую запись
            record_id = response.data[0]["id"]
            logger.info(f"Updating existing pool site record for {pool_id}")

            supabase.table("pool_sites").update(
                {
                    "site_url": site_url,
                    "twitter_url": twitter_url,
                    "updated_at": "NOW()",
                }
            ).eq("id", record_id).execute()
            logger.info(f"Updated pool site for {pool_id}, id: {record_id}")

        return record_id
    except Exception as e:
        logger.error(f"Error saving pool site for {pool_id}: {e}", exc_info=True)
        return None


def link_apy_history_to_pool_sites(supabase: Client) -> None:
    """
    Связывает записи в таблице apy_history с записями в pool_sites
    """
    try:
        logger.info("Linking apy_history records to pool_sites...")

        # Получаем все записи из pool_sites
        pool_sites_response = (
            supabase.table("pool_sites").select("id,pool_id").execute()
        )
        pool_sites = pool_sites_response.data

        logger.info(f"Found {len(pool_sites)} records in pool_sites table")

        # Получаем записи из apy_history, у которых нет связи с pool_sites
        apy_history_response = (
            supabase.table("apy_history")
            .select("id,pool_id")
            .is_("pool_site_id", "null")
            .limit(1000)
            .execute()
        )
        apy_records = apy_history_response.data

        logger.info(
            f"Found {len(apy_records)} records in apy_history without pool_site_id (limited to 1000)"
        )

        # Создаем словарь {pool_id: site_id} для быстрого доступа
        pool_id_to_site_id = {site["pool_id"]: site["id"] for site in pool_sites}

        # Счетчики для статистики
        updated_count = 0
        not_found_count = 0

        # Обновляем каждую запись в apy_history
        for record in apy_records:
            apy_id = record["id"]
            pool_id = record["pool_id"]

            if pool_id in pool_id_to_site_id:
                site_id = pool_id_to_site_id[pool_id]

                # Обновляем запись
                supabase.table("apy_history").update({"pool_site_id": site_id}).eq(
                    "id", apy_id
                ).execute()

                updated_count += 1
                if updated_count % 100 == 0:
                    logger.info(f"Updated {updated_count} records so far")
            else:
                not_found_count += 1
                if not_found_count % 100 == 0:
                    logger.info(
                        f"No matching pool_site for {not_found_count} records so far"
                    )

        logger.info(
            f"Completed linking. Updated {updated_count} records, {not_found_count} records had no matching pool_site"
        )

    except Exception as e:
        logger.error(f"Error linking apy_history to pool_sites: {e}", exc_info=True)


def main():
    logger.info("Starting demo records creation process...")

    # Проверяем наличие переменных окружения
    if not SUPABASE_URL or not SUPABASE_KEY:
        logger.error("SUPABASE_URL or SUPABASE_KEY not set in environment")
        return

    # Создаем клиент Supabase
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

    # Добавляем демо-записи
    for record in DEMO_RECORDS:
        save_pool_site(supabase, record)

    # Связываем записи в apy_history с pool_sites
    link_apy_history_to_pool_sites(supabase)

    logger.info("Demo records creation completed successfully")


if __name__ == "__main__":
    main()
