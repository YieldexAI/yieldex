# Yieldex

Yieldex is an automated yield optimizer for stablecoins on EVM networks. The project periodically gathers current APY/APR information from protocols (e.g., AAVE and Lendle) and stores it in a database (Supabase). Additionally, all APY data is recorded in a smart contract on the Mantle network to ensure transparency and data integrity.

Using the AI Analytics module, Yieldex analyzes the collected yield figures and generates recommendations for shifting capital between pools across various networks based on potential profit (taking gas costs into account).

## Core Functionality and Architecture

The project consists of the following modules/components:

1. **Data Collection Module:**  
   - Periodically fetches yield rates for selected tokens (DAI, USDT, USDC, GHO, etc.) from DeFi providers such as DeFiLlama.  
   - Saves this data to a Supabase database and also duplicates it to the Mantle smart contract for decentralized storage.

2. **Analytics Module:**  
   - Retrieves the latest yield information from the database.  
   - Compares APYs/APRs across different networks, accounting for gas costs, to determine the most profitable place to keep an asset.  
   - Generates recommendations to move funds from one pool to another.

3. **On-chain Module:**  
   - Handles interactions with AAVE, Lendle, and other protocols.  
   - Provides classes to initialize Web3 connections, sign, and send transactions to the respective networks.  
   - Uses ABIs (e.g., AaveV3Pool.json, ERC20.json) to call methods like supply, deposit, withdraw, etc.

4. **Notifications (Telegram):**  
   - Sends alerts to Telegram regarding events or generated recommendations.  
   - If the system detects any "arbitrage" or more profitable pools, the bot notifies about potential capital moves.

5. **Data Storage (Supabase + Mantle Oracle):**  
   - Supabase serves as the primary database, storing all historical yield data for the pools, as well as the balances of any owned positions.  
   - The Mantle smart contract (YieldexOracle) reinforces decentralized data storage for the APY figures.

---

## Installation and Setup

Below are brief instructions for running the project locally.

### 1. Clone the Repository
```bash
git clone https://github.com/example/yieldex.git
cd yieldex
```

### 2. Install Dependencies

This project is written in Python. The main packages are listed in [pyproject.toml](pyproject.toml). You can install them using pip or another package manager:

```bash
pip install .
```

Alternatively, you can install from:
```bash
pip install -r requirements.txt
```

### 3. Configure Environment Variables

Copy the .env.example file to .env and fill in the required secrets. The .env file includes details such as Supabase connection information, the private key for EVM networks, a Telegram bot token, etc.

Example (env.example):

Supabase
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_anon_key
Private key EVM
PRIVATE_KEY=your_wallet_private_key
Telegram
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_telegram_chat_id
TELEGRAM_THREAD_ID=your_telegram_thread_id

### 4. Initialize the Database

In the src/sql/migrations folder, you'll find SQL files that create the required tables for Supabase (apy_history, pool_balances, etc.).  
You can execute them manually in Supabase or with any migration tool:

- 01_create_apy_history.sql  
- 02_create_pool_balances.sql  
...

### 5. Run the Data Collection Module

```bash
python -m src.yieldex.data_collector
```
This module:  
1) Fetches yield data from DeFi sources.  
2) Saves them to the apy_history table.  
3) Attempts to update Mantle (YieldexOracle) with the latest APY values.

### 6. Run the Analytics Module (example)

Generate recommendations:
```bash
python -m src.yieldex.analytics
```
(In particular, you can call the get_recommendations function, which returns a list of potential transfers.)

### 7. On-Chain Operations

The onchain.py module allows you to:  
- Check token balances (get_balance).  
- Approve tokens for protocols (approve_token).  
- Supply and withdraw liquidity in AAVE, Lendle, etc.

Example usage:
```python
from src.yieldex.onchain import ERC20Utils

utils = ERC20Utils("Polygon")
balance = utils.get_balance("0x...")  # ERC20 contract address
print("Balance:", balance)
```

---

## Key Files and Directories

- src/yieldex/onchain.py — Logic for blockchain interaction (approve, get_balance, etc.).  
- src/yieldex/protocol_fabric.py — Operator classes for protocol integration (AaveOperator, LendleOperator, YieldexOracleOperator).  
- src/yieldex/config.py — Configuration: loading environment variables, storing contract addresses, etc.  
- src/yieldex/notifications.py — Telegram alert subsystem.  
- src/yieldex/data_collector.py — Data fetching, database updates, Mantle oracle updates.  
- src/yieldex/analytics.py — Yield analysis and recommendation generation.  
- src/sql/ — Folder with migrations and stored procedures for Supabase.

---

## Additional Information

- [manifesto.md](manifesto.md) outlines the project's conceptual idea.  
- [Roadmap_MVP.md](Roadmap_MVP.md) details the upcoming plan for development (Phase 1 — MVP).

If you have any questions about how this repository works or suggestions for improvements, please open an Issue or Pull Request on GitHub.

Thank you for using Yieldex!