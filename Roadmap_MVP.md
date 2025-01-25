## Phase 1: MVP (Minimal Viable Product)

### Goal

Launch a basic version with minimal dependencies to validate the concept.

### Technical Tasks

### 1. Data Collection Module

- [ ] Integration with DeFiLlama API (https://yields.llama.fi/pools)
- [ ] Parsing AAVE data (USDT, USDC, DAI) in networks: Polygon, Arbitrum, Optimism, Base, Avalanche, Ethereum
- [ ] Saving to Supabase (tables: `apy_history`, `assets`)

### 2. Analytics Module

- [ ] APY comparison algorithm between networks
- [ ] Profitability calculation considering gas fees (static values)
- [ ] Generation of JSON recommendations in the format:
