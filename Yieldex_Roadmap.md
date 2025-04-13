## Phase 1: Protocol backend development

### Goal

Develop the core modules of the protocol backend

### Technical Tasks

### 1. Data Collection Module

- [X] Integration with DeFiLlama API (https://yields.llama.fi/pools)
- [X] Parsing AAVE data (USDT, USDC, DAI) in networks: Polygon, Arbitrum, Optimism, Base, Avalanche, Ethereum
- [X] Saving to Supabase (tables: `apy_history`, `assets`)
- [X] Containerize and launch the service

### 2. Analytics Module

- [X] APY comparison algorithm between networks
- [X] Profitability calculation considering gas fees (static values)
- [X] Generation of JSON recommendations in the format:

### 3. Onchain Module

- [X] Add connectors to: AAVE, Compound, Uniswap
- [X] Develop rebalancing scenarios within a single network
- [X] Develop rebalancing scenarios for different tokens

## Phase 2: Run autonomous Agent

### Goal

Develop and launch an autonomous agent connected to backend modules

### Technical Tasks:

### 1. Rebalance formula development

- [ ] Define the formula that will be used for making funds rebalancing decisions
- [ ] Develop an API endpoint for formula editing

### 2. Yieldex Agent interface development

- [ ] Integrate backend modules: Analytics Module, Onchain Module
- [ ] Develop 2 operation modes: Manual, Autonomous
- [ ] Containerize the service

### 3. Deploy Yieldex Agent

- [ ] Deploy solution
- [ ] Add logging service

## Phase 3: Smart-wallet Architecture Development

### Goal
Develop and integrate a Smart-wallet module to work with users' EOAs for secure rebalance execution

### Technical Tasks:

### 1. Smart Wallet Core Development
- [ ] Implement ERC-4337 compliant Smart Account contracts
- [ ] Develop session key management system with time/amount/protocols limits
- [ ] Create permission contracts for AAVE protocol interactions

### 2. Smart Wallet Integration
- [ ] Integrate with backend modules: Analytics Module, Onchain Module
- [ ] Develop delegation interface for users (Web3 connection)

### 3. Security & Deployment
- [ ] Develop audit framework for smart contract security
- [ ] Create user-facing permission management dashboard
- [ ] Deploy Smart Wallet Factory contract to mainnet
- [ ] Implement transaction simulation environment