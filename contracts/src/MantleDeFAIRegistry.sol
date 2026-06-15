// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

/**
 * @title MantleDeFAIRegistry
 * @notice On-chain signal registry with subscription-based access control.
 *         Signals are encrypted before storage. Only active subscribers
 *         can read decrypted signals (via off-chain key distribution).
 */
contract MantleDeFAIRegistry {
    /*//////////////////////////////////////////////////////////////
                                 ERRORS
    //////////////////////////////////////////////////////////////*/
    error NotSubscribed(address user);
    error InvalidPrice();
    error ExpiredSubscription();
    error AlreadySubscribed();
    error EmptyData();
    error InvalidTimeframe();

    /*//////////////////////////////////////////////////////////////
                                 EVENTS
    //////////////////////////////////////////////////////////////*/
    event SignalSubmitted(
        string indexed symbol,
        string indexed timeframe,
        bytes32 dataHash,
        uint256 timestamp,
        uint256 signalId
    );
    event Subscribed(address indexed user, uint256 expiry, uint256 pricePaid);
    event SubscriptionExtended(address indexed user, uint256 newExpiry);
    event PriceUpdated(uint256 newPrice);
    event Withdrawal(address indexed to, uint256 amount);

    /*//////////////////////////////////////////////////////////////
                                 STRUCTS
    //////////////////////////////////////////////////////////////*/
    struct Signal {
        bytes encryptedData;     // AES-encrypted signal payload
        bytes32 dataHash;        // keccak256(original plaintext) for integrity
        uint256 timestamp;       // block timestamp at submission
        address submitter;       // authorized backend address
    }

    struct Subscription {
        uint256 expiry;          // unix timestamp when subscription ends
        uint256 totalPaid;       // total MNT paid by this user
    }

    /*//////////////////////////////////////////////////////////////
                            STATE VARIABLES
    //////////////////////////////////////////////////////////////*/
    // symbol => timeframe => signal list
    mapping(string => mapping(string => Signal[])) public signals;

    // user => subscription info
    mapping(address => Subscription) public subscriptions;

    // authorized signal submitters (backend multi-sig or EOAs)
    mapping(address => bool) public authorizedSubmitters;

    // subscription price in wei (MNT has 18 decimals)
    uint256 public subscriptionPrice;

    // subscription duration in seconds (default 30 days)
    uint256 public subscriptionDuration;

    // contract owner
    address public owner;

    // valid timeframes
    mapping(string => bool) public validTimeframes;

    /*//////////////////////////////////////////////////////////////
                              MODIFIERS
    //////////////////////////////////////////////////////////////*/
    modifier onlyOwner() {
        require(msg.sender == owner, "Only owner");
        _;
    }

    modifier onlyAuthorized() {
        require(authorizedSubmitters[msg.sender], "Not authorized");
        _;
    }

    modifier onlySubscribed() {
        if (subscriptions[msg.sender].expiry < block.timestamp) {
            revert NotSubscribed(msg.sender);
        }
        _;
    }

    /*//////////////////////////////////////////////////////////////
                              CONSTRUCTOR
    //////////////////////////////////////////////////////////////*/
    constructor(
        uint256 _subscriptionPrice,
        uint256 _subscriptionDuration,
        address[] memory _initialSubmitters
    ) {
        owner = msg.sender;
        subscriptionPrice = _subscriptionPrice;
        subscriptionDuration = _subscriptionDuration;

        // initialize valid timeframes
        validTimeframes["1h"] = true;
        validTimeframes["4h"] = true;
        validTimeframes["1d"] = true;
        validTimeframes["1w"] = true;

        for (uint256 i = 0; i < _initialSubmitters.length; i++) {
            authorizedSubmitters[_initialSubmitters[i]] = true;
        }
    }

    /*//////////////////////////////////////////////////////////////
                           SUBSCRIPTION LOGIC
    //////////////////////////////////////////////////////////////*/
    /**
     * @notice Subscribe to signal access by sending MNT.
     *         Extends existing subscription if already active.
     */
    function subscribe() external payable {
        if (msg.value < subscriptionPrice) {
            revert InvalidPrice();
        }

        Subscription storage sub = subscriptions[msg.sender];

        uint256 newExpiry;
        if (sub.expiry > block.timestamp) {
            // extend existing subscription
            newExpiry = sub.expiry + subscriptionDuration;
        } else {
            newExpiry = block.timestamp + subscriptionDuration;
        }

        sub.expiry = newExpiry;
        sub.totalPaid += msg.value;

        emit Subscribed(msg.sender, newExpiry, msg.value);
    }

    /**
     * @notice Check if an address has an active subscription.
     */
    function isSubscribed(address user) external view returns (bool) {
        return subscriptions[user].expiry >= block.timestamp;
    }

    /**
     * @notice Get subscription details for a user.
     */
    function getSubscription(address user)
        external
        view
        returns (uint256 expiry, uint256 totalPaid, bool active)
    {
        Subscription storage sub = subscriptions[user];
        expiry = sub.expiry;
        totalPaid = sub.totalPaid;
        active = sub.expiry >= block.timestamp;
    }

    /*//////////////////////////////////////////////////////////////
                            SIGNAL SUBMISSION
    //////////////////////////////////////////////////////////////*/
    /**
     * @notice Submit an encrypted signal to the registry.
     * @param symbol      Trading pair symbol, e.g. "BTC"
     * @param timeframe   One of "1h", "4h", "1d", "1w"
     * @param encryptedData  AES-encrypted signal payload (bytes)
     * @param dataHash    keccak256 hash of original plaintext for integrity
     */
    function submitSignal(
        string calldata symbol,
        string calldata timeframe,
        bytes calldata encryptedData,
        bytes32 dataHash
    ) external onlyAuthorized {
        if (!validTimeframes[timeframe]) {
            revert InvalidTimeframe();
        }
        if (encryptedData.length == 0) {
            revert EmptyData();
        }

        Signal memory sig = Signal({
            encryptedData: encryptedData,
            dataHash: dataHash,
            timestamp: block.timestamp,
            submitter: msg.sender
        });

        signals[symbol][timeframe].push(sig);

        emit SignalSubmitted(
            symbol,
            timeframe,
            dataHash,
            block.timestamp,
            signals[symbol][timeframe].length - 1
        );
    }

    /**
     * @notice Batch submit multiple signals in one transaction.
     */
    function submitSignalsBatch(
        string[] calldata symbols,
        string[] calldata timeframes,
        bytes[] calldata encryptedDataArray,
        bytes32[] calldata dataHashes
    ) external onlyAuthorized {
        uint256 len = symbols.length;
        require(
            len == timeframes.length &&
            len == encryptedDataArray.length &&
            len == dataHashes.length,
            "Length mismatch"
        );

        for (uint256 i = 0; i < len; i++) {
            if (!validTimeframes[timeframes[i]]) continue;
            if (encryptedDataArray[i].length == 0) continue;

            Signal memory sig = Signal({
                encryptedData: encryptedDataArray[i],
                dataHash: dataHashes[i],
                timestamp: block.timestamp,
                submitter: msg.sender
            });

            signals[symbols[i]][timeframes[i]].push(sig);

            emit SignalSubmitted(
                symbols[i],
                timeframes[i],
                dataHashes[i],
                block.timestamp,
                signals[symbols[i]][timeframes[i]].length - 1
            );
        }
    }

    /*//////////////////////////////////////////////////////////////
                              SIGNAL READING
    //////////////////////////////////////////////////////////////*/
    /**
     * @notice Get the latest signal for a symbol/timeframe.
     *         Only active subscribers can call this.
     */
    function getLatestSignal(string calldata symbol, string calldata timeframe)
        external
        view
        onlySubscribed
        returns (Signal memory)
    {
        Signal[] storage sigs = signals[symbol][timeframe];
        require(sigs.length > 0, "No signals");
        return sigs[sigs.length - 1];
    }

    /**
     * @notice Get a specific signal by index.
     */
    function getSignal(
        string calldata symbol,
        string calldata timeframe,
        uint256 index
    ) external view onlySubscribed returns (Signal memory) {
        require(index < signals[symbol][timeframe].length, "Invalid index");
        return signals[symbol][timeframe][index];
    }

    /**
     * @notice Get all signals for a symbol/timeframe (paginated).
     */
    function getSignals(
        string calldata symbol,
        string calldata timeframe,
        uint256 offset,
        uint256 limit
    ) external view onlySubscribed returns (Signal[] memory) {
        Signal[] storage sigs = signals[symbol][timeframe];
        uint256 total = sigs.length;

        if (offset >= total) {
            return new Signal[](0);
        }

        uint256 end = offset + limit;
        if (end > total) {
            end = total;
        }

        Signal[] memory result = new Signal[](end - offset);
        for (uint256 i = offset; i < end; i++) {
            result[i - offset] = sigs[i];
        }
        return result;
    }

    /**
     * @notice Get total signal count for a symbol/timeframe.
     *         Public — no subscription required for count only.
     */
    function getSignalCount(string calldata symbol, string calldata timeframe)
        external
        view
        returns (uint256)
    {
        return signals[symbol][timeframe].length;
    }

    /*//////////////////////////////////////////////////////////////
                            ADMIN FUNCTIONS
    //////////////////////////////////////////////////////////////*/
    function addAuthorizedSubmitter(address submitter) external onlyOwner {
        authorizedSubmitters[submitter] = true;
    }

    function removeAuthorizedSubmitter(address submitter) external onlyOwner {
        authorizedSubmitters[submitter] = false;
    }

    function updateSubscriptionPrice(uint256 newPrice) external onlyOwner {
        subscriptionPrice = newPrice;
        emit PriceUpdated(newPrice);
    }

    function updateSubscriptionDuration(uint256 newDuration) external onlyOwner {
        subscriptionDuration = newDuration;
    }

    function addTimeframe(string calldata timeframe) external onlyOwner {
        validTimeframes[timeframe] = true;
    }

    function removeTimeframe(string calldata timeframe) external onlyOwner {
        validTimeframes[timeframe] = false;
    }

    /**
     * @notice Withdraw accumulated MNT subscription fees.
     */
    function withdraw(address payable to) external onlyOwner {
        uint256 balance = address(this).balance;
        require(balance > 0, "No balance");
        (bool success, ) = to.call{value: balance}("");
        require(success, "Transfer failed");
        emit Withdrawal(to, balance);
    }

    /**
     * @notice Transfer ownership.
     */
    function transferOwnership(address newOwner) external onlyOwner {
        require(newOwner != address(0), "Zero address");
        owner = newOwner;
    }

    /*//////////////////////////////////////////////////////////////
                               FALLBACK
    //////////////////////////////////////////////////////////////*/
    receive() external payable {
        // allow direct MNT transfers (treat as subscription if sufficient)
        if (msg.value >= subscriptionPrice) {
            Subscription storage sub = subscriptions[msg.sender];
            uint256 newExpiry = sub.expiry > block.timestamp
                ? sub.expiry + subscriptionDuration
                : block.timestamp + subscriptionDuration;
            sub.expiry = newExpiry;
            sub.totalPaid += msg.value;
            emit Subscribed(msg.sender, newExpiry, msg.value);
        }
    }
}
