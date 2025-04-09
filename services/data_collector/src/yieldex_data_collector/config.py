from yieldex_common.config import validate_base_env_vars, logger, get_web3

def validate_env_vars(service_type: str = None) -> bool:
    """
    Validate environment variables for data collector
    Args:
        service_type: Optional service type identifier
    """
    # Для data-collector не требуем Web3
    if not validate_base_env_vars(require_web3=False):
        return False
    return True