# Mantle DeFAI Trader — 前后端架构与业务逻辑分析

> 生成时间: 2026-06-08

---

## 一、项目概览

本项目是一个面向 **Mantle 生态的 DeFAI（DeFi + AI）交易 Agent 平台**，包含：

| 模块 | 技术栈 | 路径 | 状态 |
|------|--------|------|------|
| **新版前端** | React 19 + TypeScript + Vite + Wagmi | `apps/web-react/` | ✅ 活跃开发 |
| **旧版前端** | 原生 JS + ethers.js v5 | `apps/web/` | 📦 归档 |
| **后端 API** | FastAPI + Web3.py + SQLite | `apps/api/` | ✅ 活跃 |
| **智能合约** | Foundry + Solidity ^0.8.19 | `contracts/` | ✅ 已部署 Sepolia |

部署链：**Mantle Sepolia Testnet** (Chain ID: 5003)
合约地址：`0x684802d365d1bbc0b74f7b57f823acdf965d1ba3`

---

## 二、系统整体架构

```mermaid
flowchart TB
    subgraph 用户层["👤 用户层"]
        User["用户浏览器"]
    end

    subgraph 前端层["🖥️ 前端层 (React 19 + Wagmi)"]
        WebReact["apps/web-react/"]
        Pages["Dashboard | Sentiment | Swap<br/>SmartRouting | OnChain | OnChainSignals"]
        Hooks["useWallet | useRegistry<br/>useSignalVerify | useSignalDecrypt"]
        Wagmi["Wagmi/Viem<br/>Mantle Mainnet + Sepolia"]
    end

    subgraph 后端层["⚙️ 后端层 (FastAPI + Web3.py)"]
        API["apps/api/ — FastAPI"]
        Routes["/api/sentiment/*<br/>/api/onchain/*<br/>/api/swap/*<br/>/api/routing/wizard/*"]
        Modules["SentimentAnalyzer | Backtest<br/>ElliottWave | TrendScheduler<br/>WhaleMonitor | DEXQuote"]
        RegistryClient["RegistryClient<br/>(EOA私钥签名)"]
    end

    subgraph 数据层["💾 数据层"]
        SQLite[("SQLite<br/>cache.db")]
        MemCache["内存缓存<br/>TTL 300s"]
    end

    subgraph 合约层["⛓️ 合约层 (Mantle Sepolia)"]
        Contract["MantleDeFAIRegistry<br/>0x6848...1ba3"]
        SwapRouter["Swap Router<br/>0x013e...21E3a"]
    end

    subgraph 外部服务["🌐 外部数据源"]
        Binance["Binance API<br/>K线/行情"]
        DefiLlama["DeFiLlama API<br/>协议TVL"]
        MantleRPC["Mantle RPC<br/>区块/Gas/余额"]
        Moralis["Moralis API<br/>多链转账"]
        Kimi["Kimi AI<br/>趋势分析/图表审核"]
    end

    User --> WebReact
    WebReact --> Pages
    Pages --> Hooks
    Hooks --> Wagmi
    Wagmi -->|"读取 getLatestSignal"| Contract
    Wagmi -->|"执行 Swap"| SwapRouter
    Wagmi -->|"订阅 10 MNT"| Contract
    
    Pages -->|"REST API"| API
    API --> Routes
    Routes --> Modules
    Modules --> SQLite
    Modules --> MemCache
    
    Modules -->|"获取K线"| Binance
    Modules -->|"获取协议TVL"| DefiLlama
    Modules -->|"获取链上数据"| MantleRPC
    Modules -->|"获取转账数据"| Moralis
    Modules -->|"AI分析"| Kimi
    
    RegistryClient -->|"submitSignalsBatch<br/>(每小时)"| Contract
    RegistryClient --> MantleRPC
```

---

## 三、后端数据上链逻辑（核心流程）

### 3.1 上链流程全景

