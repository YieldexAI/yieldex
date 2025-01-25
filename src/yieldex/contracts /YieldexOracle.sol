// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title YieldexOracle
 * @dev Decentralized APY storage for stablecoin pools with Mantle support
 */
contract YieldexOracle {
    // Contract admin (only they can update data)
    address public admin;
    
    // Structure for storing pool data
    struct PoolData {
        uint256 apy;         // APY in format 5% = 500 (2 decimal places)
        uint256 timestamp;   // Last update time
        string poolId;       // Pool identifier (e.g. "mantle-lendle-usdt")
    }
    
    // Mapping to store data by unique key
    mapping(string => PoolData) public pools;
    
    // Events for tracking changes
    event ApyUpdated(string indexed poolId, uint256 newApy, uint256 timestamp);
    event AdminChanged(address indexed oldAdmin, address newAdmin);

    constructor(address _admin) {
        admin = _admin;
    }

    modifier onlyAdmin() {
        require(msg.sender == admin, "Only admin");
        _;
    }

    /**
     * @dev Update APY for pool (called by backend)
     * @param poolId Unique pool identifier (e.g. "arbitrum-aave-usdc")
     * @param apy New APY value (in format 5% = 500)
     */
    function updateApy(string memory poolId, uint256 apy) external onlyAdmin {
        require(apy <= 10_000, "APY cannot exceed 10000 (100%)");
        
        pools[poolId] = PoolData({
            apy: apy,
            timestamp: block.timestamp,
            poolId: poolId
        });
        
        emit ApyUpdated(poolId, apy, block.timestamp);
    }

    /**
     * @dev Get pool data
     * @param poolId Unique pool identifier
     * @return apy Current APY value
     * @return timestamp Last update time
     */
    function getApy(string memory poolId) external view returns (uint256 apy, uint256 timestamp) {
        PoolData memory data = pools[poolId];
        require(data.timestamp > 0, "Pool not found");
        return (data.apy, data.timestamp);
    }

    /**
     * @dev Change admin (only current admin)
     * @param newAdmin New admin address
     */
    function changeAdmin(address newAdmin) external onlyAdmin {
        require(newAdmin != address(0), "Invalid address");
        emit AdminChanged(admin, newAdmin);
        admin = newAdmin;
    }
}