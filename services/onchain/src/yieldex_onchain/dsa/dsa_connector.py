"""
DSA connector for interacting with DeFi protocols through DSA
"""
from web3 import Web3
import json
import os
import logging
from typing import Dict, List, Any, Optional

from .dsa_manager import DSAManager
from ..constants.fluid_addresses import DSA_CONNECTORS, DSA_CONNECTOR_ADDRESSES

logger = logging.getLogger(__name__)

class DSAConnector:
    """
    DSA connector for interacting with DeFi protocols
    
    This class provides a simple interface for interacting with DeFi protocols
    through DSA (DeFi Smart Accounts). Реализация основана на официальном SDK
    Instadapp DSA Connect (https://github.com/Instadapp/dsa-connect).
    """
    
    def __init__(self, dsa_manager: DSAManager):
        """
        Initialize DSA connector
        
        Args:
            dsa_manager: DSA manager instance
        """
        self.dsa_manager = dsa_manager
        self.operator = dsa_manager.operator
        self.web3 = dsa_manager.web3
        self.account = dsa_manager.account
        self.network = dsa_manager.network
        
        # Load connector ABIs
        self._load_connectors()
        
        logger.info("DSA connector initialized")
        
    def _load_connectors(self):
        """Load connector ABIs"""
        try:
            # Базовые методы для Fluid коннектора (ERC20 Vault)
            self.fluid_connector_abi = [
                {
                    "inputs": [
                        {"name": "token", "type": "address"},
                        {"name": "amount", "type": "uint256"},
                        {"name": "getId", "type": "uint256"},
                        {"name": "setId", "type": "uint256"}
                    ],
                    "name": "deposit",
                    "outputs": [],
                    "stateMutability": "nonpayable",
                    "type": "function"
                },
                {
                    "inputs": [
                        {"name": "token", "type": "address"},
                        {"name": "amount", "type": "uint256"},
                        {"name": "to", "type": "address"},
                        {"name": "getId", "type": "uint256"},
                        {"name": "setId", "type": "uint256"}
                    ],
                    "name": "withdraw",
                    "outputs": [],
                    "stateMutability": "nonpayable",
                    "type": "function"
                }
            ]
            
            # Получаем идентификаторы коннекторов
            if self.network not in DSA_CONNECTORS:
                raise ValueError(f"No DSA connectors defined for network: {self.network}")
                
            self.connector_ids = DSA_CONNECTORS[self.network]
            
            # Получаем адреса коннекторов
            self.connector_addresses = DSA_CONNECTOR_ADDRESSES.get(self.network, {})
            logger.info(f"Loaded connector addresses: {self.connector_addresses}")
            
            # Проверяем адрес Fluid коннектора
            if 'FLUID-A' not in self.connector_addresses or self.connector_addresses['FLUID-A'] == '0x0000000000000000000000000000000000000000':
                logger.warning("Fluid connector address is not properly configured!")
            
        except Exception as e:
            logger.error(f"Error loading DSA connectors: {str(e)}")
            raise
    
    def _approve_token(self, token_address: str, dsa_address: str, amount: int) -> str:
        """
        Approve tokens for DSA to spend
        
        Args:
            token_address: Token address
            dsa_address: DSA account address
            amount: Amount to approve
            
        Returns:
            Transaction hash
        """
        # Load ERC20 ABI for token
        common_abi_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'common/abi')
        erc20_path = os.path.join(common_abi_dir, 'ERC20.json')
        
        with open(erc20_path, 'r') as f:
            erc20_abi = json.load(f)
        
        # Create token contract
        token_contract = self.web3.eth.contract(
            address=Web3.to_checksum_address(token_address),
            abi=erc20_abi
        )
        
        # Check current allowance
        allowance = token_contract.functions.allowance(
            self.account.address,
            dsa_address
        ).call()
        
        if allowance >= amount:
            logger.info(f"Token already approved: {allowance} >= {amount}")
            return None
        
        logger.info(f"Approving {amount} tokens for DSA: {dsa_address}")
        
        # Используем _send_transaction вместо собственной логики
        tx_function = token_contract.functions.approve(
            dsa_address,
            amount
        )
        
        tx_hash = self.operator._send_transaction(tx_function)
        if tx_hash:
            logger.info(f"Approval transaction sent: {tx_hash}")
            return tx_hash
        else:
            logger.error("Approval failed")
            return None
    
    class Spell:
        """
        Spell class - аналог DSA.Spell() из DSA Connect
        Spell позволяет добавлять и выполнять последовательность операций в DeFi протоколах
        """
        def __init__(self, connector):
            self.connector = connector
            self.actions = []
            
        def add(self, action):
            """
            Добавить действие в заклинание
            
            Args:
                action: Действие с полями connector, method и args
            """
            self.actions.append(action)
            return self
            
        def cast(self, options=None):
            """
            Выполнить заклинание (отправить транзакцию)
            
            Args:
                options: Дополнительные настройки (gasPrice, value, nonce)
                
            Returns:
                Transaction hash
            """
            # Получить текущий DSA аккаунт
            accounts = self.connector.dsa_manager.get_dsa_accounts()
            if not accounts:
                logger.error("No DSA accounts found. Create one first.")
                return None
                
            dsa_address = accounts[0]['address']
            
            # Выполнить заклинание
            return self.connector._create_spell(dsa_address, self.actions, options)
    
    def get_spell(self):
        """
        Создать новое заклинание (Spell)
        
        Returns:
            Spell instance
        """
        return self.Spell(self)
    
    def _create_spell(self, dsa_address: str, actions: List[Dict[str, Any]], options: Dict[str, Any] = None) -> str:
        """
        Create and cast a spell (execute operations through DSA)
        
        Args:
            dsa_address: DSA account address
            actions: List of actions to perform
            options: Additional options (gasPrice, value, nonce)
            
        Returns:
            Transaction hash
        """
        # Get DSA contract
        dsa_contract = self.dsa_manager.get_dsa_contract(dsa_address)
        
        # Process actions into targets and data
        targets = []
        datas = []
        
        for action in actions:
            connector_id = action['connector']
            method = action['method']
            args = action['args']
            
            # Получаем адрес коннектора из нашего реестра
            if connector_id in self.connector_addresses:
                connector_address = self.connector_addresses[connector_id]
            elif connector_id in self.connector_ids and self.connector_ids[connector_id] in self.connector_addresses:
                # Пробуем по идентификатору из маппинга
                connector_address = self.connector_addresses[self.connector_ids[connector_id]]
            else:
                logger.warning(f"Connector address not found for {connector_id}, using placeholder")
                connector_address = "0x0000000000000000000000000000000000000000"
                logger.error(f"Cannot continue with invalid connector address")
                return None
            
            logger.info(f"Using connector {connector_id} at address {connector_address}")
            
            # Get connector ABI based on type
            if connector_id == 'fluid' or connector_id == self.connector_ids.get('fluid'):
                connector_abi = self.fluid_connector_abi
            else:
                # Для других коннекторов используем базовый ERC20 ABI
                connector_abi = self.fluid_connector_abi  # Временное решение
            
            # Create a contract instance for encoding the call
            connector_contract = self.web3.eth.contract(
                address=Web3.to_checksum_address(connector_address),
                abi=connector_abi
            )
            
            # Encode the function call
            data = connector_contract.encodeABI(fn_name=method, args=args)
            
            targets.append(Web3.to_checksum_address(connector_address))
            datas.append(data)
        
        logger.info(f"Creating spell with {len(actions)} actions")
        
        # Создаем базовые параметры транзакции
        tx_params = {}
        if options:
            if 'value' in options and options['value']:
                tx_params['value'] = options['value']
        
        # Используем _send_transaction вместо собственной логики
        tx_function = dsa_contract.functions.cast(
            targets,
            datas,
            self.account.address  # Origin
        )
        
        tx_hash = self.operator._send_transaction(tx_function)
        if tx_hash:
            logger.info(f"Spell cast successful: {tx_hash}")
            return tx_hash
        else:
            logger.error("Spell cast failed")
            return None
    
    def deposit_to_fluid(self, token_address: str, amount: int) -> str:
        """
        Deposit tokens to Fluid through DSA (using Spell pattern from DSA Connect)
        
        Args:
            token_address: Token address
            amount: Amount to deposit
            
        Returns:
            Transaction hash
        """
        # Get or create DSA account
        dsa_id, dsa_address = self.dsa_manager.create_dsa_account()
        
        if not dsa_address:
            logger.error("Failed to get or create DSA account")
            return None
        
        # Approve tokens for DSA
        approve_tx = self._approve_token(token_address, dsa_address, amount)
        if not approve_tx and amount > 0:
            logger.error("Failed to approve tokens for DSA")
            return None
        
        # Создаем заклинание (Spell) в стиле DSA Connect
        spell = self.get_spell()
        
        # Добавляем операцию депозита
        spell.add({
            'connector': self.connector_ids.get('fluid', 'FLUID-A'),
            'method': 'deposit',
            'args': [
                Web3.to_checksum_address(token_address), 
                amount, 
                0,  # getId
                0   # setId
            ]
        })
        
        # Выполняем заклинание
        return spell.cast()
    
    def withdraw_from_fluid(self, token_address: str, amount: int) -> str:
        """
        Withdraw tokens from Fluid through DSA (using Spell pattern from DSA Connect)
        
        Args:
            token_address: Token address
            amount: Amount to withdraw
            
        Returns:
            Transaction hash
        """
        # Get DSA accounts
        accounts = self.dsa_manager.get_dsa_accounts()
        
        if not accounts:
            logger.error("No DSA accounts found. Create one first.")
            return None
        
        # Создаем заклинание (Spell) в стиле DSA Connect
        spell = self.get_spell()
        
        # Добавляем операцию вывода
        spell.add({
            'connector': self.connector_ids.get('fluid', 'FLUID-A'),
            'method': 'withdraw',
            'args': [
                Web3.to_checksum_address(token_address), 
                amount, 
                Web3.to_checksum_address(self.account.address),  # to
                0,  # getId
                0   # setId
            ]
        })
        
        # Выполняем заклинание
        return spell.cast() 