```mermaid
flowchart TB
    Start(["每15分钟触发<br/>Unified Refresh"]) --> Counter{"计数器 % 4 == 0?"}
    Counter -->|"否"| Wait(["等待下个周期"])
    Counter -->|"是 (约每小时)"| Collect

    subgraph 数据采集["📥 数据采集"]
        Collect["采集多源数据"]
        BinanceData["Binance K线<br/>Top50币种行情"]
        DefiData["DeFiLlama<br/>协议TVL/链TVL"]
        MantleData["Mantle RPC<br/>区块/Gas/网络状态"]
    end

    subgraph AI分析["🧠 AI 分析"]
        Sentiment["SentimentAnalyzer<br/>情绪指数/多空方向/FNG"]
        Elliott["ElliottWave<br/>波浪检测+图表生成"]
        Backtest["Backtest引擎<br/>相似状态匹配回测"]
        Trend["TrendScheduler<br/>分级AI趋势分析"]
    end

    subgraph 信号组装["📦 信号组装 (v2.1 Payload)"]
        Assemble["组装信号JSON"]
        Decision["decision<br/>方向/置信度/理由"]
        Wave["elliott_wave<br/>波浪结构/预测"]
        Bt["backtest<br/>胜率/盈亏比"]
        Sent["sentiment<br/>情绪指数/市场偏向"]
        Pos["position_report<br/>多空观察列表"]
        Onchain["onchain_context<br/>TVL/Gas/区块"]
        Dash["dashboard<br/>top_bullish/top_bearish"]
    end

    subgraph 上链提交["⛓️ 上链提交"]
        Filter{"confidence ∈<br/>{high, medium}?"}
        Hash["crypto_utils.hash_signal()<br/>keccak256(plaintext)"]
        BuildTx["RegistryClient<br/>构建交易"]
        Nonce["获取 nonce"]
        Gas["估算 gas * 1.2"]
        Sign["EOA私钥签名<br/>account.sign_transaction"]
        Broadcast["广播交易<br/>w3.eth.send_raw_transaction"]
        Confirm["合约存储<br/>Signal {data, dataHash, timestamp, submitter}"]
    end

    Collect --> BinanceData & DefiData & MantleData
    BinanceData & DefiData & MantleData --> Sentiment & Elliott & Backtest & Trend
    Sentiment & Elliott & Backtest & Trend --> Assemble
    Assemble --> Decision & Wave & Bt & Sent & Pos & Onchain & Dash
    Assemble --> Filter
    Filter -->|"通过"| Hash
    Filter -->|"丢弃"| Discard["❌ 丢弃低置信度信号"]
    Hash --> BuildTx
    BuildTx --> Nonce --> Gas --> Sign --> Broadcast --> Confirm
```

### 3.2 交易构建与签名细节

```mermaid
sequenceDiagram
    participant B as Background Scheduler
    participant R as RegistryClient
    participant W as Web3.py
    participant M as Mantle Sepolia RPC
    participant C as MantleDeFAIRegistry

    B->>R: submit_signals_batch(signals)
    R->>W: get_transaction_count(address)
    W->>M: eth_getTransactionCount
    M-->>W: nonce
    W-->>R: nonce
    
    R->>W: gas_price
    W->>M: eth_gasPrice
    M-->>W: gasPrice
    W-->>R: gasPrice
    
    R->>W: build_transaction({from, nonce, gasPrice, chainId})
    W->>R: unsigned_tx
    
    R->>W: estimate_gas(tx)
    W->>M: eth_estimateGas
    M-->>W: estimated_gas
    W-->>R: gas = estimated_gas * 1.2
    
    alt estimate_gas 失败
        R->>R: gas = 500,000 (fallback)
    end
    
    R->>W: sign_transaction(tx, private_key)
    W-->>R: signed_tx
    
    R->>W: send_raw_transaction(signed_tx)
    W->>M: eth_sendRawTransaction
    M->>C: 执行 submitSignalsBatch()
    C-->>M: tx_hash
    M-->>W: tx_hash
    W-->>R: tx_hash
    R-->>B: 返回 tx_hash
```

### 3.3 信号数据结构（v2.1）

