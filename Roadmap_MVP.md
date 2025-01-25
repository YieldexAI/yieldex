## Phase 1: MVP (Minimal Viable Product)

### Goal

Launch a basic version with minimal dependencies to validate the concept.

### Technical Tasks

### 1. Data Collection Module

- [X] Integration with DeFiLlama API (https://yields.llama.fi/pools)
- [X] Parsing AAVE data (USDT, USDC, DAI) in networks: Polygon, Arbitrum, Optimism, Base, Avalanche, Ethereum
- [X] Saving to Supabase (tables: `apy_history`, `assets`)

### 2. Analytics Module

- [X] APY comparison algorithm between networks
- [X] Profitability calculation considering gas fees (static values)
- [ ] Generation of JSON recommendations in the format:
