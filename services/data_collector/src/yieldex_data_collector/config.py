import os
import dotenv
import yaml
import logging

logger = logging.getLogger(__name__)

def load_config(file_path=None):
    """
    Load configuration from YAML file and substitute environment variables.
    
    Args:
        file_path (str, optional): Path to the YAML configuration file. 
                                   If None, will attempt to find config.yaml in multiple locations.
        
    Returns:
        dict: Configuration with environment variables substituted
    """
    # If path is not specified, try to find config.yaml in multiple locations
    if file_path is None:
        # List of possible config.yaml file locations
        possible_paths = [
            'config.yaml',  # In current directory
            '/app/data_collector/config.yaml',  # In new Docker directory structure
            '/app/config.yaml',  # In /app root in Docker
            os.path.join(os.getcwd(), 'config.yaml'),  # From current working directory
        ]
        
        # Determine current file and try to find relative to it
        current_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Add several levels up from current script
        service_dir = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
        possible_paths.append(os.path.join(service_dir, 'config.yaml'))
        
        # Add paths for backward compatibility with old structure
        possible_paths.append(os.path.join(service_dir, 'services/data_collector/config.yaml'))
        possible_paths.append('/app/services/data_collector/config.yaml')
        
        # Check CONFIG_PATH environment variable
        if os.getenv('CONFIG_PATH'):
            possible_paths.insert(0, os.getenv('CONFIG_PATH'))
        
        # Try each path until we find the file
        for path in possible_paths:
            if os.path.isfile(path):
                file_path = path
                print(f"Found config file at: {file_path}")
                logger.info(f"Using config file from: {file_path}")
                break
        
        if file_path is None:
            # Log all paths we checked
            print(f"Tried to find config.yaml in: {possible_paths}")
            logger.error(f"Could not find config.yaml in any of: {possible_paths}")
            print(f"Current working directory: {os.getcwd()}")
            print(f"Directory listing of current dir: {os.listdir(os.getcwd())}")
            if os.path.exists('/app/data_collector'):
                print(f"Content of /app/data_collector: {os.listdir('/app/data_collector')}")
            return {}
    
    try:
        with open(file_path, 'r') as file:
            config = yaml.safe_load(file)

        # Substitute environment variables
        for key, value in config.items():
            if isinstance(value, dict):
                for sub_key, sub_value in value.items():
                    if isinstance(sub_value, str) and sub_value.startswith('${') and sub_value.endswith('}'):
                        env_var = sub_value.strip('${}')
                        env_value = os.getenv(env_var)
                        if env_value is not None:
                            config[key][sub_key] = env_value
                        else:
                            logger.warning(f"Environment variable {env_var} not found")
            elif isinstance(value, str) and value.startswith('${') and value.endswith('}'):
                env_var = value.strip('${}')
                env_value = os.getenv(env_var)
                if env_value is not None:
                    config[key] = env_value
                else:
                    logger.warning(f"Environment variable {env_var} not found")

        return config
    except FileNotFoundError:
        logger.error(f"Configuration file not found: {file_path}")
        print(f"Configuration file not found: {file_path}")  # Print for Docker logs
        return {}
    except yaml.YAMLError:
        logger.error(f"Error parsing YAML configuration file: {file_path}")
        return {}

def validate_env_vars() -> bool:
    """
    Validate environment variables for data collector using YAML config.
    
    Loads environment variables from .env file and validates required config values.
    
    Returns:
        bool: True if all required configuration values are available, False otherwise
    """
    dotenv.load_dotenv()
    
    # Load configuration from YAML file (will use auto-detection if env var not set)
    config_path = os.getenv('CONFIG_PATH')
    config = load_config(config_path)
    
    # Check if required configuration sections and values exist
    if not config:
        logger.error("Failed to load configuration")
        print("Failed to load configuration")  # Print for Docker logs
        return False
    
    # Validate Supabase configuration
    if 'supabase' not in config or not config['supabase'].get('key') or not config['supabase'].get('url'):
        logger.error("Missing Supabase configuration (key or url)")
        return False
    
    # Validate white list configuration
    if 'white_list' not in config or not config['white_list'].get('protocols') or not config['white_list'].get('tokens'):
        logger.error("Missing white list configuration (protocols or tokens)")
        return False
    
    return True

def get_white_lists():
    """
    Get white lists for protocols and tokens from configuration.
    
    Returns:
        dict: Dictionary with 'protocols' and 'tokens' lists
    """
    config_path = os.getenv('CONFIG_PATH')
    config = load_config(config_path)
    
    white_lists = {
        'protocols': [],
        'tokens': []
    }
    
    if config and 'white_list' in config:
        if 'protocols' in config['white_list']:
            white_lists['protocols'] = config['white_list']['protocols'].split(',')
        if 'tokens' in config['white_list']:
            white_lists['tokens'] = config['white_list']['tokens'].split(',')
    
    return white_lists