```mermaid
classDiagram
    class Signal {
        +string data        // Plaintext JSON
        +bytes32 dataHash   // keccak256(data)
        +uint256 timestamp  // block.timestamp
        +address submitter  // 授权后端地址
    }
    
    class SignalPayload {
        +string version = "2.1"
        +string timestamp
        +string agent_id = "mantle-defai-agent-v2.1"
        +Decision decision
        +ElliottWave elliott_wave
        +Backtest backtest
        +Sentiment sentiment
        +PositionReport position_report
        +OnChainContext onchain_context
        +Dashboard dashboard
        +Trends trends
        +SymbolScores symbol_scores
        +Protocols[] protocols
        +Overview overview
        +BlockData block
        +GasData gas
        +NetworkData network
        +string risk_warning
    }
    
    Signal --> SignalPayload : data字段JSON解析
```

---

## 四、后端核心业务逻辑

### 4.1 后台调度器架构

```mermaid
flowchart LR
    subgraph FastAPI["FastAPI Lifespan"]
        Startup["应用启动"]
    end

    subgraph Schedulers["🕐 后台调度器"]
        U["Unified Refresh<br/>每15分钟"]
        O["OnChain Collector<br/>每15分钟"]
        A["Aggregator<br/>每15分钟"]
        T["Trend Scheduler<br/>每小时"]
        E["Elliott Wave<br/>每小时"]
    end

    subgraph Tasks["📋 执行任务"]
        U1["刷新全部数据"]
        U2["信号上链<br/>(每小时触发)"]
        O1["采集区块/Gas/协议"]
        A1["聚合多源数据"]
        T1["AI小时级分析"]
        T2["半日汇总<br/>每12小时"]
        T3["大周期汇总<br/>每3天"]
        E1["波浪检测+图表"]
    end

    subgraph Storage["💾 存储"]
        DB[("SQLite<br/>cache.db")]
        Cache["内存缓存"]
    end

    Startup --> U & O & A & T & E
    U --> U1 --> U2
    O --> O1
    A --> A1
    T --> T1 --> T2 --> T3
    E --> E1
    U1 & O1 & A1 & T1 & T2 & T3 & E1 --> DB
    U1 & O1 & A1 --> Cache
```

### 4.2 情绪分析流程

```mermaid
flowchart TB
    Request["POST /api/sentiment/analyze<br/>或 调度器定时触发"] --> FetchKlines["获取 Binance K线<br/>多时间周期"]
    FetchKlines --> CalcMetrics["计算技术指标"]
    
    subgraph 指标计算["📊 指标计算"]
        MA["MA 移动平均线"]
        RSI["RSI 相对强弱"]
        MACD["MACD 趋势"]
        Volume["成交量分析"]
    end
    
    CalcMetrics --> MA & RSI & MACD & Volume
    MA & RSI & MACD & Volume --> SentimentScore["综合情绪评分<br/>0-100"]
    SentimentScore --> MarketBias["市场偏向<br/>bullish/bearish/neutral"]
    MarketBias --> FNG["恐惧贪婪指数 FNG"]
    FNG --> SignalGen["生成交易信号<br/>direction + confidence + reason"]
    
    SignalGen --> CacheResult["写入内存缓存<br/>+ SQLite缓存"]
    SignalGen --> Return["返回 sentiment 数据"]
```

### 4.3 回测引擎流程

```mermaid
flowchart TB
    Request["GET /api/sentiment/backtest/{symbol}/{timeframe}"] --> Whitelist{"IP白名单检查"}
    Whitelist -->|"拒绝"| 403["返回 403"]
    Whitelist -->|"通过"| FetchData["获取历史K线<br/>+ 当前 sentiment"]
    
    FetchData --> MatchState["相似状态匹配<br/>MA对齐滑动窗口"]
    MatchState --> HoldPeriod["设定持有期<br/>10根K线"]
    HoldPeriod --> Simulate["模拟交易执行"]
    
    subgraph 回测计算["🔄 回测计算"]
        PnL["计算每笔盈亏 PnL"]
        WinRate["统计胜率<br/>盈利笔数/总笔数"]
        ProfitFactor["盈亏比<br/>总盈利/总亏损"]
        Duration["持续时长分布"]
    end
    
    Simulate --> PnL & WinRate & ProfitFactor & Duration
    PnL & WinRate & ProfitFactor & Duration --> Summary["生成回测报告"]
    Summary --> ReturnResult["返回回测结果"]
```

