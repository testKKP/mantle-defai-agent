// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import {Test, console} from "forge-std/Test.sol";
import {MantleDeFAIRegistry} from "../src/MantleDeFAIRegistry.sol";

contract MantleDeFAIRegistryTest is Test {
    MantleDeFAIRegistry public registry;

    address owner = address(1);
    address submitter = address(2);
    address subscriber = address(3);
    address stranger = address(4);

    uint256 constant PRICE = 10 ether;
    uint256 constant DURATION = 30 days;

    function setUp() public {
        vm.prank(owner);
        address[] memory submitters = new address[](1);
        submitters[0] = submitter;
        registry = new MantleDeFAIRegistry(PRICE, DURATION, submitters);
    }

    function test_Subscribe() public {
        vm.deal(subscriber, 100 ether);

        vm.prank(subscriber);
        registry.subscribe{value: PRICE}();

        (uint256 expiry, uint256 totalPaid, bool active) = registry.getSubscription(subscriber);
        assertTrue(active);
        assertEq(totalPaid, PRICE);
        assertGt(expiry, block.timestamp);
    }

    function test_Subscribe_RevertIfInsufficientPayment() public {
        vm.deal(subscriber, 100 ether);
        vm.prank(subscriber);
        vm.expectRevert(MantleDeFAIRegistry.InvalidPrice.selector);
        registry.subscribe{value: PRICE - 1}();
    }

    function test_SubmitSignal() public {
        bytes memory encrypted = hex"deadbeef";
        bytes32 hash = keccak256("test");

        vm.prank(submitter);
        registry.submitSignal("BTC", "1d", encrypted, hash);

        assertEq(registry.getSignalCount("BTC", "1d"), 1);
    }

    function test_GetLatestSignal_OnlySubscribed() public {
        // submit a signal first
        vm.prank(submitter);
        registry.submitSignal("BTC", "1d", hex"abcd", keccak256("test"));

        // non-subscriber should revert
        vm.prank(stranger);
        vm.expectRevert(abi.encodeWithSelector(MantleDeFAIRegistry.NotSubscribed.selector, stranger));
        registry.getLatestSignal("BTC", "1d");

        // subscriber should succeed
        vm.deal(subscriber, 100 ether);
        vm.prank(subscriber);
        registry.subscribe{value: PRICE}();

        vm.prank(subscriber);
        MantleDeFAIRegistry.Signal memory sig = registry.getLatestSignal("BTC", "1d");
        assertEq(sig.dataHash, keccak256("test"));
    }

    function test_SubmitSignalsBatch() public {
        string[] memory symbols = new string[](2);
        symbols[0] = "BTC";
        symbols[1] = "ETH";

        string[] memory tfs = new string[](2);
        tfs[0] = "1d";
        tfs[1] = "4h";

        bytes[] memory data = new bytes[](2);
        data[0] = hex"aa";
        data[1] = hex"bb";

        bytes32[] memory hashes = new bytes32[](2);
        hashes[0] = keccak256("btc");
        hashes[1] = keccak256("eth");

        vm.prank(submitter);
        registry.submitSignalsBatch(symbols, tfs, data, hashes);

        assertEq(registry.getSignalCount("BTC", "1d"), 1);
        assertEq(registry.getSignalCount("ETH", "4h"), 1);
    }

    function test_ReceiveAsSubscription() public {
        vm.deal(subscriber, 100 ether);
        vm.prank(subscriber);
        (bool success, ) = address(registry).call{value: PRICE}("");
        assertTrue(success);

        (, , bool active) = registry.getSubscription(subscriber);
        assertTrue(active);
    }

    function test_Withdraw() public {
        vm.deal(subscriber, 100 ether);
        vm.prank(subscriber);
        registry.subscribe{value: PRICE}();

        uint256 before = owner.balance;

        vm.prank(owner);
        registry.withdraw(payable(owner));

        assertEq(owner.balance, before + PRICE);
    }

    function test_AuthorizedSubmitterManagement() public {
        address newSubmitter = address(5);

        vm.prank(owner);
        registry.addAuthorizedSubmitter(newSubmitter);
        assertTrue(registry.authorizedSubmitters(newSubmitter));

        vm.prank(owner);
        registry.removeAuthorizedSubmitter(newSubmitter);
        assertFalse(registry.authorizedSubmitters(newSubmitter));
    }
}
