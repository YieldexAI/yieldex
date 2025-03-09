// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "./SmartAgent.sol";

contract SmartAgentFactory {
    event AgentCreated(address indexed owner, address agent);

    address public immutable admin;
    mapping(address => address) public agents;

    constructor(address _admin) {
        admin = _admin;
    }

    function createAgent() external {
        require(agents[msg.sender] == address(0), "Agent already exists");
        SmartAgent agent = new SmartAgent(admin);
        agents[msg.sender] = address(agent);
        emit AgentCreated(msg.sender, address(agent));
    }
} 