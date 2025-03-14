#!/usr/bin/env python
"""
Silo Finance Demo Script

This script demonstrates how to interact with Silo Finance protocol
to deposit and withdraw USDC.E from a specified market.

Usage:
  python -m src.onchain.silo_demo [--deposit amount] [--withdraw amount] [--market market_id]
  
Examples:
  python -m src.onchain.silo_demo --deposit 10
  python -m src.onchain.silo_demo --withdraw 5
  python -m src.onchain.silo_demo --market 20
"""

import argparse
import logging
import sys
import time
from pathlib import Path

# Add project root to path for imports
current_dir = Path(__file__).parent
project_root = current_dir.parent.parent
sys.path.insert(0, str(project_root))

from src.onchain.protocol_fabric import SiloOperator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def check_wallet_balance(operator):
    """Check wallet balance of USDC.E"""
    try:
        # Удаляем неправильную проверку аккаунта
        # if operator.network not in operator.w3.eth.accounts:
        #     logger.error(f"Account not available in {operator.network} network")
        #     return None
            
        # Get USDC.E token address from common/config.py 
        from src.common.config import STABLECOINS
        if "USDC.E" not in STABLECOINS or operator.network not in STABLECOINS["USDC.E"]:
            logger.error(f"USDC.E token not configured for {operator.network}")
            return None
            
        token_address = STABLECOINS["USDC.E"][operator.network]
        
        # Load ERC20 ABI
        with open(Path(__file__).parent.parent / "common" / "abi" / "ERC20.json") as f:
            import json
            abi = json.load(f)
            
        # Create token contract
        token = operator.w3.eth.contract(address=token_address, abi=abi)
        
        # Get balance
        balance = token.functions.balanceOf(operator.account.address).call()
        decimals = token.functions.decimals().call()
        balance_human = balance / 10**decimals
        
        logger.info(f"Wallet balance: {balance_human} USDC.E")
        return balance_human
        
    except Exception as e:
        logger.error(f"Error checking wallet balance: {str(e)}")
        return None

def display_market_info(operator, market_id):
    """Display information about a specific Silo market"""
    try:
        print(f"\n=== Market {market_id} Information ===")
        
        # Get all silos for this market
        silos = operator.find_silos_for_market(market_id)
        
        if not silos:
            print(f"No silos found for market {market_id}")
            return
            
        print(f"Found {len(silos)} silos:")
        
        for i, silo in enumerate(silos, 1):
            silo_address = silo.get("silo_address")
            silo_type = "Protected" if silo.get("silo_type") == 1 else "Standard"
            token_info = silo.get("token_info", {})
            
            print(f"\nSilo {i}: {silo_type}")
            print(f"  Address: {silo_address}")
            print(f"  Name: {token_info.get('silo_name', token_info.get('name', 'Unknown'))}")
            print(f"  Symbol: {token_info.get('silo_symbol', token_info.get('symbol', 'Unknown'))}")
            
            # Check our balance in this silo
            balance = operator.get_silo_balance(silo_address)
            print(f"  Our balance: {balance}")
            
    except Exception as e:
        logger.error(f"Error displaying market info: {str(e)}")

def run_deposit_flow(operator, amount):
    """Run the deposit flow for USDC.E"""
    try:
        print(f"\n=== Depositing {amount} USDC.E ===")
        
        # Check wallet balance first
        wallet_balance = check_wallet_balance(operator)
        if wallet_balance is None:
            return
            
        if wallet_balance < amount:
            print(f"Insufficient wallet balance: {wallet_balance} USDC.E")
            return
            
        # Get current balance in Silo
        before_balance = operator.get_token_balance("USDC.E")
        print(f"Current balance in Silo: {before_balance} USDC.E")
        
        # Execute deposit
        print(f"Depositing {amount} USDC.E...")
        tx_hash = operator.supply("USDC.E", amount)
        
        if not tx_hash:
            print("Deposit failed!")
            return
            
        print(f"Deposit submitted! Transaction: {tx_hash}")
        print("Waiting for confirmation...")
        
        # Wait a bit for the transaction to be processed
        time.sleep(5)
        
        # Check new balance
        after_balance = operator.get_token_balance("USDC.E")
        print(f"New balance in Silo: {after_balance} USDC.E")
        
        if after_balance > before_balance:
            print(f"Successfully deposited {after_balance - before_balance} USDC.E")
        else:
            print("Deposit might not have been processed yet or failed")
            
    except Exception as e:
        logger.error(f"Error in deposit flow: {str(e)}")

def run_withdraw_flow(operator, amount=None, withdraw_all=False, force_withdrawal=False):
    """
    Run the withdrawal flow from Silo
    
    Args:
        operator: SiloOperator instance
        amount: Amount to withdraw (optional)
        withdraw_all: Whether to withdraw all available funds
        force_withdrawal: Whether to attempt withdrawal of all funds even if not all is immediately available
    """
    try:
        print("\n=== Withdrawing from USDC.E Silo ===")
        
        # Find USDC.E Silo
        silos = operator.find_silos_for_market(operator.market_id)
        if not silos:
            print(f"No silos found for market {operator.market_id}")
            return
            
        # First try to find the USDC.E Protected silo directly by its known address
        usdc_silo = "0x4E216C15697C1392fE59e1014B009505E05810Df"  # Known USDC.E Protected silo address
        silo_type = "Protected"
        
        # Verify that the silo exists in our list
        if usdc_silo in silos:
            print(f"Found USDC.E Protected Silo: {usdc_silo}")
        else:
            print(f"Known USDC.E silo address not found in the list of silos, searching by info...")
            
            # Fall back to finding by info
            for silo in silos:
                # Make sure we're working with the silo address as string, not a dict
                silo_address = silo if isinstance(silo, str) else silo.get('silo_address', '')
                
                try:
                    silo_info = operator.get_silo_info(silo_address)
                    
                    if silo_info and 'symbol' in silo_info:
                        symbol = silo_info.get('symbol', '').upper()
                        name = silo_info.get('name', '').upper()
                        
                        if 'USDC' in symbol or 'USDC' in name:
                            usdc_silo = silo_address
                            
                            if 'PROTECTED' in symbol or 'PROTECTED' in name:
                                silo_type = "Protected"
                                print(f"Found USDC.E Protected Silo by info: {usdc_silo}")
                                break
                            elif 'STANDARD' in symbol or 'STANDARD' in name:
                                silo_type = "Standard" 
                                print(f"Found USDC.E Standard Silo by info: {usdc_silo}")
                except Exception as e:
                    logger.warning(f"Error checking silo {silo_address}: {e}")
                    
        # Get current balance and withdrawal info
        balance = operator.get_silo_balance(usdc_silo)
        print(f"Current balance in Silo: {balance} USDC.E")
        
        # Get detailed withdrawal information
        collateral_type = operator.CollateralType.PROTECTED if silo_type == "Protected" else operator.CollateralType.STANDARD
        withdrawal_info = operator.get_withdrawal_info(usdc_silo, collateral_type)
        
        print("\n=== Silo Liquidity Information ===")
        print(f"Total balance: {withdrawal_info['total_balance']:.8f} USDC.E")
        print(f"Available for withdrawal: {withdrawal_info['available_balance']:.8f} USDC.E")
        print(f"Liquidity percentage: {withdrawal_info['liquidity_percentage']:.4f}%")
        print("Note: In lending protocols like Silo, not all funds are immediately available for withdrawal.")
        print("      This is because funds are being used to generate yield (current APR: 3.1%).")
        print("      The remaining balance will become available as borrowers repay loans or as liquidity increases.")
        
        if force_withdrawal:
            print("\n!!! FORCE WITHDRAWAL MODE ENABLED !!!")
            print("Will attempt to withdraw the full amount, but protocol may partially fulfill the request.")
        
        # Determine withdrawal amount
        if withdraw_all:
            if force_withdrawal:
                # Use total balance for force withdrawal
                amount = withdrawal_info['total_balance']
                print(f"Requesting withdrawal of entire balance: {amount:.8f} USDC.E")
                print(f"Note: Only about {withdrawal_info['liquidity_percentage']:.2f}% ({withdrawal_info['available_balance']:.8f} USDC.E) is likely to be processed immediately.")
            else:
                # Use only available amount for normal withdrawal
                amount = withdrawal_info['available_balance']
                print(f"Withdrawing all available funds: {amount:.8f} USDC.E")
                print(f"This represents {withdrawal_info['liquidity_percentage']:.2f}% of your total balance of {withdrawal_info['total_balance']:.8f} USDC.E")
        elif amount is None:
            # Default to a small amount if none specified
            amount = min(0.001, withdrawal_info['available_balance'])
            print(f"No amount specified, using default: {amount:.8f} USDC.E")
        elif amount > withdrawal_info['available_balance'] and not force_withdrawal:
            print(f"Requested amount ({amount:.8f}) exceeds maximum, adjusting to: {withdrawal_info['available_balance']:.8f} USDC.E")
            amount = withdrawal_info['available_balance']
        elif amount > withdrawal_info['total_balance']:
            print(f"Requested amount ({amount:.8f}) exceeds total balance, adjusting to: {withdrawal_info['total_balance']:.8f} USDC.E")
            amount = withdrawal_info['total_balance']
            
        if amount <= 0:
            print("Nothing to withdraw")
            return
            
        # Confirm with user
        confirm = input(f"Proceed with withdrawal of {amount:.8f} USDC.E? (y/n): ")
        if confirm.lower() != 'y':
            print("Withdrawal cancelled")
            return
            
        # Execute withdrawal
        print(f"Withdrawing {amount:.8f} USDC.E...")
        tx_hash = operator.withdraw(
            usdc_silo, 
            amount,
            collateral_type,
            force_withdrawal  # Pass the force_withdrawal flag
        )
        
        if not tx_hash:
            print("Withdrawal failed!")
            return
            
        print(f"Withdrawal submitted! Transaction: {tx_hash}")
        print("Waiting for confirmation...")
        
        # Wait a bit for the transaction to be processed
        time.sleep(5)
        
        # Check new balance
        balance = operator.get_silo_balance(usdc_silo)
        print(f"New balance in Silo: {balance} USDC.E")
            
        # Check wallet balance
        check_wallet_balance(operator)
        
    except Exception as e:
        print(f"Error in withdrawal flow: {e}")
        logger.error(f"Error in withdrawal flow: {e}", exc_info=True)

def main():
    """Main function"""
    try:
        parser = argparse.ArgumentParser(description='Silo Finance Demo')
        parser.add_argument('--market', type=str, default="8", help='Market ID to interact with')
        parser.add_argument('--network', type=str, default="Sonic", help='Network to use (Ethereum, Arbitrum, etc.)')
        parser.add_argument('--deposit', type=float, help='Deposit amount')
        parser.add_argument('--withdraw', type=float, help='Withdraw amount')
        parser.add_argument('--all', action='store_true', help='Withdraw all available funds')
        parser.add_argument('--force-all', action='store_true', help='Force withdraw all funds (protocol may fulfill partially)')
        
        args = parser.parse_args()
        
        market_id = args.market
        network = args.network
        
        print(f"\n=== Silo Finance Demo for Market {market_id} on {network} ===")
        
        # Initialize operator
        operator = SiloOperator(network, market_id)
        
        # Display market information
        display_market_info(operator, market_id)
        
        # Check wallet balance
        check_wallet_balance(operator)
        
        # Run deposit or withdrawal flow based on arguments
        if args.deposit is not None:
            run_deposit_flow(operator, args.deposit)
        elif args.withdraw is not None or args.all or args.force_all:
            run_withdraw_flow(operator, args.withdraw, args.all, args.force_all)
        else:
            # Just check balance
            balance = operator.get_token_balance("USDC.E")
            print(f"\nCurrent USDC.E balance in market {market_id}: {balance}")
                
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        print(f"ERROR: {str(e)}")
        return 1
        
    return 0

if __name__ == "__main__":
    sys.exit(main()) 