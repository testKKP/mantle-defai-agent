// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import {Script, console} from "forge-std/Script.sol";
import {MantleDeFAIRegistry} from "../src/MantleDeFAIRegistry.sol";

/**
 * @title DeployRegistry
 * @notice Deployment script for MantleDeFAIRegistry on Mantle Sepolia Testnet.
 *
 * Usage:
 *   forge script script/DeployRegistry.s.sol:DeployRegistry \
 *     --rpc-url mantleSepolia \
 *     --broadcast \
 *     --private-key $PRIVATE_KEY
 *
 * Environment variables:
 *   - PRIVATE_KEY: deployer private key (with Sepolia MNT from faucet)
 *   - INITIAL_SUBMITTER_1: first authorized backend submitter address
 */
contract DeployRegistry is Script {
    // Subscription price: 10 MNT (18 decimals)
    uint256 constant SUBSCRIPTION_PRICE = 10 ether;

    // Subscription duration: 30 days
    uint256 constant SUBSCRIPTION_DURATION = 30 days;

    function run() external returns (MantleDeFAIRegistry) {
        uint256 deployerPrivateKey = vm.envUint("PRIVATE_KEY");

        // Read optional authorized submitter from env, fallback to deployer
        address initialSubmitter = vm.envOr("INITIAL_SUBMITTER", vm.addr(deployerPrivateKey));

        address[] memory submitters = new address[](1);
        submitters[0] = initialSubmitter;

        vm.startBroadcast(deployerPrivateKey);

        MantleDeFAIRegistry registry = new MantleDeFAIRegistry(
            SUBSCRIPTION_PRICE,
            SUBSCRIPTION_DURATION,
            submitters
        );

        vm.stopBroadcast();

        console.log("MantleDeFAIRegistry deployed at:", address(registry));
        console.log("  Subscription price:", SUBSCRIPTION_PRICE);
        console.log("  Subscription duration:", SUBSCRIPTION_DURATION);
        console.log("  Initial submitter:", initialSubmitter);

        return registry;
    }
}