### 4.4 智能路由向导流程（8步状态机）

```mermaid
flowchart LR
    Start(["POST /wizard/start"]) --> S1["Step 1<br/>选择源链"]
    S1 --> S2["Step 2<br/>选择目标链"]
    S2 --> S3["Step 3<br/>选择源代币"]
    S3 --> S4["Step 4<br/>选择目标代币"]
    S4 --> S5["Step 5<br/>输入金额"]
    S5 --> S6["Step 6<br/>AI分析路由"]
    S6 --> S7["Step 7<br/>选择路由方案"]
    S7 --> S8["Step 8<br/>钱包检查+执行"]
    S8 --> End(["交易完成"])
    
    S6 -.->|"/analyze"| AI["AI分析多链/多DEX<br/>最优路由"]
    S8 -.->|"/wallet-check"| Check["余额检查<br/>授权检查"]
    S8 -.->|"/execute"| Execute["构建并广播<br/>跨链交易"]
```

---

## 五、前端交互流程

### 5.1 页面路由与数据来源

```mermaid
flowchart TB
    subgraph 前端页面["🖥️ 前端页面"]
        Dashboard["/ — Dashboard<br/>市场情绪仪表盘"]
        SentimentPage["/sentiment<br/>情绪分析+回测"]
        SwapPage["/swap<br/>代币兑换"]
        RoutingPage["/routing<br/>智能路由向导"]
        OnChainPage["/onchain<br/>链上数据深度"]
        SignalsPage["/onchain-signals<br/>链上信号浏览器"]
    end

    subgraph API数据["📡 REST API 数据"]
        API1["/api/sentiment/latest"]
        API2["/api/sentiment/backtest/*"]
        API3["/api/swap/quote"]
        API4["/api/routing/wizard/*"]
        API5["/api/onchain/*"]
        API6["/api/mantle/*"]
    end

    subgraph 链上数据["⛓️ 链上直接读取"]
        Chain1["getLatestSignal<br/>(Mantle Sepolia)"]
        Chain2["Swap Router<br/>(Mantle Mainnet)"]
        Chain3["Registry.subscribe<br/>(Mantle Sepolia)"]
    end

    Dashboard --> API1 & API5 & API6
    Dashboard --> Chain1
    SentimentPage --> API1 & API2
    SwapPage --> API3 --> Chain2
    RoutingPage --> API4
    OnChainPage --> API5 & API6
    SignalsPage --> Chain1
```

### 5.2 Swap 交易执行流程

```mermaid
sequenceDiagram
    participant U as 用户
    participant F as Swap页面
    participant API as /api/swap/quote
    participant Wallet as useWallet Hook
    participant MetaMask as MetaMask
    participant Router as Swap Router合约

    U->>F: 选择代币对 + 输入金额
    F->>API: POST /api/swap/quote
    API-->>F: 返回 quote (price, slippage, route)
    F->>U: 显示报价
    U->>F: 确认 Swap
    F->>Wallet: executeSwap(tokenIn, tokenOut, amount)
    Wallet->>MetaMask: 请求交易签名
    MetaMask->>U: 弹出确认窗口
    U->>MetaMask: 确认
    MetaMask->>Router: sendTransaction(swapExactTokensForTokens)
    Router-->>MetaMask: 交易收据
    MetaMask-->>Wallet: tx_hash
    Wallet-->>F: 交易完成
    F->>U: 显示成功 + tx_hash
```

### 5.3 链上信号读取与验证流程

