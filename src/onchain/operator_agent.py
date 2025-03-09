from web3 import Web3
import json
from typing import List, Dict
from .config import RPC_URLS, PRIVATE_KEY, ADMIN_ADDRESS
from .protocol_fabric import AaveOperator

class AgentOperator:
    def __init__(self, network: str):
        self.w3 = Web3(Web3.HTTPProvider(RPC_URLS[network]))
        self.account = self.w3.eth.account.from_key(PRIVATE_KEY)
        self.factory_address = None  # Set after deployment
        self.agents = []

    def load_agents_from_db(self):
        """Load agents from Supabase database"""
        from supabase import create_client
        from common.config import SUPABASE_URL, SUPABASE_KEY
        
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        result = supabase.table('agents').select('*').execute()
        self.agents = [a['address'] for a in result.data]

    def execute_on_agents(self, calls: List[Dict]):
        """Execute batch operations on all agents"""
        for agent in self.agents:
            for call in calls:
                self._build_and_send_tx(
                    agent_address=agent,
                    target=call['target'],
                    data=call['data'],
                    value=call.get('value', 0)
                )

    def _build_and_send_tx(self, agent_address: str, target: str, data: str, value: int = 0):
        contract = self.w3.eth.contract(
            address=agent_address,
            abi=json.load(open('abi/SmartAgent.json'))
        )
        
        tx = contract.functions.execute(target, data, value).build_transaction({
            'from': ADMIN_ADDRESS,
            'gas': 500000,
            'nonce': self.w3.eth.get_transaction_count(ADMIN_ADDRESS)
        })
        
        signed_tx = self.account.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)
        return tx_hash.hex()

def process_recommendations(recommendations: List[Dict]):
    operator = AgentOperator(network='Sonic')
    operator.load_agents_from_db()
    
    calls = []
    for rec in recommendations:
        aave = AaveOperator(rec['chain'], 'aave-v3')
        calls.append({
            'target': aave.pool_address,
            'data': aave.build_deposit_calldata(
                token=rec['token'],
                amount=rec['amount']
            )
        })
    
    operator.execute_on_agents(calls) 