Description - Yieldex is a stablecoin yield optimizer for EVM. AAVE is the first protocol for integration.
It analyzes current yield percentages across different AAVE networks and automatically transfers stablecoins like (DAI, USDT, USDC, GHO) to the target network (where AAVE operates) to increase APY/APR.

Architecture:
3 modules working together:

1) Data Collection Module
2) Decision Making Module  
3) On-chain Interaction Module

Detailed module responsibilities:

1) Data Collection Module - collects data from public sources about current APR/APY percentages, forms datasets and writes this data to the database with selected periodicity
2) Analytics Module - uses aggregated data obtained from module #1 to form "calls to action", evaluates the potential of transferring funds from the current USDT pool in AAVE, for example from Optimism network with 5% APY to the USDT pool in Base network with 8% APY
3) Onchain Module - set of tools that allow forming and sending blockchain transactions to execute fund transfers - executes the "call to action" created in the analytics module

Technical description in Roadmap_MVP.md document