```mermaid
flowchart TB
    User["用户访问<br/>OnChain Signals页面"] --> Select["选择币种 + 时间周期"]
    Select --> ReadChain["useReadContract<br/>getLatestSignal(symbol, timeframe)"]
    ReadChain --> SignalData["获取 Signal 数据<br/>{data, dataHash, timestamp, submitter}"]
    
    SignalData --> Verify["useSignalVerify<br/>本地验证"]
    subgraph 验证逻辑["✅ 三项验证"]
        V1["提交者校验<br/>submitter == 预期地址"]
        V2["Hash 校验<br/>keccak256(data) == dataHash"]
        V3["时效性校验<br/>当前时间 - timestamp < 24h"]
    end
    Verify --> V1 & V2 & V3
    
    V1 & V2 & V3 --> AllPass{"全部通过?"}
    AllPass -->|"是"| Decrypt["useSignalDecrypt<br/>解析 JSON 数据"]
    AllPass -->|"否"| Warning["⚠️ 显示验证警告"]
    
    Decrypt --> Display["展示结构化信号"]
    subgraph 信号内容["📋 信号内容展示"]
        D1["决策: direction/confidence"]
        D2["艾略特波浪: wave_pattern"]
        D3["回测: win_rate/avg_pnl"]
        D4["情绪: sentiment_index"]
        D5["持仓报告: long/short/watch"]
        D6["链上上下文: TVL/Gas"]
    end
    Display --> D1 & D2 & D3 & D4 & D5 & D6
```

---

## 六、关键文件索引

### 前端
| 文件 | 职责 |
|------|------|
| `apps/web-react/src/App.tsx` | 路由定义 |
| `apps/web-react/src/services/api.ts` | API 客户端 (axios) |
| `apps/web-react/src/hooks/useWallet.ts` | 钱包连接 + Swap 执行 |
| `apps/web-react/src/hooks/useRegistry.ts` | 合约读写（订阅/查询） |
| `apps/web-react/src/hooks/useSignalVerify.ts` | 信号本地验证 |
| `apps/web-react/src/hooks/useSignalDecrypt.ts` | 信号 JSON 解析 |
| `apps/web-react/src/pages/Dashboard.tsx` | 主仪表盘 |
| `apps/web-react/src/pages/Sentiment.tsx` | 情绪分析 + 回测 |
| `apps/web-react/src/pages/OnChainSignals.tsx` | 链上信号浏览器 |

### 后端
| 文件 | 职责 |
|------|------|
| `apps/api/main.py` | FastAPI 入口 + 启动后台任务 |
| `apps/api/routes.py` | 主 APIRouter（所有 /api/*） |
| `apps/api/routing_wizard.py` | 智能路由向导 |
| `apps/api/contract_client.py` | RegistryClient（上链交易） |
| `apps/api/background.py` | 后台刷新 + 信号上链 |
| `apps/api/clients.py` | Binance/Mantle/DEX 客户端 |
| `apps/api/backtest.py` | 回测引擎 |
| `apps/api/elliott_wave.py` | 艾略特波浪检测 |
| `apps/api/kimi_analyzer.py` | Kimi AI 趋势分析 |
| `apps/api/onchain_collector.py` | 链上数据收集 |
| `apps/api/crypto_utils.py` | keccak256 哈希工具 |

### 合约
| 文件 | 职责 |
|------|------|
| `contracts/src/MantleDeFAIRegistry.sol` | 核心信号注册表合约 |
| `contracts/script/DeployRegistry.s.sol` | 部署脚本 |

---

## 七、安全与访问控制

| 机制 | 实现 | 位置 |
|------|------|------|
| IP 白名单 | `IP_WHITELIST` 环境变量 | `apps/api/core.py` |
| 限流 | 100 请求/60秒 | `apps/api/core.py` |
| 回测保护 | `require_whitelist()` 装饰器 | `apps/api/routes.py` |
| DEBUG 模式 | 跳过白名单检查 | `apps/api/core.py` |
| 信号验证 | keccak256 + 授权提交者 + 时效 | 合约 + 前端 |
| EOA 私钥 | 环境变量 `REGISTRY_PRIVATE_KEY` | `apps/api/contract_client.py` |
