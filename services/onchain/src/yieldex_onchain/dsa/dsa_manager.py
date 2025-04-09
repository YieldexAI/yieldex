"""
DSA manager for creating and managing DSA accounts
"""
from web3 import Web3
import json
import os
import logging
from typing import Dict, List, Any, Tuple, Optional, Union

from ..constants.network_addresses import Network, get_chain_id
from ..constants.fluid_addresses import DSA_ADDRESSES

logger = logging.getLogger(__name__)

class DSAManager:
    """
    DSA manager for creating and managing DSA accounts
    
    This class provides a simple interface for creating and managing DSA accounts.
    DSA accounts are used to interact with DeFi protocols through Instadapp.
    """
    
    def __init__(self, operator, web3: Web3, network: str = 'arbitrum'):
        """
        Initialize DSA manager
        
        Args:
            operator: Protocol operator
            web3: Web3 instance
            network: Network name
        """
        self.operator = operator
        self.web3 = web3
        self.account = operator.account
        self.network = network
        
        # Load DSA contracts
        self._load_dsa_contracts()
        
        logger.info("DSA manager initialized")
        
    def _load_dsa_contracts(self):
        """Load DSA contracts and ABIs"""
        try:
            # Load DSA factory ABI
            common_abi_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'common/abi')
            insta_index_path = os.path.join(common_abi_dir, 'InstaDSAIndex.json')
            
            with open(insta_index_path, 'r') as f:
                self.dsa_factory_abi = json.load(f)
            
            # Добавляем методы, которые могут отсутствовать в ABI
            factory_build_method = {
                "constant": False,
                "inputs": [
                    {
                        "internalType": "address",
                        "name": "_owner",
                        "type": "address"
                    },
                    {
                        "internalType": "uint256",
                        "name": "_accountVersion",
                        "type": "uint256"
                    },
                    {
                        "internalType": "address",
                        "name": "_origin",
                        "type": "address"
                    }
                ],
                "name": "build",
                "outputs": [
                    {
                        "internalType": "address",
                        "name": "_account",
                        "type": "address"
                    }
                ],
                "payable": False,
                "stateMutability": "nonpayable",
                "type": "function"
            }
            
            # Обновленный метод для получения аккаунтов
            factory_get_accounts_method = {
                "constant": True,
                "inputs": [
                    {
                        "internalType": "address",
                        "name": "_owner",
                        "type": "address"
                    }
                ],
                "name": "getAccounts",
                "outputs": [
                    {
                        "components": [
                            {
                                "internalType": "uint256",
                                "name": "id",
                                "type": "uint256"
                            },
                            {
                                "internalType": "address",
                                "name": "account",
                                "type": "address"
                            },
                            {
                                "internalType": "uint256",
                                "name": "version",
                                "type": "uint256"
                            }
                        ],
                        "internalType": "struct AccountsContract.Record[]",
                        "name": "",
                        "type": "tuple[]"
                    }
                ],
                "payable": False,
                "stateMutability": "view",
                "type": "function"
            }
            
            # Добавляем/обновляем методы в ABI
            methods_exists = {'build': False, 'getAccounts': False}
            
            # Проверяем, есть ли build и getAccounts в ABI
            for i, method in enumerate(self.dsa_factory_abi):
                if method.get('name') == 'build':
                    self.dsa_factory_abi[i] = factory_build_method
                    methods_exists['build'] = True
                elif method.get('name') == 'getAccounts':
                    self.dsa_factory_abi[i] = factory_get_accounts_method
                    methods_exists['getAccounts'] = True
                # Устаревший метод - заменяем на новый
                elif method.get('name') == 'getAuthorityAccounts':
                    self.dsa_factory_abi[i] = factory_get_accounts_method
                    methods_exists['getAccounts'] = True
            
            # Если методов нет, добавляем их
            if not methods_exists['build']:
                self.dsa_factory_abi.append(factory_build_method)
            if not methods_exists['getAccounts']:
                self.dsa_factory_abi.append(factory_get_accounts_method)
            
            # Load DSA implementation ABI
            insta_dsa_path = os.path.join(common_abi_dir, 'InstaDSA.json')
            
            with open(insta_dsa_path, 'r') as f:
                self.dsa_implementation_abi = json.load(f)
            
            # Get DSA factory address from constants
            self.factory_address = DSA_ADDRESSES.get(self.network, {}).get('factory')
            if not self.factory_address:
                raise ValueError(f"No DSA factory address found for network: {self.network}")
            
            # Create DSA factory contract instance
            self.factory_contract = self.web3.eth.contract(
                address=Web3.to_checksum_address(self.factory_address),
                abi=self.dsa_factory_abi
            )
            
            logger.info(f"DSA factory loaded: {self.factory_address}")
            
        except Exception as e:
            logger.error(f"Error loading DSA contracts: {str(e)}")
            raise
            
    def get_dsa_accounts(self) -> List[Dict[str, Any]]:
        """
        Get DSA accounts for current address
        
        Returns:
            List of DSA accounts with id, address and version
        """
        try:
            # Сначала пробуем вызвать getAccounts (новый метод)
            try:
                accounts_raw = self.factory_contract.functions.getAccounts(
                    self.account.address
                ).call()
                
                accounts = []
                
                # Обрабатываем результат вызова getAccounts, который возвращает tuple[]
                for account in accounts_raw:
                    # account может быть tuple с id, address и version
                    if isinstance(account, tuple) and len(account) >= 3:
                        dsa_id, dsa_address, version = account
                        accounts.append({
                            'id': dsa_id,
                            'address': dsa_address,
                            'version': version
                        })
                    # Либо может быть dict с id, account и version
                    elif isinstance(account, dict):
                        accounts.append({
                            'id': account.get('id', 0),
                            'address': account.get('account', "0x0000000000000000000000000000000000000000"),
                            'version': account.get('version', 1)
                        })
                
                logger.info(f"Found {len(accounts)} DSA accounts using getAccounts method")
                return accounts
            
            except Exception as e:
                logger.warning(f"Error getting accounts with getAccounts: {str(e)}")
                
                # Если новый метод не сработал, пробуем getAuthorityAccounts
                try:
                    accounts_raw = self.factory_contract.functions.getAuthorityAccounts(
                        self.account.address
                    ).call()
                    
                    accounts = []
                    
                    # Обрабатываем результат вызова getAuthorityAccounts
                    for account in accounts_raw:
                        if isinstance(account, tuple) and len(account) >= 3:
                            dsa_id, dsa_address, version = account
                            accounts.append({
                                'id': dsa_id,
                                'address': dsa_address,
                                'version': version
                            })
                    
                    logger.info(f"Found {len(accounts)} DSA accounts using getAuthorityAccounts method")
                    return accounts
                    
                except Exception as e2:
                    logger.warning(f"Error getting accounts with getAuthorityAccounts: {str(e2)}")
                    
                    # Если и этот метод не сработал, последняя попытка - пробуем обойти проблему
                    try:
                        # Собираем события AccountCreated для нашего адреса
                        events = self.factory_contract.events.LogAccountCreated.getLogs(
                            fromBlock=0,  # В идеале указать более оптимальный диапазон блоков
                            toBlock="latest",
                            argument_filters={"owner": self.account.address}
                        )
                        
                        accounts = []
                        
                        for event in events:
                            accounts.append({
                                'id': event.args.id,
                                'address': event.args.account,
                                'version': event.args.version
                            })
                            
                        logger.info(f"Found {len(accounts)} DSA accounts using events")
                        return accounts
                        
                    except Exception as e3:
                        logger.error(f"Failed to get accounts using events: {str(e3)}")
                        return []
            
        except Exception as e:
            logger.error(f"Error getting DSA accounts: {str(e)}")
            return []
            
    def create_dsa_account(self) -> Tuple[int, str]:
        """
        Create a new DSA account or get existing one
        
        Returns:
            Tuple with DSA ID and address
        """
        # Check if DSA account already exists
        accounts = self.get_dsa_accounts()
        
        if accounts:
            logger.info(f"Using existing DSA account: {accounts[0]}")
            return accounts[0]['id'], accounts[0]['address']
        
        logger.info("No DSA accounts found, creating new one...")
        
        try:
            # Call build method to create a new DSA account
            tx_function = self.factory_contract.functions.build(
                self.account.address,  # _owner
                1,                   # _accountVersion - Usually version 1
                self.account.address   # _origin
            )
            
            # Prepare and send transaction using operator
            tx_hash = self.operator._send_transaction(tx_function)
            
            if tx_hash:
                logger.info(f"DSA account creation transaction sent: {tx_hash}")
                
                # Get the transaction receipt
                receipt = self.web3.eth.wait_for_transaction_receipt(tx_hash)
                
                # Extract the DSA address from the event
                logs = self.factory_contract.events.LogAccountCreated().process_receipt(receipt)
                
                if logs:
                    dsa_id = logs[0]['args']['id']
                    dsa_address = logs[0]['args']['account']
                    logger.info(f"DSA account created: ID={dsa_id}, Address={dsa_address}")
                    return dsa_id, dsa_address
                else:
                    logger.error("DSA account creation failed: No LogAccountCreated event found")
                    return 0, ""
            else:
                logger.error("DSA account creation failed: Transaction failed")
                return 0, ""
                
        except Exception as e:
            logger.error(f"Error creating DSA account: {str(e)}")
            return 0, ""
            
    def get_dsa_contract(self, dsa_address: str):
        """
        Get DSA contract instance
        
        Args:
            dsa_address: DSA account address
            
        Returns:
            Contract instance
        """
        try:
            # Create DSA implementation contract instance (for a specific DSA account)
            dsa_contract = self.web3.eth.contract(
                address=Web3.to_checksum_address(dsa_address),
                abi=self.dsa_implementation_abi
            )
            
            return dsa_contract
            
        except Exception as e:
            logger.error(f"Error getting DSA contract: {str(e)}")
            raise 