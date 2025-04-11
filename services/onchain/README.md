# Yieldex Onchain Service

Service for interacting with DeFi blockchain protocols within the YieldEx platform.

## Installation

The `onchain` service is part of the YieldEx monorepo and should be installed in an environment using `uv`.

```bash
# Clone the repository (if not already done)
git clone git@github.com:yourusername/yieldex.git
cd yieldex

# Create a virtual environment
uv venv .venv
source .venv/bin/activate

# Install all monorepo packages
cd services/common && uv pip install -e .
cd ../analyzer && uv pip install -e .
cd ../onchain && uv pip install -e .
```

## Service Structure

Main modules of the service:

- `protocol_fabric.py` - protocol operator factory and basic interaction classes
- `onchain_operator.py` - high-level operations for executing recommendations
- `config.py` - service configuration

## Supported Protocols

- AAVE V3
- AAVE V2
- Compound V3
- Silo Finance
- Uniswap V3
- Fluid Finance
- Rho Markets
- Lendle

## Usage

### Using the Script

A script `onchain_runner.sh` is created in the project root for convenient interaction with the service:

```bash
# View AAVE V3 rates for a token
./onchain_runner.sh aave-rates Arbitrum USDC

# Check token support
./onchain_runner.sh token-check Optimism DAI

# View supported protocols in the network
./onchain_runner.sh supported-pools Base

# Run tests
./onchain_runner.sh test
```

### Through Python Code

```python
from yieldex_onchain.protocol_fabric import get_protocol_operator
from yieldex_common.utils import get_token_address

# Create a protocol operator
aave_operator = get_protocol_operator("Arbitrum", "aave-v3")

# Check token support
token_address = get_token_address("USDC", "Arbitrum")
is_supported = aave_operator._check_token_support(token_address)

# Perform a deposit operation
deposit_tx = aave_operator.supply("USDC", 100.0)

# Perform a withdrawal operation
withdraw_tx = aave_operator.withdraw("USDC", 50.0)
```

### For Executing Recommendations

```python
from yieldex_onchain.onchain_operator import RecommendationExecutor
from analyzer.analyzer import get_recommendations

# Get recommendations
recommendations = get_recommendations(chain="Arbitrum")

# Select the first recommendation
if recommendations:
    recommendation = recommendations[0]
    
    # Create an executor and execute the recommendation
    executor = RecommendationExecutor(recommendation)
    result = executor.execute()
    
    print(f"Execution result: {result}")
```

## Testing

To check the service's functionality, execute:

```bash
# Basic import and communication tests
python test_onchain.py

# Functionality tests
python test_onchain_functions.py
```

## Dependencies

- `yieldex-common` - common utilities, configuration, ABI access
- `yieldex-analyzer` - yield analysis and recommendation generation service
- `web3` - library for working with Ethereum-compatible blockchains
