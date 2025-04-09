import logging
import os
from typing import Dict, List
from supabase import create_client, Client
from dotenv import load_dotenv

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
logger = logging.getLogger("link_pool_sites")

# Получаем переменные окружения
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

def link_apy_history_to_pool_sites(supabase: Client) -> None:
    """
    Связывает записи в таблице apy_history с записями в pool_sites
    без использования SQL-запросов через RPC
    """
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

def main():
    logger.info("Starting link_pool_sites script...")
    
    # Проверяем наличие переменных окружения
    if not SUPABASE_URL or not SUPABASE_KEY:
        logger.error("SUPABASE_URL or SUPABASE_KEY not set in environment")
        return
    
    # Создаем клиент Supabase
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    
    # Связываем записи
    link_apy_history_to_pool_sites(supabase)
    
    logger.info("Script completed successfully")

if __name__ == "__main__":
    main() 