"""Constants for Fluid Finance and DSA (DeFi Smart Account)"""

# Addresses of Fluid vaults for different tokens
FLUID_ADDRESSES = {
    "Arbitrum": {
        "USDC": "0x4CFA50B7Ce747e2D61724fcAc57f24B748FF2b2A",
        "USDT": "0x876Ec6bE52486Eeec06bc06434f3E629D695C6Ba",
    }
}

# Token addresses
TOKEN_ADDRESSES = {
    "Arbitrum": {
        "USDC": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
        "USDT": "0xFd086bC7CD5C481DCC9C85ebE478A1C0b69FCbb9",
    }
}

# DSA contracts
DSA_ADDRESSES = {
    "Arbitrum": {
        "factory": "0x1eE00C305C51Ff3bE60162456A9B533C07cD9288",  # DSA Factory (Index)
        "account": "0x857f3b524317C0C403EC40e01837F1B160F9E7Ab",  # DSA Account
        "connectors": "0x67fCE99Dd6d8d659eea2a1ac1b8881c57eb6592B",  # Connectors
    }
}

# DSA connector identifiers
DSA_CONNECTORS = {
    "Arbitrum": {
        "basic": "BASIC-A",
        "fluid": "FLUID-A",  # Предполагаемый идентификатор, нужно уточнить
    }
}

# DSA connector addresses
# Это реальные адреса коннекторов DSA, которые можно получить через реестр Instadapp
# Для получения актуальных адресов нужно либо:
# 1. Выполнить запрос к InstaIndex контракту
# 2. Посмотреть в официальном реестре: https://github.com/Instadapp/dsa-connectors
DSA_CONNECTOR_ADDRESSES = {
    "Arbitrum": {
        # Примечание: эти адреса нужно обновить на реальные!
        "BASIC-A": "0x94aFEAAD699720F6eE75E1AD90497cE1Eb02624e",  # Реальный адрес BASIC-A
        "FLUID-A": "0x0000000000000000000000000000000000000000",  # Заглушка, нужно узнать реальный
    }
}
