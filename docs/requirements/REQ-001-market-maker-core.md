# REQ-001: Market Maker Core System

**Version:** 1.1
**Status:** Draft
**Created:** 2026-01-17
**Last Updated:** 2026-01-17

---

## 1. Overview

### 1.1 Purpose

Build an automated market-making system for Kalshi prediction markets, initially targeting crypto hourly markets. The system will provide liquidity by maintaining bid/ask quotes, manage inventory risk through dynamic quote skewing, and protect capital through multiple layers of risk controls.

### 1.2 Scope

**In Scope:**
- Exchange abstraction layer supporting multiple exchanges
- Kalshi exchange integration (REST API + WebSocket) - initial implementation
- Avellaneda-Stoikov style market-making strategy
- Paper trading mode with simulated fills against live data
- Live trading mode with real order execution
- Single market operation (crypto hourly) for initial release
- Local and AWS deployment

**Planned Extensions:**
- Polymarket integration (design for this from day one)
- Multi-market simultaneous operation
- Cross-exchange arbitrage opportunities

**Out of Scope (Future):**
- Web dashboard UI
- Machine learning signal generation

### 1.3 Target Market

- **Exchange:** Kalshi
- **Market Type:** Crypto hourly contracts (e.g., "Bitcoin > $X at end of hour")
- **Contract Structure:** Binary (settles $1 if YES, $0 if NO)
- **Price Range:** $0.01 - $0.99

### 1.4 Capital Requirements

| Phase | Capital | Purpose |
|-------|---------|---------|
| Integration Testing | $50-$100 | API validation, connectivity |
| Strategy Testing | $250-$750 | Real behavior validation |
| Performance Evaluation | $1,000-$2,500 | Profitability assessment |
| Production | $5,000+ | Operational market making |

---

## 2. Functional Requirements

### 2.1 Exchange Adapter (FR-100)

#### FR-101: WebSocket Connection
The system SHALL maintain a persistent WebSocket connection to Kalshi for real-time market data.

**Acceptance Criteria:**
- [ ] Connect to Kalshi WebSocket endpoint with authentication
- [ ] Receive order book updates (snapshots and deltas)
- [ ] Receive trade/fill notifications
- [ ] Automatic reconnection on disconnect with exponential backoff
- [ ] Connection health monitoring with heartbeat

#### FR-102: REST API Integration
The system SHALL integrate with Kalshi REST API for order operations and account queries.

**Acceptance Criteria:**
- [ ] Authenticate using API key credentials
- [ ] Place limit orders (YES and NO sides)
- [ ] Cancel orders by ID
- [ ] Query open orders
- [ ] Query account positions
- [ ] Query account balance
- [ ] Handle rate limiting (respect 10 writes/sec on Basic tier)

#### FR-103: Data Normalization
The system SHALL normalize Kalshi-specific data formats into internal domain models.

**Acceptance Criteria:**
- [ ] Convert Kalshi order book format to internal `OrderBook` model
- [ ] Convert Kalshi order responses to internal `Order` model
- [ ] Convert Kalshi fill events to internal `Fill` model
- [ ] Handle Kalshi-specific price representation (cents vs dollars)

### 2.1.1 Exchange Abstraction Layer (FR-110)

The system SHALL be designed with a clean abstraction layer to support multiple exchanges.

#### FR-110: Exchange Adapter Interface
The system SHALL define abstract interfaces that all exchange adapters must implement.

**Required Interfaces:**

```python
class ExchangeAdapter(ABC):
    """Abstract base for all exchange integrations."""

    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def disconnect(self) -> None: ...

    @abstractmethod
    async def subscribe_market(self, market_id: str) -> None: ...

    @abstractmethod
    async def unsubscribe_market(self, market_id: str) -> None: ...

    @abstractmethod
    async def place_order(self, order: OrderRequest) -> Order: ...

    @abstractmethod
    async def cancel_order(self, order_id: str) -> None: ...

    @abstractmethod
    async def get_positions(self) -> list[Position]: ...

    @abstractmethod
    async def get_balance(self) -> Balance: ...


class WebSocketClient(ABC):
    """Abstract base for WebSocket connections."""

    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def subscribe(self, channels: list[str]) -> None: ...

    @abstractmethod
    async def on_message(self, handler: Callable) -> None: ...

    @abstractmethod
    async def reconnect(self) -> None: ...
```

**Acceptance Criteria:**
- [ ] `ExchangeAdapter` ABC defined with all required methods
- [ ] `WebSocketClient` ABC defined with all required methods
- [ ] All exchange-specific code isolated in adapter implementations
- [ ] Core system components depend only on abstract interfaces
- [ ] Factory pattern for adapter instantiation based on configuration

#### FR-111: Exchange-Agnostic Domain Models
The system SHALL use domain models that are independent of any specific exchange.

**Core Models (exchange-agnostic):**

| Model | Purpose | Exchange-Specific Mapping |
|-------|---------|--------------------------|
| `Price` | Decimal price 0.01-0.99 | Kalshi: cents, Polymarket: USDC |
| `Quantity` | Contract count | Direct mapping |
| `Side` | YES / NO | Kalshi: yes/no, Polymarket: outcome tokens |
| `OrderSide` | BUY / SELL | Direct mapping |
| `Order` | Order state | Map from exchange order format |
| `Fill` | Execution event | Map from exchange fill format |
| `OrderBook` | Market depth | Normalize from exchange format |
| `Position` | Holdings | Aggregate from exchange positions |

**Acceptance Criteria:**
- [ ] Domain models contain no exchange-specific fields
- [ ] Each adapter implements bidirectional mapping (internal ↔ exchange)
- [ ] Models use Decimal for prices (not float)
- [ ] Models are immutable (frozen dataclasses or Pydantic with frozen=True)

#### FR-112: Exchange Configuration
The system SHALL support configuration-driven exchange selection.

**Configuration Structure:**
```yaml
exchanges:
  active: kalshi  # or polymarket

  kalshi:
    api_key_env: KALSHI_API_KEY
    api_secret_env: KALSHI_API_SECRET
    base_url: https://trading-api.kalshi.com
    ws_url: wss://trading-api.kalshi.com
    rate_limits:
      writes_per_second: 10
      reads_per_second: 20

  polymarket:  # Future
    api_key_env: POLYMARKET_API_KEY
    base_url: https://clob.polymarket.com
    ws_url: wss://ws-subscriptions-clob.polymarket.com
    chain_id: 137  # Polygon
```

**Acceptance Criteria:**
- [ ] Exchange selected via configuration, not code changes
- [ ] All exchange-specific settings isolated in config
- [ ] Credentials referenced by environment variable names
- [ ] Easy to add new exchange configuration blocks

#### FR-113: Exchange Feature Compatibility
The system SHALL handle differences in exchange capabilities gracefully.

**Feature Matrix:**

| Feature | Kalshi | Polymarket | Handling |
|---------|--------|------------|----------|
| Binary contracts | Yes | Yes | Core support |
| REST API | Yes | Yes | Required |
| WebSocket | Yes | Yes | Required |
| Order amendment | Yes | No | Adapter abstracts (cancel+replace) |
| Batch orders | Yes (20) | Yes (varies) | Adapter handles batching |
| Rate limits | 10-400/sec | Varies | Configurable per exchange |
| Authentication | API key + HMAC | API key + Polygon wallet | Adapter handles |
| Settlement | USD | USDC | Normalize to decimal |

**Acceptance Criteria:**
- [ ] Feature differences handled in adapter layer, not core
- [ ] Missing features emulated where possible (e.g., amend → cancel+create)
- [ ] Unsupported operations raise clear `NotSupportedError`
- [ ] Core system queries adapter for capabilities

#### FR-114: Mock Exchange Adapter
The system SHALL include a mock adapter for testing.

**Mock Adapter Capabilities:**
- Simulates order book with configurable depth
- Simulates fills based on configurable rules
- Simulates latency and errors
- Supports deterministic replay for unit tests
- Supports randomized behavior for integration tests

**Acceptance Criteria:**
- [ ] `MockExchangeAdapter` implements full `ExchangeAdapter` interface
- [ ] Configurable fill behavior (immediate, delayed, partial, reject)
- [ ] Configurable error injection (network, rate limit, invalid order)
- [ ] State inspection for test assertions
- [ ] Used in all unit tests (no real exchange calls)

### 2.2 Market Data Handler (FR-200)

#### FR-201: Order Book State
The system SHALL maintain an accurate, real-time view of the order book for subscribed markets.

**Acceptance Criteria:**
- [ ] Process order book snapshots
- [ ] Apply incremental deltas correctly
- [ ] Calculate best bid/ask prices and sizes
- [ ] Calculate mid-price
- [ ] Calculate spread
- [ ] Timestamp all updates

#### FR-202: Market Snapshot
The system SHALL provide market snapshots to the strategy engine on demand.

**Acceptance Criteria:**
- [ ] `MarketSnapshot` includes: market_id, mid_price, spread, best_bid, best_ask, timestamp
- [ ] Snapshots reflect the most recent order book state
- [ ] Stale data detection (alert if no updates for configurable period)

### 2.3 Volatility Estimator (FR-300)

#### FR-301: EWMA Volatility
The system SHALL calculate real-time volatility using exponentially weighted moving average of price changes.

**Formula:**
```
σ_t = sqrt(α * (mid_t - mid_{t-1})² + (1-α) * σ²_{t-1})
```

**Acceptance Criteria:**
- [ ] Configurable decay factor (α), default 0.94
- [ ] Update on each mid-price change
- [ ] Provide current volatility estimate to strategy engine
- [ ] Handle initialization period gracefully

### 2.4 Strategy Engine (FR-400)

#### FR-401: Reservation Price Calculation
The system SHALL calculate a reservation price using the Avellaneda-Stoikov model.

**Formula:**
```
r = s - q / (γ * σ² * T)
```

Where:
- `s` = current mid-price
- `q` = current inventory (positive = long YES, negative = short YES)
- `γ` = risk aversion parameter (configurable)
- `σ` = current volatility estimate
- `T` = time remaining until settlement

**Acceptance Criteria:**
- [ ] Reservation price shifts DOWN when long (encourages selling)
- [ ] Reservation price shifts UP when short (encourages buying)
- [ ] Effect increases as time-to-settlement decreases
- [ ] Effect increases with higher volatility

#### FR-402: Quote Generation
The system SHALL generate bid/ask quotes for both YES and NO contracts around the reservation price.

**Two-Sided Quoting:**
The system quotes both YES and NO sides simultaneously to capture flow from traders who prefer either contract type. This produces 4 active quotes per market.

**YES Quote Formulas:**
```
YES_bid = r - δ - skew
YES_ask = r + δ - skew
```

**NO Quote Formulas (derived from YES to maintain $1 consistency):**
```
NO_bid = 1 - YES_ask
NO_ask = 1 - YES_bid
```

Where:
- `r` = reservation price (from FR-401)
- `δ` = half-spread (base spread / 2)
- `skew` = inventory-based adjustment: `k * (q / Q_max)`
- `q` = net inventory (YES - NO), positive = long YES
- `Q_max` = maximum inventory limit
- `k` = skew intensity parameter

**Quote Sheet Example (mid = $0.50, inventory = +300):**
```
        BID       ASK
YES    $0.481    $0.501
NO     $0.499    $0.519
```

**Inventory Impact on All Four Quotes:**
| Inventory State | Skew Effect | YES Quotes | NO Quotes | Net Effect |
|-----------------|-------------|------------|-----------|------------|
| Long YES (q > 0) | Positive skew | Shift down | Shift up | Encourages selling YES / buying NO |
| Short YES (q < 0) | Negative skew | Shift up | Shift down | Encourages buying YES / selling NO |
| Neutral (q = 0) | No skew | Centered | Centered | Symmetric around mid |

**Acceptance Criteria:**
- [ ] Generate 4 quotes per market: YES bid, YES ask, NO bid, NO ask
- [ ] NO quotes derived from YES quotes using $1 complement
- [ ] Configurable base spread
- [ ] Configurable skew intensity (k)
- [ ] All quotes respect price bounds ($0.01 - $0.99)
- [ ] All quotes maintain minimum tick size ($0.01)
- [ ] YES_ask + NO_bid ≈ $1.00 (within spread)
- [ ] YES_bid + NO_ask ≈ $1.00 (within spread)

#### FR-403: Quote Sizing
The system SHALL determine appropriate quote sizes based on inventory and risk limits using asymmetric sizing.

**Asymmetric Sizing Formula:**
Quote sizes adjust based on inventory to discourage increasing exposure and encourage reducing it.

```
bid_size = base_size * max(0, 1 - q / Q_max)
ask_size = base_size * max(0, 1 + q / Q_max)
```

Where:
- `base_size` = base quote size (default: 100 contracts)
- `q` = net inventory (YES - NO), positive = long YES
- `Q_max` = maximum inventory limit (default: 1,000 contracts)

**Sizing Behavior:**
| Inventory State | Bid Size | Ask Size | Effect |
|-----------------|----------|----------|--------|
| Neutral (q = 0) | 100% | 100% | Symmetric |
| Long +500 | 50% | 150% | Discourages buying, encourages selling |
| Long +1000 | 0% | 200% | Stops buying, max selling |
| Short -500 | 150% | 50% | Encourages buying, discourages selling |
| Short -1000 | 200% | 0% | Max buying, stops selling |

**Example (base_size=100, Q_max=1000, inventory=+300):**
```
bid_size = 100 * max(0, 1 - 300/1000) = 100 * 0.7 = 70 contracts
ask_size = 100 * max(0, 1 + 300/1000) = 100 * 1.3 = 130 contracts
```

**Applying to YES/NO Quotes:**
Since NO trades have inverse inventory impact, sizes are swapped:
```
YES_bid_size = bid_size    (buying YES increases q)
YES_ask_size = ask_size    (selling YES decreases q)
NO_bid_size  = ask_size    (buying NO decreases q)
NO_ask_size  = bid_size    (selling NO increases q)
```

**Acceptance Criteria:**
- [ ] Configurable base quote size
- [ ] Bid size reduces as inventory becomes more positive (long)
- [ ] Ask size reduces as inventory becomes more negative (short)
- [ ] Size can exceed base_size to encourage rebalancing (up to 2x)
- [ ] Size floors at 0 when at max inventory on that side
- [ ] Respect maximum position limits
- [ ] NO quote sizes inverted relative to YES (same rebalancing intent)

#### FR-404: Strategy Parameters
The system SHALL support configurable strategy parameters.

| Parameter | Description | Default |
|-----------|-------------|---------|
| `gamma` | Risk aversion (higher = more conservative) | 0.1 |
| `base_spread` | Minimum spread width | 0.02 |
| `skew_intensity` | Inventory skew multiplier | 0.01 |
| `quote_size` | Base contracts per quote | 100 |
| `max_inventory` | Maximum net position | 1000 |

### 2.4.1 Pluggable Strategy Components (FR-410)

The strategy engine SHALL be composed of pluggable components that can be swapped independently via configuration.

#### FR-410: Component Architecture
The system SHALL use a composition-based strategy architecture where each calculation step is a separate pluggable component.

**Architecture:**
```
┌─────────────────────────────────────────────────────────────────────┐
│                         StrategyEngine                               │
│                                                                      │
│   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐              │
│   │ Volatility  │   │ Reservation │   │    Skew     │              │
│   │ Estimator   │──►│   Price     │──►│ Calculator  │              │
│   │   (ABC)     │   │   (ABC)     │   │   (ABC)     │              │
│   └─────────────┘   └─────────────┘   └─────────────┘              │
│                            │                 │                       │
│                            ▼                 ▼                       │
│                     ┌─────────────┐   ┌─────────────┐              │
│                     │   Spread    │   │    Quote    │              │
│                     │ Calculator  │   │    Sizer    │              │
│                     │   (ABC)     │   │   (ABC)     │              │
│                     └─────────────┘   └─────────────┘              │
│                            │                 │                       │
│                            └────────┬────────┘                       │
│                                     ▼                                │
│                              ┌─────────────┐                        │
│                              │  QuoteSet   │                        │
│                              └─────────────┘                        │
└─────────────────────────────────────────────────────────────────────┘
```

**Component Flow:**
1. `VolatilityEstimator` → produces `σ` (volatility)
2. `ReservationPriceCalculator` → produces `r` (fair value adjusted for inventory)
3. `SpreadCalculator` → produces `δ` (half-spread)
4. `SkewCalculator` → produces `skew` (inventory adjustment)
5. `QuoteSizer` → produces `bid_size`, `ask_size`
6. `StrategyEngine` combines outputs → `QuoteSet`

**Acceptance Criteria:**
- [ ] Each component defined as an abstract base class (ABC)
- [ ] Components receive only the inputs they need (dependency injection)
- [ ] Components are stateless where possible (easier testing)
- [ ] Component selection via configuration, not code changes
- [ ] Default implementations provided for each component
- [ ] Components can be mixed and matched freely

#### FR-411: Volatility Estimator Interface
The system SHALL define a pluggable interface for volatility estimation.

**Interface:**
```python
class VolatilityEstimator(ABC):
    """Estimates current market volatility."""

    @abstractmethod
    def update(self, mid_price: Decimal, timestamp: datetime) -> None:
        """Process a new mid-price observation."""
        ...

    @abstractmethod
    def get_volatility(self) -> Decimal:
        """Return current volatility estimate."""
        ...

    @abstractmethod
    def is_ready(self) -> bool:
        """Return True if enough data for valid estimate."""
        ...
```

**Provided Implementations:**

| Implementation | Description | Use Case |
|----------------|-------------|----------|
| `EWMAVolatility` | Exponentially weighted moving average (FR-301) | Default, simple |
| `RealizedVolatility` | Rolling window of squared returns | More stable |
| `FixedVolatility` | Constant value from config | Testing, backtesting |

**Configuration:**
```yaml
strategy:
  components:
    volatility:
      type: ewma           # ewma, realized, fixed
      params:
        alpha: 0.94        # EWMA decay factor
```

**Acceptance Criteria:**
- [ ] `VolatilityEstimator` ABC defined
- [ ] `EWMAVolatility` implements FR-301 formula
- [ ] `RealizedVolatility` uses configurable window size
- [ ] `FixedVolatility` for deterministic testing
- [ ] Graceful handling of initialization period

#### FR-412: Reservation Price Calculator Interface
The system SHALL define a pluggable interface for reservation price calculation.

**Interface:**
```python
class ReservationPriceCalculator(ABC):
    """Calculates inventory-adjusted fair value."""

    @abstractmethod
    def calculate(
        self,
        mid_price: Decimal,
        inventory: int,
        volatility: Decimal,
        time_to_settlement: float,
    ) -> Decimal:
        """Return reservation price."""
        ...
```

**Provided Implementations:**

| Implementation | Formula | Use Case |
|----------------|---------|----------|
| `AvellanedaStoikov` | `r = s - q / (γ * σ² * T)` | Default, inventory-sensitive |
| `SimpleMidPrice` | `r = s` (ignore inventory) | Baseline comparison |
| `LinearAdjustment` | `r = s - k * q` | Simpler inventory adjustment |

**Configuration:**
```yaml
strategy:
  components:
    reservation_price:
      type: avellaneda_stoikov    # avellaneda_stoikov, simple_mid, linear
      params:
        gamma: 0.1                 # Risk aversion
```

**Acceptance Criteria:**
- [ ] `ReservationPriceCalculator` ABC defined
- [ ] `AvellanedaStoikov` implements FR-401 formula
- [ ] `SimpleMidPrice` returns mid without adjustment
- [ ] `LinearAdjustment` for simpler inventory sensitivity
- [ ] All implementations handle edge cases (T→0, σ→0)

#### FR-413: Skew Calculator Interface
The system SHALL define a pluggable interface for inventory skew calculation.

**Interface:**
```python
class SkewCalculator(ABC):
    """Calculates quote skew based on inventory."""

    @abstractmethod
    def calculate(
        self,
        inventory: int,
        max_inventory: int,
        volatility: Decimal,
    ) -> Decimal:
        """Return skew adjustment (positive = shift quotes down)."""
        ...
```

**Provided Implementations:**

| Implementation | Formula | Behavior |
|----------------|---------|----------|
| `LinearSkew` | `skew = k * (q / Q_max)` | Default, proportional to inventory |
| `ExponentialSkew` | `skew = k * sign(q) * (q/Q_max)²` | Aggressive near limits |
| `AdaptiveSkew` | `skew = k * (q / Q_max) * σ` | Scales with volatility |
| `NoSkew` | `skew = 0` | Baseline comparison |

**Configuration:**
```yaml
strategy:
  components:
    skew:
      type: linear           # linear, exponential, adaptive, none
      params:
        intensity: 0.01      # k parameter
```

**Acceptance Criteria:**
- [ ] `SkewCalculator` ABC defined
- [ ] `LinearSkew` implements FR-402 formula
- [ ] `ExponentialSkew` for more aggressive inventory management
- [ ] `AdaptiveSkew` adjusts to market conditions
- [ ] `NoSkew` for A/B testing skew impact

#### FR-414: Spread Calculator Interface
The system SHALL define a pluggable interface for spread calculation.

**Interface:**
```python
class SpreadCalculator(ABC):
    """Calculates bid-ask spread."""

    @abstractmethod
    def calculate(
        self,
        volatility: Decimal,
        inventory: int,
        max_inventory: int,
        time_to_settlement: float,
    ) -> Decimal:
        """Return half-spread (δ)."""
        ...
```

**Provided Implementations:**

| Implementation | Formula | Behavior |
|----------------|---------|----------|
| `FixedSpread` | `δ = base_spread / 2` | Default, constant spread |
| `VolatilitySpread` | `δ = base + vol_multiplier * σ` | Widens in volatile markets |
| `InventorySpread` | `δ = base * (1 + abs(q)/Q_max)` | Widens when inventory high |
| `TimeDecaySpread` | `δ = base / sqrt(T)` | Widens near settlement |

**Configuration:**
```yaml
strategy:
  components:
    spread:
      type: fixed            # fixed, volatility, inventory, time_decay
      params:
        base_spread: 0.02
        vol_multiplier: 0.5  # For volatility spread
```

**Acceptance Criteria:**
- [ ] `SpreadCalculator` ABC defined
- [ ] `FixedSpread` returns constant half-spread
- [ ] `VolatilitySpread` scales with market volatility
- [ ] `InventorySpread` widens to protect when inventory high
- [ ] `TimeDecaySpread` increases spread near settlement
- [ ] All implementations respect minimum spread

#### FR-415: Quote Sizer Interface
The system SHALL define a pluggable interface for quote sizing.

**Interface:**
```python
class QuoteSizer(ABC):
    """Calculates quote sizes for bid and ask."""

    @abstractmethod
    def calculate(
        self,
        inventory: int,
        max_inventory: int,
        base_size: int,
    ) -> tuple[int, int]:
        """Return (bid_size, ask_size)."""
        ...
```

**Provided Implementations:**

| Implementation | Behavior | Use Case |
|----------------|----------|----------|
| `AsymmetricSizer` | FR-403 formula, encourages rebalancing | Default |
| `LinearSizer` | `size = base * (1 - abs(q)/Q_max)` | Reduces both sides equally |
| `FixedSizer` | `size = base_size` always | Simple baseline |
| `KellySizer` | Size based on edge estimate | Advanced |

**Configuration:**
```yaml
strategy:
  components:
    sizer:
      type: asymmetric       # asymmetric, linear, fixed, kelly
      params:
        base_size: 100
```

**Acceptance Criteria:**
- [ ] `QuoteSizer` ABC defined
- [ ] `AsymmetricSizer` implements FR-403 formula
- [ ] `LinearSizer` reduces size symmetrically
- [ ] `FixedSizer` for baseline comparison
- [ ] All implementations respect max position limits

#### FR-416: Strategy Composition Configuration
The system SHALL support composing strategies from components via configuration.

**Full Configuration Example:**
```yaml
strategy:
  # Select component implementations
  components:
    volatility:
      type: ewma
      params:
        alpha: 0.94

    reservation_price:
      type: avellaneda_stoikov
      params:
        gamma: 0.1

    skew:
      type: linear
      params:
        intensity: 0.01

    spread:
      type: volatility
      params:
        base_spread: 0.02
        vol_multiplier: 0.5

    sizer:
      type: asymmetric
      params:
        base_size: 100

  # Global strategy parameters
  max_inventory: 1000
  min_spread: 0.01
  price_bounds:
    min: 0.01
    max: 0.99
```

**Pre-built Strategy Presets:**
```yaml
# Use a preset instead of configuring each component
strategy:
  preset: conservative    # conservative, aggressive, baseline

# Presets:
# - conservative: wide spreads, strong skew, small sizes
# - aggressive: tight spreads, light skew, large sizes
# - baseline: fixed spread, no skew (for comparison)
```

**Acceptance Criteria:**
- [ ] All components selectable via YAML configuration
- [ ] Invalid component combinations detected at startup
- [ ] Pre-built presets for common configurations
- [ ] Component parameters validated with clear error messages
- [ ] Hot-reload of parameters without restart (future)

### 2.5 Risk Manager (FR-500)

#### FR-501: Position Limits
The system SHALL enforce hard position limits.

**Acceptance Criteria:**
- [ ] Maximum contracts per side (YES and NO independently)
- [ ] Maximum net inventory (YES - NO)
- [ ] Maximum notional exposure
- [ ] Reject quotes that would exceed limits
- [ ] Limits configurable per market

#### FR-502: Time-Based Rules
The system SHALL enforce time-based trading restrictions.

**Acceptance Criteria:**
- [ ] Stop placing new orders in final N minutes before settlement (default: 3 minutes)
- [ ] Cancel all open orders before settlement cutoff
- [ ] Configurable cutoff period per market type

#### FR-503: PnL Limits
The system SHALL enforce profit/loss limits.

**Acceptance Criteria:**
- [ ] Maximum loss per hour triggers kill switch
- [ ] Maximum loss per day triggers kill switch
- [ ] Configurable thresholds
- [ ] Track both realized and unrealized PnL

#### FR-504: Kill Switch
The system SHALL implement an emergency stop mechanism.

**Triggers:**
- PnL limit breach
- Manual activation
- Anomaly detection (future)

**Actions:**
- Cancel all open orders immediately
- Block all new order placement
- Log the trigger reason
- Require manual intervention to resume

**Acceptance Criteria:**
- [ ] Kill switch activates within 1 second of trigger
- [ ] All orders cancelled successfully
- [ ] System enters "halted" state
- [ ] Clear logging of trigger reason
- [ ] Manual reset required (no auto-resume)

### 2.5.1 Pluggable Risk Rules (FR-510)

The risk manager SHALL support pluggable risk rules that can be enabled, disabled, and configured independently.

#### FR-510: Risk Rule Interface
The system SHALL define a pluggable interface for risk rules.

**Interface:**
```python
class RiskRule(ABC):
    """A single risk rule that evaluates proposed quotes."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable rule name."""
        ...

    @abstractmethod
    def evaluate(
        self,
        proposed_quotes: QuoteSet,
        context: RiskContext,
    ) -> RiskDecision:
        """
        Evaluate quotes against this rule.

        Returns:
            RiskDecision with action (ALLOW, MODIFY, BLOCK) and reason
        """
        ...


@dataclass
class RiskContext:
    """Context provided to risk rules for evaluation."""
    current_inventory: int
    max_inventory: int
    positions: dict[str, Position]
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    hourly_pnl: Decimal
    daily_pnl: Decimal
    time_to_settlement: float
    current_volatility: Decimal
    market_snapshot: MarketSnapshot


@dataclass
class RiskDecision:
    """Result of a risk rule evaluation."""
    action: Literal["ALLOW", "MODIFY", "BLOCK"]
    reason: str | None = None
    modified_quotes: QuoteSet | None = None  # If action == MODIFY
    trigger_kill_switch: bool = False
```

**Risk Manager Pipeline:**
```
ProposedQuotes ──► Rule1 ──► Rule2 ──► Rule3 ──► ApprovedQuotes
                    │         │         │
                    ▼         ▼         ▼
                 ALLOW     MODIFY    BLOCK
                           (adjust)  (reject)
```

**Acceptance Criteria:**
- [ ] `RiskRule` ABC defined with `evaluate()` method
- [ ] `RiskContext` provides all data rules might need
- [ ] `RiskDecision` supports ALLOW, MODIFY, BLOCK actions
- [ ] Rules executed in configured order (priority chain)
- [ ] First BLOCK stops evaluation and rejects quotes
- [ ] MODIFY rules can adjust quotes for subsequent rules

#### FR-511: Built-in Risk Rules
The system SHALL provide the following built-in risk rules.

**Position Limit Rules:**

| Rule | Description | Default |
|------|-------------|---------|
| `MaxInventoryRule` | Block if quote would exceed max net inventory | 1000 |
| `MaxPositionPerSideRule` | Block if YES or NO position exceeds limit | 1000 |
| `MaxOrderSizeRule` | Block/modify if single order too large | 500 |
| `MaxNotionalRule` | Block if total notional exposure exceeded | $500 |

**Time-Based Rules:**

| Rule | Description | Default |
|------|-------------|---------|
| `SettlementCutoffRule` | Block quotes in final N minutes | 3 min |
| `MarketHoursRule` | Block outside trading hours | Always on |

**PnL Rules:**

| Rule | Description | Default |
|------|-------------|---------|
| `HourlyLossLimitRule` | Kill switch if hourly loss exceeds limit | $50 |
| `DailyLossLimitRule` | Kill switch if daily loss exceeds limit | $100 |
| `DrawdownRule` | Kill switch if drawdown from peak exceeds limit | $75 |

**Market Condition Rules:**

| Rule | Description | Default |
|------|-------------|---------|
| `HighVolatilityRule` | Widen spread when σ > threshold | 2x normal |
| `WideSpreadRule` | Block if market spread unusually wide | 3x normal |
| `StaleDataRule` | Block if market data older than threshold | 5 sec |

**Acceptance Criteria:**
- [ ] All rules listed above implemented
- [ ] Each rule independently enable/disable via config
- [ ] Each rule's thresholds configurable
- [ ] Rules log their decisions for debugging
- [ ] Kill switch rules can halt trading immediately

#### FR-512: Custom Risk Rules
The system SHALL support user-defined custom risk rules.

**Custom Rule Example:**
```python
class MyCustomRule(RiskRule):
    """Block trading when inventory is high AND volatility is high."""

    @property
    def name(self) -> str:
        return "high_inventory_high_vol"

    def evaluate(
        self,
        proposed_quotes: QuoteSet,
        context: RiskContext,
    ) -> RiskDecision:
        inventory_pct = abs(context.current_inventory) / context.max_inventory
        vol_ratio = context.current_volatility / self.normal_volatility

        if inventory_pct > 0.8 and vol_ratio > 1.5:
            return RiskDecision(
                action="BLOCK",
                reason=f"High inventory ({inventory_pct:.0%}) + high vol ({vol_ratio:.1f}x)"
            )
        return RiskDecision(action="ALLOW")
```

**Registration:**
```yaml
risk:
  custom_rules:
    - module: my_rules.MyCustomRule
      enabled: true
      params:
        normal_volatility: 0.05
```

**Acceptance Criteria:**
- [ ] Custom rules loadable from Python modules
- [ ] Custom rules receive same context as built-in rules
- [ ] Custom rule errors caught and logged (don't crash system)
- [ ] Custom rules can be enabled/disabled via config

#### FR-513: Risk Rule Configuration
The system SHALL support comprehensive risk rule configuration.

**Full Configuration Example:**
```yaml
risk:
  # Rule execution order (first match wins for BLOCK)
  rule_order:
    - settlement_cutoff    # Time-based first
    - stale_data
    - daily_loss_limit     # PnL limits
    - hourly_loss_limit
    - max_inventory        # Position limits
    - max_order_size
    - high_volatility      # Market conditions (can MODIFY)

  # Individual rule configuration
  rules:
    settlement_cutoff:
      enabled: true
      cutoff_minutes: 3

    daily_loss_limit:
      enabled: true
      limit: 100.00
      action: kill_switch

    hourly_loss_limit:
      enabled: true
      limit: 50.00
      action: kill_switch

    max_inventory:
      enabled: true
      limit: 1000

    max_order_size:
      enabled: true
      limit: 500
      action: modify        # Reduce size instead of blocking

    high_volatility:
      enabled: true
      threshold_multiplier: 2.0
      action: modify        # Widen spread
      spread_multiplier: 1.5

    stale_data:
      enabled: true
      max_age_seconds: 5

  # Global settings
  kill_switch:
    enabled: true
    require_manual_reset: true
```

**Acceptance Criteria:**
- [ ] All rules configurable via YAML
- [ ] Rule order explicitly configurable
- [ ] Rules can be individually enabled/disabled
- [ ] Invalid configurations detected at startup
- [ ] Default configuration provided if not specified

### 2.6 Execution Engine (FR-600)

#### FR-601: Order Lifecycle Management
The system SHALL manage the complete order lifecycle.

**States:** Pending → Open → PartiallyFilled → Filled/Cancelled/Rejected

**Acceptance Criteria:**
- [ ] Track all orders with unique client order IDs
- [ ] Update order state on exchange confirmations
- [ ] Handle partial fills correctly
- [ ] Detect and handle stuck orders

#### FR-602: Diff-Based Updates
The system SHALL use intelligent diffing to minimize API calls.

**Acceptance Criteria:**
- [ ] Compare desired quotes to current live orders
- [ ] Only send updates when price or size changes materially
- [ ] Configurable materiality threshold (default: 1 tick)
- [ ] Avoid cancel/replace storms

#### FR-603: Rate Limiting
The system SHALL respect Kalshi API rate limits.

**Acceptance Criteria:**
- [ ] Implement token bucket rate limiter
- [ ] Default to Basic tier limits (10 writes/sec)
- [ ] Configurable for higher tiers
- [ ] Queue excess requests (don't drop)
- [ ] Log rate limit approaching/exceeded events

#### FR-604: Paper Trading Mode
The system SHALL support paper trading with simulated fills.

**Fill Simulation Rules (Top-of-Book Crossing):**
- Virtual bid filled when bid_price >= market best_ask
- Virtual ask filled when ask_price <= market best_bid
- Fill price = crossing price (best_ask or best_bid)
- Fill size = min(order_size, available_size)

**Acceptance Criteria:**
- [ ] Process live market data via WebSocket
- [ ] Maintain virtual order book
- [ ] Simulate fills using crossing rule
- [ ] Track virtual positions and PnL
- [ ] No real orders sent to exchange
- [ ] Identical interface to live execution

### 2.7 State Store (FR-700)

#### FR-701: Position Tracking
The system SHALL maintain accurate position state.

**Acceptance Criteria:**
- [ ] Track YES and NO quantities per market
- [ ] Track average entry prices
- [ ] Calculate net inventory
- [ ] Calculate notional exposure
- [ ] Update immediately on fills

#### FR-702: PnL Calculation
The system SHALL calculate real-time PnL including fees.

**PnL Components:**
```
Gross PnL = Realized PnL + Unrealized PnL
Net PnL   = Gross PnL - Total Fees
```

**Fee Tracking:**

| Fee Type | Source | When Charged |
|----------|--------|--------------|
| Trading fee | Exchange | Per fill |
| Settlement fee | Exchange | On contract settlement |
| API fee | Exchange (if applicable) | Per API call |

**Kalshi Fee Structure (example):**
- Taker fee: 7% of profit (capped)
- Maker rebate: Varies
- No fee on losing trades

**PnL Calculation:**
```python
# Per trade
trade_pnl = (exit_price - entry_price) * quantity
trade_fee = calculate_fee(trade_pnl, fee_structure)
net_trade_pnl = trade_pnl - trade_fee

# Aggregate
realized_pnl = sum(closed_trade_pnls)
total_fees = sum(all_fees)
unrealized_pnl = sum(open_position_mtm)
gross_pnl = realized_pnl + unrealized_pnl
net_pnl = gross_pnl - total_fees
```

**Fee Configuration:**
```yaml
fees:
  exchange: kalshi
  structure:
    taker_rate: 0.07           # 7% of profit
    maker_rebate: 0.00         # No rebate on basic tier
    min_fee: 0.00
    max_fee_per_contract: 0.07  # $0.07 cap
  track_estimated_fees: true    # Estimate fees for unrealized PnL
```

**Acceptance Criteria:**
- [ ] Realized PnL from closed trades
- [ ] Unrealized PnL marked to mid-price
- [ ] Fees tracked per trade
- [ ] Gross PnL (before fees) calculated
- [ ] Net PnL (after fees) calculated
- [ ] Fee breakdown available (trading, settlement, other)
- [ ] PnL per market and aggregate
- [ ] Historical fee totals queryable

#### FR-703: Reconciliation
The system SHALL periodically reconcile with exchange state.

**Acceptance Criteria:**
- [ ] Compare local positions to exchange positions
- [ ] Alert on any divergence
- [ ] Configurable reconciliation interval
- [ ] Log all reconciliation results

### 2.8 Persistence (FR-800)

#### FR-801: Order History
The system SHALL persist all order activity.

**Acceptance Criteria:**
- [ ] Store every order: id, market, side, price, size, status, timestamps
- [ ] Store every fill: id, order_id, price, size, timestamp
- [ ] Query orders by market, time range, status

#### FR-802: PnL Snapshots
The system SHALL persist periodic PnL snapshots.

**Acceptance Criteria:**
- [ ] Snapshot interval configurable (default: 1 minute)
- [ ] Include: timestamp, realized_pnl, unrealized_pnl, positions
- [ ] Support historical PnL queries

#### FR-803: Market Data Samples
The system SHALL optionally persist market data for analysis.

**Acceptance Criteria:**
- [ ] Store order book snapshots at configurable intervals
- [ ] Store trade events
- [ ] Support replay for backtesting

### 2.9 Recording and Replay (FR-900)

The system SHALL support recording trading sessions and replaying them for debugging and backtesting.

#### FR-901: Session Recording
The system SHALL record all events necessary to fully replay a trading session.

**Recorded Event Types:**

| Event | Fields | Trigger |
|-------|--------|---------|
| `session_start` | session_id, timestamp, config, market_ids | Session begins |
| `book_snapshot` | timestamp, market_id, bids[], asks[] | On connect + periodic |
| `book_delta` | timestamp, market_id, side, price, size, action | Every book update |
| `trade` | timestamp, market_id, price, size, side | Public trade occurs |
| `volatility_update` | timestamp, market_id, sigma | Volatility recalculated |
| `quote_generated` | timestamp, inputs{}, yes_quotes{}, no_quotes{} | Strategy produces quotes |
| `order_sent` | timestamp, client_order_id, market_id, side, price, size | Order submitted |
| `order_ack` | timestamp, client_order_id, exchange_order_id, status | Exchange confirms |
| `order_rejected` | timestamp, client_order_id, reason | Exchange rejects |
| `fill` | timestamp, order_id, price, size, remaining | Execution occurs |
| `state_snapshot` | timestamp, positions{}, pnl{}, inventory | Periodic checkpoint |
| `session_end` | timestamp, reason, final_pnl | Session terminates |

**Recording Format:**
```json
{"ts": 1705500000.123, "type": "book_delta", "market": "BTC-hourly", "side": "bid", "price": 0.52, "size": 100, "action": "add"}
{"ts": 1705500000.456, "type": "quote_generated", "inputs": {"mid": 0.50, "sigma": 0.05, "q": 100, "T": 0.5}, "yes_bid": 0.48, "yes_ask": 0.52, ...}
```

**Storage:**
- Format: JSON Lines (`.jsonl`) - one event per line
- Compression: gzip for archived sessions
- Naming: `session_{market}_{YYYYMMDD}_{HHMM}.jsonl.gz`
- Location: `./data/sessions/`

**Acceptance Criteria:**
- [ ] All event types listed above are recorded
- [ ] Events are written with microsecond-precision timestamps
- [ ] Recording can be enabled/disabled via configuration
- [ ] Recording has minimal performance impact (< 5ms latency added)
- [ ] Sessions are automatically named and organized by date
- [ ] Configurable snapshot interval (default: 60 seconds)
- [ ] Record strategy inputs alongside outputs for debugging

#### FR-902: Session Replay (Deterministic)
The system SHALL support replaying recorded sessions to reproduce exact behavior.

**Replay Architecture:**
```
┌─────────────────┐      ┌──────────────────────┐
│  Session File   │ ──►  │   ReplayExchange     │
│  (.jsonl)       │      │   Adapter            │
└─────────────────┘      └──────────────────────┘
                                   │
                                   │ (feeds events at recorded timestamps)
                                   ▼
                         ┌──────────────────────┐
                         │   Trading System     │
                         │   (unmodified)       │
                         └──────────────────────┘
                                   │
                                   ▼
                         ┌──────────────────────┐
                         │   Replay Validator   │
                         │   (compare outputs)  │
                         └──────────────────────┘
```

**Replay Modes:**

| Mode | Time Handling | Fill Handling | Use Case |
|------|---------------|---------------|----------|
| `realtime` | Wait real wall-clock time | Replay recorded fills | Watch replay live |
| `accelerated` | Configurable speedup (10x, 100x) | Replay recorded fills | Quick review |
| `instant` | No delays | Replay recorded fills | CI/testing |

**Determinism Requirements:**
- Same session file + same config = identical outputs
- Random seeds recorded and restored
- Timestamps injected from recording (not wall clock)

**Acceptance Criteria:**
- [ ] Replay produces identical `quote_generated` events as original
- [ ] Replay produces identical `order_sent` events as original
- [ ] State snapshots match at each checkpoint
- [ ] Supports realtime, accelerated, and instant modes
- [ ] ReplayExchangeAdapter implements full ExchangeAdapter interface
- [ ] Divergence detection with clear error reporting
- [ ] Can replay from any state_snapshot (partial replay)

#### FR-903: Backtesting Engine
The system SHALL support backtesting strategies against recorded market data with simulated fills.

**Backtest vs Replay Difference:**

| Aspect | Replay (FR-902) | Backtest (FR-903) |
|--------|-----------------|-------------------|
| Fills | Replay recorded fills | Simulate based on book state |
| Purpose | Debug/verify system | Evaluate strategy performance |
| Output | Pass/fail (matches original) | PnL metrics, statistics |
| Strategy | Must match original | Can test modified strategies |

**Simulated Fill Logic:**
```
For each quote_generated event:
  If YES_bid >= best_ask from book:
    Simulate fill at best_ask (we buy YES)
  If YES_ask <= best_bid from book:
    Simulate fill at best_bid (we sell YES)
  (Same logic for NO side)
```

**Fill Simulation Modes:**

| Mode | Description | Realism |
|------|-------------|---------|
| `optimistic` | Fill immediately if price crosses | Low (ignores queue) |
| `pessimistic` | Only fill if we'd be at top of book | High (conservative) |
| `probabilistic` | Random fill based on queue position | Medium |

**Backtest Output:**

```
Backtest Report: session_BTC-hourly_20260117_1400.jsonl
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Duration:        3600 seconds
Total Trades:    47
Win Rate:        62.3%
Gross PnL:       $12.34
Fees:            $2.35
Net PnL:         $9.99
Max Drawdown:    $4.50
Sharpe (hourly): 1.23

Quote Statistics:
  Quotes Generated:  720
  Quotes Filled:     47 (6.5%)
  Avg Spread:        $0.02

Inventory:
  Max Long:          +340 contracts
  Max Short:         -120 contracts
  Time at Limit:     2.3%
```

**Acceptance Criteria:**
- [ ] Backtest runs against any recorded session file
- [ ] Supports optimistic, pessimistic, and probabilistic fill modes
- [ ] Generates comprehensive PnL report
- [ ] Calculates key metrics: PnL, win rate, Sharpe, max drawdown
- [ ] Can run modified strategy parameters against same data
- [ ] Supports parameter sweeps (grid search over gamma, spread, etc.)
- [ ] Output exportable as JSON/CSV for further analysis
- [ ] Backtest completes in < 10 seconds for 1-hour session

#### FR-904: Recording Configuration
The system SHALL support flexible recording configuration.

**Configuration Options:**
```yaml
recording:
  enabled: true
  output_dir: ./data/sessions

  # What to record
  events:
    book_snapshots: true
    book_deltas: true
    trades: true
    quotes: true
    orders: true
    fills: true
    state: true

  # Intervals
  snapshot_interval_seconds: 60

  # Storage management
  compression: gzip              # none, gzip
  retention_days: 30             # auto-delete after N days
  max_storage_mb: 1000           # stop recording if exceeded

  # Performance
  async_write: true              # buffer writes to avoid blocking
  buffer_size: 1000              # events to buffer before flush
```

**Acceptance Criteria:**
- [ ] All recording options configurable via YAML
- [ ] Can selectively enable/disable event types
- [ ] Automatic storage management (retention, size limits)
- [ ] Async writing does not block trading loop
- [ ] Graceful handling when storage limit reached

### 2.10 Hot Configuration and Component Swap (FR-1000)

The system SHALL support changing configuration and swapping components at runtime without requiring a restart.

#### FR-1001: Configuration Hot-Reload
The system SHALL support reloading configuration parameters at runtime.

**Hot-Reloadable Parameters:**

| Category | Parameters | Reload Behavior |
|----------|------------|-----------------|
| Strategy | gamma, base_spread, skew_intensity, quote_size | Apply on next quote cycle |
| Risk | All rule thresholds and limits | Apply immediately |
| Recording | Event toggles, intervals | Apply immediately |
| Logging | Log level | Apply immediately |

**Non-Hot-Reloadable (require restart):**

| Category | Parameters | Reason |
|----------|------------|--------|
| Exchange | API credentials, endpoints | Security, connection state |
| Database | Connection string | Connection pool |
| Market | Market IDs to trade | Subscription state |

**Reload Triggers:**

| Trigger | Description |
|---------|-------------|
| File watch | Automatic reload when config file changes |
| API endpoint | `POST /config/reload` |
| Signal | `SIGHUP` triggers reload |
| CLI command | Interactive reload command |

**Reload Process:**
```
1. Detect change (file/API/signal)
2. Parse new configuration
3. Validate against schema
4. Validate business rules (e.g., max_inventory > 0)
5. Create atomic snapshot of current config
6. Apply changes in safe order
7. Log all changes with before/after values
8. If error: rollback to snapshot
```

**Acceptance Criteria:**
- [ ] Config file changes detected within 1 second
- [ ] Invalid configs rejected with clear error message
- [ ] Failed reload does not affect running system
- [ ] All parameter changes logged with old/new values
- [ ] Reload event recorded in session recording

#### FR-1002: Component Hot-Swap
The system SHALL support swapping strategy and risk components at runtime.

**Hot-Swappable Components:**

| Component | Swap Behavior | State Handling |
|-----------|---------------|----------------|
| `VolatilityEstimator` | Swap on next update | New estimator starts fresh or inherits state |
| `ReservationPriceCalculator` | Swap on next quote cycle | Stateless, immediate |
| `SkewCalculator` | Swap on next quote cycle | Stateless, immediate |
| `SpreadCalculator` | Swap on next quote cycle | Stateless, immediate |
| `QuoteSizer` | Swap on next quote cycle | Stateless, immediate |
| `RiskRule` (individual) | Swap immediately | Stateless, immediate |

**Component Swap Process:**
```
1. Load new component class
2. Instantiate with new parameters
3. Validate component (type check, required methods)
4. If stateful: optionally transfer state
5. Atomic swap reference
6. Log swap event
7. Old component garbage collected
```

**State Transfer for Stateful Components:**
```python
class VolatilityEstimator(ABC):
    @abstractmethod
    def get_state(self) -> dict:
        """Export internal state for transfer."""
        ...

    @abstractmethod
    def set_state(self, state: dict) -> None:
        """Import state from previous estimator."""
        ...
```

**Example: Swap Volatility Estimator**
```yaml
# Original config
strategy:
  components:
    volatility:
      type: ewma
      params:
        alpha: 0.94

# Updated config (triggers hot-swap)
strategy:
  components:
    volatility:
      type: realized
      params:
        window_seconds: 300
      state_transfer: true    # Transfer accumulated state if compatible
```

**Acceptance Criteria:**
- [ ] Component swap completes within 100ms
- [ ] No quotes generated during swap (brief pause acceptable)
- [ ] Swap failures leave old component in place
- [ ] State transfer supported for stateful components
- [ ] Swap event recorded in session recording
- [ ] Clear logging of component transitions

#### FR-1003: Risk Rule Hot-Swap
The system SHALL support enabling, disabling, and modifying risk rules at runtime.

**Operations:**

| Operation | Description | Behavior |
|-----------|-------------|----------|
| Enable rule | Activate a disabled rule | Immediate |
| Disable rule | Deactivate a rule | Immediate |
| Modify rule | Change rule parameters | Immediate |
| Add rule | Add new custom rule | Immediate |
| Remove rule | Remove custom rule | Immediate |
| Reorder rules | Change evaluation order | Immediate |

**Safety Constraints:**
- Kill switch rules cannot be disabled while trading
- At least one position limit rule must be active
- Disabling critical rules requires confirmation flag

**Configuration:**
```yaml
risk:
  rules:
    daily_loss_limit:
      enabled: true
      limit: 100.00
      # Hot-reload this to change limit:
      limit: 75.00           # Takes effect immediately

    # Disable a rule at runtime
    high_volatility:
      enabled: false         # Was true, now disabled

  # Critical rules that require explicit override to disable
  critical_rules:
    - daily_loss_limit
    - hourly_loss_limit
    - max_inventory
```

**Acceptance Criteria:**
- [ ] Rule enable/disable takes effect within 1 quote cycle
- [ ] Rule parameter changes apply immediately
- [ ] Critical rules require `force: true` to disable
- [ ] Rule changes logged with reason
- [ ] Rule state changes recorded in session

#### FR-1004: Live Parameter Adjustment API
The system SHALL provide an API for runtime parameter adjustment.

**API Endpoints:**

```
GET  /config                     # Get current configuration
GET  /config/strategy            # Get strategy config
GET  /config/risk                # Get risk config
POST /config/reload              # Reload from file
PUT  /config/strategy/params     # Update strategy parameters
PUT  /config/risk/rules/{name}   # Update specific risk rule
POST /config/component/swap      # Swap a component
GET  /config/history             # Get config change history
POST /config/rollback/{version}  # Rollback to previous config
```

**Example: Adjust Gamma at Runtime**
```bash
# Increase risk aversion during volatile period
curl -X PUT http://localhost:8080/config/strategy/params \
  -H "Content-Type: application/json" \
  -d '{"gamma": 0.2}'

# Response
{
  "status": "applied",
  "changes": [
    {"param": "gamma", "old": 0.1, "new": 0.2}
  ],
  "applied_at": "2026-01-17T14:30:00Z"
}
```

**Example: Swap Skew Calculator**
```bash
curl -X POST http://localhost:8080/config/component/swap \
  -H "Content-Type: application/json" \
  -d '{
    "component": "skew",
    "type": "exponential",
    "params": {"intensity": 0.015}
  }'
```

**Acceptance Criteria:**
- [ ] All endpoints authenticated
- [ ] Changes validated before applying
- [ ] Response includes before/after state
- [ ] Failed changes return clear error
- [ ] Rate limiting on config changes (prevent rapid flapping)

#### FR-1005: Configuration Versioning and Rollback
The system SHALL maintain configuration history and support rollback.

**Version Tracking:**
```
config_history/
├── 2026-01-17T14:00:00Z.yaml    # Initial config
├── 2026-01-17T14:30:00Z.yaml    # Gamma changed to 0.2
├── 2026-01-17T15:00:00Z.yaml    # Skew swapped to exponential
└── current.yaml -> 2026-01-17T15:00:00Z.yaml
```

**Rollback Process:**
```
1. Select target version
2. Validate target config still valid
3. Cancel outstanding orders (safety)
4. Apply target config atomically
5. Log rollback event
6. Resume quoting with new config
```

**Acceptance Criteria:**
- [ ] Last N config versions retained (configurable, default 20)
- [ ] Rollback completes within 5 seconds
- [ ] Rollback cancels orders before applying (safety)
- [ ] Rollback recorded in session with reason
- [ ] Cannot rollback to config with invalid components

#### FR-1006: Safe Transition During Hot-Swap
The system SHALL ensure safe state transitions during configuration changes.

**Transition Safety Protocol:**

| Phase | Action | Duration |
|-------|--------|----------|
| 1. Pause | Stop generating new quotes | Immediate |
| 2. Drain | Wait for pending orders to be acknowledged | Up to 5s |
| 3. Apply | Apply configuration changes | < 100ms |
| 4. Validate | Verify new config produces valid quotes | < 100ms |
| 5. Resume | Resume normal quoting | Immediate |

**Failure Handling:**

| Failure Point | Recovery Action |
|---------------|-----------------|
| Parse error | Reject, keep current config |
| Validation error | Reject, keep current config |
| Component instantiation | Reject, keep current config |
| First quote invalid | Rollback to previous config |
| Timeout during drain | Force cancel, then apply |

**Configuration:**
```yaml
hot_reload:
  enabled: true
  file_watch: true
  drain_timeout_seconds: 5
  validation_timeout_seconds: 1
  max_changes_per_minute: 10     # Prevent rapid flapping
  require_confirmation: false    # If true, changes queued for approval
```

**Acceptance Criteria:**
- [ ] No orders placed during transition
- [ ] Position remains unchanged during transition
- [ ] Transition completes within 10 seconds max
- [ ] Failed transitions leave system in known good state
- [ ] Transition events fully logged and recorded

#### FR-1007: Change Notifications
The system SHALL emit events when configuration changes.

**Event Types:**

```python
@dataclass
class ConfigChangeEvent:
    timestamp: datetime
    change_type: Literal["reload", "param_update", "component_swap", "rollback"]
    component: str
    changes: list[ParamChange]
    triggered_by: Literal["file_watch", "api", "signal", "cli"]
    success: bool
    error: str | None = None


@dataclass
class ParamChange:
    param: str
    old_value: Any
    new_value: Any
```

**Notification Channels:**

| Channel | Description |
|---------|-------------|
| Log | Structured log entry |
| Session recording | Recorded for replay |
| Webhook | POST to configured URL |
| WebSocket | Real-time to connected clients |

**Acceptance Criteria:**
- [ ] All config changes emit events
- [ ] Events include full before/after state
- [ ] Events recorded in session for replay
- [ ] Webhook notifications support retry

### 2.11 Graceful Shutdown (FR-1100)

The system SHALL support graceful shutdown with configurable order handling.

#### FR-1101: Shutdown Modes
The system SHALL support multiple shutdown modes.

**Shutdown Modes:**

| Mode | Order Handling | Position Handling | Use Case |
|------|----------------|-------------------|----------|
| `immediate` | Cancel all orders | Leave positions | Emergency stop |
| `drain` | Cancel orders, wait for fills | Leave positions | Normal shutdown |
| `unwind` | Cancel orders, place closing orders | Attempt to flatten | End of session |
| `pause` | Cancel orders, block new | Preserve for restart | Temporary stop |

**Shutdown Process:**
```
1. Receive shutdown signal (SIGTERM, SIGINT, API, kill switch)
2. Enter "shutting_down" state
3. Stop quote generation
4. Execute order handling per mode:
   - immediate: Cancel all, don't wait
   - drain: Cancel all, wait for pending fills (timeout)
   - unwind: Cancel all, place market orders to flatten
   - pause: Cancel all, save state for restart
5. Flush all pending writes (database, session recording)
6. Close exchange connections gracefully
7. Log final state (positions, PnL)
8. Exit
```

**Configuration:**
```yaml
shutdown:
  default_mode: drain
  drain_timeout_seconds: 30
  unwind:
    enabled: false              # Must explicitly enable
    max_slippage: 0.02          # Max price deviation for unwind orders
    timeout_seconds: 60
  save_state_on_pause: true
```

**Acceptance Criteria:**
- [ ] All shutdown modes implemented
- [ ] Shutdown completes within configured timeout
- [ ] Final state logged (positions, PnL, open orders)
- [ ] No data loss (all writes flushed)
- [ ] Clean WebSocket disconnection
- [ ] Exit code indicates shutdown reason

#### FR-1102: Shutdown Triggers
The system SHALL respond to multiple shutdown triggers.

| Trigger | Default Mode | Override |
|---------|--------------|----------|
| `SIGTERM` | drain | Via config |
| `SIGINT` (Ctrl+C) | drain | Via config |
| `SIGQUIT` | immediate | Cannot override |
| Kill switch | immediate | Cannot override |
| API `/control/shutdown` | Specified in request | N/A |
| Health check failure | pause | Via config |

**Acceptance Criteria:**
- [ ] All triggers handled correctly
- [ ] Signal handlers don't interfere with trading loop
- [ ] Double SIGINT forces immediate shutdown
- [ ] Shutdown reason logged

### 2.12 Crash Recovery (FR-1200)

The system SHALL recover gracefully from unexpected crashes.

#### FR-1201: State Persistence for Recovery
The system SHALL persist state sufficient to recover from crashes.

**Persisted State:**

| State | Persistence | Recovery Use |
|-------|-------------|--------------|
| Open orders (local view) | Database | Reconcile with exchange |
| Positions | Database | Verify against exchange |
| Session recording | File | Replay to verify state |
| Configuration | File | Restore settings |
| Last known good state | Checkpoint file | Fast recovery |

**Checkpoint File:**
```json
{
  "timestamp": "2026-01-17T14:30:00Z",
  "market_id": "BTC-hourly-1700",
  "positions": {"YES": 150, "NO": 0},
  "inventory": 150,
  "realized_pnl": 12.34,
  "open_orders": ["order-123", "order-456"],
  "config_version": "2026-01-17T14:00:00Z"
}
```

**Acceptance Criteria:**
- [ ] Checkpoint written every N seconds (configurable, default 10)
- [ ] Checkpoint write is atomic (write to temp, rename)
- [ ] Checkpoint includes all recovery-critical state
- [ ] Checkpoint file survives crash

#### FR-1202: Startup Recovery Protocol
The system SHALL execute a recovery protocol on startup.

**Recovery Protocol:**
```
1. Detect if previous shutdown was clean
   - Check for checkpoint file
   - Check for lock file (indicates crash)

2. If clean shutdown:
   - Normal startup
   - Optional: reconcile positions with exchange

3. If crash detected:
   a. Enter "recovery" mode (no trading)
   b. Load last checkpoint
   c. Query exchange for:
      - Current positions
      - Open orders
      - Recent fills since checkpoint
   d. Reconcile local state with exchange:
      - Update positions to match exchange
      - Update order states
      - Calculate any missed fills
   e. Log all discrepancies
   f. If discrepancies within tolerance:
      - Auto-resume trading
   g. If discrepancies exceed tolerance:
      - Require manual intervention
      - Alert operator

4. Clear crash indicators
5. Resume normal operation
```

**Configuration:**
```yaml
recovery:
  enabled: true
  checkpoint_interval_seconds: 10
  auto_resume_threshold:
    position_contracts: 10      # Auto-resume if position diff <= 10
    pnl_dollars: 5.00           # Auto-resume if PnL diff <= $5
  require_manual_approval: false  # If true, always wait for operator
```

**Acceptance Criteria:**
- [ ] Crash detected via lock file mechanism
- [ ] Full reconciliation with exchange on recovery
- [ ] Discrepancies logged with full details
- [ ] Auto-resume only within configured tolerance
- [ ] Manual intervention path clearly documented
- [ ] Recovery time < 30 seconds

#### FR-1203: Reconciliation
The system SHALL periodically reconcile local state with exchange.

**Reconciliation Checks:**

| Check | Frequency | Action on Mismatch |
|-------|-----------|-------------------|
| Position balance | Every 60s | Log warning, update local |
| Open orders | Every 30s | Cancel orphaned, recreate missing |
| Account balance | Every 300s | Log warning |

**Acceptance Criteria:**
- [ ] Periodic reconciliation runs in background
- [ ] Mismatches logged with full context
- [ ] Local state corrected to match exchange (exchange is source of truth)
- [ ] Reconciliation does not block trading loop

### 2.13 Multi-Market Support (FR-1300)

The system SHALL support trading multiple markets simultaneously.

#### FR-1301: Market Manager
The system SHALL manage multiple markets through a central coordinator.

**Architecture:**
```
┌─────────────────────────────────────────────────────────────────┐
│                        MarketManager                             │
│                                                                  │
│   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐          │
│   │  Market A   │   │  Market B   │   │  Market C   │          │
│   │  Instance   │   │  Instance   │   │  Instance   │          │
│   ├─────────────┤   ├─────────────┤   ├─────────────┤          │
│   │ • Strategy  │   │ • Strategy  │   │ • Strategy  │          │
│   │ • State     │   │ • State     │   │ • State     │          │
│   │ • Risk      │   │ • Risk      │   │ • Risk      │          │
│   └─────────────┘   └─────────────┘   └─────────────┘          │
│          │                 │                 │                   │
│          └─────────────────┼─────────────────┘                   │
│                            ▼                                     │
│                  ┌─────────────────┐                            │
│                  │  Aggregate Risk │                            │
│                  │    Manager      │                            │
│                  └─────────────────┘                            │
└─────────────────────────────────────────────────────────────────┘
```

**Per-Market Isolation:**
- Each market has independent strategy state
- Each market has independent position tracking
- Each market has independent recording

**Shared Resources:**
- Exchange connection (WebSocket, rate limiter)
- Aggregate risk limits
- Database connection
- Configuration

**Acceptance Criteria:**
- [ ] Markets operate independently (one market's error doesn't affect others)
- [ ] Shared resources properly synchronized
- [ ] Markets can be added/removed at runtime
- [ ] Per-market and aggregate metrics available

#### FR-1302: Aggregate Risk Limits
The system SHALL enforce risk limits across all markets.

**Aggregate Limits:**

| Limit | Description | Default |
|-------|-------------|---------|
| Max total notional | Sum of all market exposures | $1000 |
| Max total contracts | Sum of all positions | 5000 |
| Max daily loss (aggregate) | Combined PnL across markets | $200 |
| Max hourly loss (aggregate) | Combined PnL across markets | $100 |
| Max concurrent markets | Number of active markets | 5 |

**Per-Market vs Aggregate:**
```yaml
risk:
  per_market:
    max_inventory: 1000
    max_daily_loss: 50.00

  aggregate:
    max_total_notional: 1000.00
    max_total_contracts: 5000
    max_daily_loss: 200.00
    max_concurrent_markets: 5
```

**Acceptance Criteria:**
- [ ] Aggregate limits checked before any order
- [ ] Aggregate kill switch stops all markets
- [ ] Per-market limits still enforced independently
- [ ] Clear reporting of per-market vs aggregate usage

#### FR-1303: Market Selection and Lifecycle
The system SHALL manage market lifecycle (discovery, activation, deactivation).

**Market Lifecycle:**
```
DISCOVERED → ANALYZING → ACTIVE → SETTLING → SETTLED
                ↓
             REJECTED
```

**Market Selection Criteria:**
```yaml
market_selection:
  auto_discover: true
  filters:
    min_volume_24h: 1000        # Minimum contracts traded
    min_open_interest: 500
    max_spread: 0.05            # Maximum current spread
    min_time_to_settlement: 30  # Minutes
    categories:
      - crypto-hourly
      - crypto-daily

  max_concurrent: 3
  selection_strategy: highest_volume  # or: lowest_spread, random
```

**Acceptance Criteria:**
- [ ] Auto-discovery of eligible markets
- [ ] Markets filtered by configurable criteria
- [ ] Automatic activation of top N markets
- [ ] Graceful deactivation as markets approach settlement
- [ ] Manual override to force-add/remove markets

### 2.14 Inventory Initialization (FR-1400)

The system SHALL handle starting with pre-existing positions.

#### FR-1401: Position Import
The system SHALL import existing positions on startup.

**Import Sources:**

| Source | Method | Use Case |
|--------|--------|----------|
| Exchange query | Automatic | Default, always accurate |
| Checkpoint file | Automatic | Fast startup |
| Manual override | Config file | Testing, corrections |

**Startup Position Handling:**
```
1. Query exchange for current positions
2. If positions exist:
   a. Log all positions with details
   b. Calculate current inventory per market
   c. Initialize state store with positions
   d. Calculate unrealized PnL at current prices
3. If no positions:
   a. Start with clean slate
4. Begin normal trading loop
```

**Configuration:**
```yaml
startup:
  position_handling:
    source: exchange            # exchange, checkpoint, manual
    manual_positions:           # Only if source: manual
      BTC-hourly-1700:
        YES: 100
        NO: 0
        avg_price_yes: 0.52

  # Safety check
  max_starting_inventory: 500   # Refuse to start if inventory exceeds
  require_confirmation_if_positions: false  # Pause for operator if positions exist
```

**Acceptance Criteria:**
- [ ] Positions accurately imported from exchange
- [ ] Starting inventory reflected in strategy decisions
- [ ] Starting PnL calculated correctly
- [ ] Large unexpected positions trigger warning/confirmation
- [ ] Position import logged with full details

#### FR-1402: Average Price Tracking
The system SHALL track average entry prices for imported positions.

**Challenge:** If positions were acquired outside the system, we don't know the entry price.

**Solutions:**

| Method | Description | Accuracy |
|--------|-------------|----------|
| Query exchange | Get historical fills | High (if available) |
| Use current price | Assume entry at current mid | Low |
| Manual entry | Operator provides | High |
| Mark-to-market | Reset PnL to 0, track from now | N/A |

**Configuration:**
```yaml
startup:
  position_handling:
    avg_price_method: query_exchange  # query_exchange, current_price, manual, mark_to_market
    manual_avg_prices:
      BTC-hourly-1700:
        YES: 0.52
```

**Acceptance Criteria:**
- [ ] Average price tracked for PnL calculation
- [ ] Method configurable per use case
- [ ] Mark-to-market option for clean slate
- [ ] Warning if using estimated prices

---

## 3. Non-Functional Requirements

### 3.1 Performance (NFR-100)

#### NFR-101: Latency
- Order book update processing: < 10ms
- Quote generation: < 50ms
- Order submission (local processing): < 20ms
- Target round-trip to Kalshi: < 50ms (when hosted in AWS us-east-1)

#### NFR-102: Throughput
- Handle up to 100 order book updates/second
- Support up to 10 quote updates/second per market

### 3.2 Reliability (NFR-200)

#### NFR-201: Availability
- System should recover from crashes automatically
- WebSocket reconnection within 5 seconds
- No data loss on restart (positions recovered from exchange/database)

#### NFR-202: Error Handling
- All errors logged with context
- Trading errors trigger alerts
- Graceful degradation (stop trading if degraded, don't crash)

#### NFR-203: Time Synchronization
Accurate timestamps are critical for trading systems.

**Requirements:**
- System clock synchronized via NTP
- Maximum allowed clock drift: 100ms
- Timestamp precision: microseconds
- All timestamps in UTC

**Implementation:**
```yaml
time_sync:
  ntp_servers:
    - time.aws.amazon.com      # Primary (if on AWS)
    - pool.ntp.org             # Fallback
  max_drift_ms: 100
  check_interval_seconds: 60
  action_on_drift: warn        # warn, pause_trading, or ignore
```

**Acceptance Criteria:**
- [ ] Clock drift monitored continuously
- [ ] Alert if drift exceeds threshold
- [ ] Option to pause trading on excessive drift
- [ ] Startup check for time sync

#### NFR-204: Network Resilience
The system SHALL handle network failures gracefully.

**Failure Scenarios:**

| Scenario | Detection | Recovery |
|----------|-----------|----------|
| WebSocket disconnect | Heartbeat timeout | Reconnect with backoff |
| DNS failure | Connection error | Use cached IP, retry |
| High latency | RTT monitoring | Widen spreads, reduce size |
| Packet loss | Missing sequence numbers | Request resync |
| Full network outage | All connections fail | Pause trading, alert |

**Reconnection Strategy:**
```
Attempt 1: Immediate
Attempt 2: 1 second delay
Attempt 3: 2 seconds
Attempt 4: 4 seconds
Attempt 5: 8 seconds
...
Max delay: 60 seconds
Max attempts: Unlimited (until manual stop)
```

**Configuration:**
```yaml
network:
  reconnect:
    initial_delay_ms: 100
    max_delay_ms: 60000
    backoff_multiplier: 2.0
    jitter: true               # Add randomness to prevent thundering herd

  health_check:
    ping_interval_seconds: 30
    ping_timeout_seconds: 5
    max_missed_pings: 3

  latency:
    warn_threshold_ms: 100
    critical_threshold_ms: 500
    action_on_critical: widen_spread  # widen_spread, pause, or ignore
```

**Acceptance Criteria:**
- [ ] Automatic reconnection on disconnect
- [ ] Exponential backoff with jitter
- [ ] Latency monitoring with configurable thresholds
- [ ] Graceful handling of DNS failures
- [ ] Clear logging of all network events

### 3.3 Security (NFR-300)

#### NFR-301: Credential Management
- API keys never stored in code or config files
- Use environment variables or AWS Secrets Manager
- Credentials never logged

#### NFR-302: Audit Trail
- All order actions logged with timestamps
- Log includes order details, exchange responses, fill events
- Logs retained for minimum 90 days

### 3.4 Observability (NFR-400)

#### NFR-401: Logging
- Structured logging (JSON format)
- Log levels: DEBUG, INFO, WARNING, ERROR
- Correlation IDs for request tracing

#### NFR-402: Metrics
The system SHALL expose metrics in Prometheus format.

**Trading Metrics:**

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `mm_pnl_realized` | Gauge | market | Realized PnL in dollars |
| `mm_pnl_unrealized` | Gauge | market | Unrealized PnL |
| `mm_pnl_fees` | Counter | market, fee_type | Accumulated fees |
| `mm_inventory` | Gauge | market | Current net inventory |
| `mm_position_yes` | Gauge | market | YES contracts held |
| `mm_position_no` | Gauge | market | NO contracts held |

**Order Metrics:**

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `mm_orders_total` | Counter | market, side, status | Order count |
| `mm_fills_total` | Counter | market, side | Fill count |
| `mm_order_latency_seconds` | Histogram | market | Order round-trip time |

**System Metrics:**

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `mm_quote_generation_seconds` | Histogram | market | Quote calc time |
| `mm_book_update_seconds` | Histogram | market | Book processing time |
| `mm_websocket_connected` | Gauge | exchange | Connection status |
| `mm_clock_drift_seconds` | Gauge | | NTP drift |

**Endpoint:**
```
GET /metrics    # Prometheus format
GET /health     # Health check
GET /ready      # Readiness check
```

#### NFR-403: Alerting
The system SHALL support configurable alerts.

**Alert Channels:**

| Channel | Use Case |
|---------|----------|
| Log | Always (default) |
| Slack | Team notifications |
| PagerDuty | Critical alerts, on-call |
| Email | Daily summaries |
| Webhook | Custom integrations |

**Built-in Alerts:**

| Alert | Severity | Condition |
|-------|----------|-----------|
| `kill_switch_triggered` | Critical | Kill switch activated |
| `daily_loss_warning` | Warning | Loss > 50% of daily limit |
| `daily_loss_critical` | Critical | Loss > 80% of daily limit |
| `high_inventory` | Warning | Inventory > 80% of max |
| `websocket_disconnect` | Warning | Connection lost |
| `reconnect_failed` | Critical | 5+ reconnect failures |
| `high_latency` | Warning | Order latency > threshold |
| `clock_drift` | Warning | NTP drift > 100ms |
| `reconciliation_mismatch` | Critical | Position mismatch with exchange |
| `stale_market_data` | Warning | No updates for > 5 seconds |

**Configuration:**
```yaml
alerting:
  channels:
    slack:
      enabled: true
      webhook_url_env: SLACK_WEBHOOK_URL
      channel: "#trading-alerts"
      severities: [warning, critical]

    pagerduty:
      enabled: false
      routing_key_env: PAGERDUTY_KEY
      severities: [critical]

    email:
      enabled: false
      smtp_host: smtp.example.com
      recipients: ["alerts@example.com"]
      severities: [critical]

  # Alert throttling (prevent spam)
  throttle:
    window_seconds: 300
    max_alerts_per_window: 10

  # Custom alert rules
  custom_alerts:
    - name: low_fill_rate
      condition: "mm_fills_total / mm_orders_total < 0.01"
      window: 1h
      severity: warning
      message: "Fill rate below 1% in last hour"
```

**Acceptance Criteria:**
- [ ] Alerts delivered within 30 seconds of condition
- [ ] Alert throttling prevents spam
- [ ] Critical alerts bypass throttling
- [ ] Alert history queryable
- [ ] Test alert endpoint available

#### NFR-404: Dashboards
The system SHALL provide dashboard specifications.

**Grafana Dashboard Panels:**

1. **Overview**
   - Current PnL (realized, unrealized, net)
   - Current inventory per market
   - Active orders count
   - System health status

2. **Trading Activity**
   - Orders over time (by status)
   - Fills over time
   - Fill rate percentage
   - Average spread captured

3. **Risk**
   - Inventory vs limits
   - PnL vs daily limit
   - Time to next settlement
   - Kill switch status

4. **Performance**
   - Quote generation latency (p50, p95, p99)
   - Order latency (p50, p95, p99)
   - WebSocket message rate
   - API rate limit usage

5. **System**
   - Memory usage
   - CPU usage
   - Network I/O
   - Disk usage (sessions, database)

**Acceptance Criteria:**
- [ ] Dashboard JSON exported for Grafana import
- [ ] All critical metrics visible
- [ ] Appropriate time ranges (1h, 24h, 7d)
- [ ] Alerting thresholds visible on graphs

### 3.5 Deployment (NFR-500)

#### NFR-501: Local Development
- Full functionality available locally
- Paper trading against live data
- SQLite for persistence
- Docker Compose for consistent environment
- Credentials via `.env` file (gitignored)

#### NFR-502: AWS Deployment
- Target region: us-east-1 (for Kalshi latency)
- Container-based deployment (Docker Compose on EC2)
- SQLite for persistence (on EBS volume) - upgrade to RDS only if needed
- Secrets Manager for credentials
- CloudWatch Logs for monitoring (optional)

#### NFR-503: Database Strategy
- Start with SQLite for simplicity and zero cost
- Same Docker image for local and AWS deployment
- Upgrade to RDS PostgreSQL only when:
  - Multiple instances need concurrent write access
  - Database exceeds 1GB
  - Advanced query/analytics requirements emerge
- See `docs/architecture/infrastructure.md` for details

### 3.6 DevOps (NFR-600)

#### NFR-601: CI/CD Pipeline
The system SHALL have automated testing and deployment.

**Pipeline Stages:**

```
┌─────────┐   ┌─────────┐   ┌─────────┐   ┌─────────┐   ┌─────────┐
│  Lint   │──►│  Test   │──►│  Build  │──►│ Deploy  │──►│ Verify  │
│ & Type  │   │  Suite  │   │  Image  │   │  Stage  │   │  Stage  │
└─────────┘   └─────────┘   └─────────┘   └─────────┘   └─────────┘
```

**Stage Details:**

| Stage | Actions | Failure Behavior |
|-------|---------|------------------|
| Lint & Type | `ruff check`, `mypy`, `black --check` | Block merge |
| Test Suite | Unit, integration, replay tests | Block merge |
| Build Image | Docker build, push to registry | Block deploy |
| Deploy Stage | Deploy to staging environment | Block prod |
| Verify Stage | Smoke tests, health checks | Rollback |

**Test Categories:**

| Category | Trigger | Duration | Coverage |
|----------|---------|----------|----------|
| Unit tests | Every commit | < 2 min | Core logic |
| Integration tests | Every PR | < 10 min | Component interactions |
| Replay tests | Every PR | < 5 min | Recorded session replay |
| Backtest suite | Nightly | < 30 min | Strategy validation |
| Performance benchmarks | Weekly | < 15 min | Latency regression |

**Deployment Strategy:**

```yaml
deployment:
  strategy: blue_green         # or: rolling, canary

  blue_green:
    health_check_path: /health
    health_check_interval: 5s
    switch_after_healthy: 30s
    rollback_on_failure: true

  canary:
    initial_percentage: 10
    increment: 20
    interval: 5m
    rollback_threshold:
      error_rate: 0.01
      latency_p99_ms: 500
```

**Acceptance Criteria:**
- [ ] All tests pass before merge allowed
- [ ] Docker image built and tagged on every merge to main
- [ ] Staging deployment automatic on merge
- [ ] Production deployment requires manual approval
- [ ] Rollback completes within 2 minutes
- [ ] Deployment history tracked

#### NFR-602: Performance Benchmarks
The system SHALL maintain performance benchmarks to detect regressions.

**Benchmark Suite:**

| Benchmark | Target | Regression Threshold |
|-----------|--------|---------------------|
| Quote generation (p50) | < 10ms | > 15ms |
| Quote generation (p99) | < 50ms | > 75ms |
| Book update processing (p50) | < 2ms | > 5ms |
| Book update processing (p99) | < 10ms | > 15ms |
| Full trading loop (p50) | < 20ms | > 30ms |
| Memory per market | < 50MB | > 75MB |
| Startup time | < 5s | > 10s |

**Benchmark Execution:**
```bash
# Run benchmark suite
pytest tests/benchmarks/ --benchmark-json=results.json

# Compare against baseline
pytest-benchmark compare baseline.json results.json --fail-on-regression
```

**Tracking:**
- Benchmark results stored per commit
- Grafana dashboard for historical trends
- Automatic alerts on regression

**Acceptance Criteria:**
- [ ] Benchmarks run on every PR
- [ ] Baseline updated on release
- [ ] Regression blocks merge (configurable)
- [ ] Historical benchmark data retained

#### NFR-603: Chaos Testing
The system SHALL be tested against simulated failures.

**Chaos Scenarios:**

| Scenario | Simulation | Expected Behavior |
|----------|------------|-------------------|
| WebSocket disconnect | Kill connection | Reconnect, resume quoting |
| High latency | Add 500ms delay | Widen spreads or pause |
| Packet loss | Drop 10% of messages | Detect gaps, resync |
| Exchange timeout | Delay responses | Timeout, retry |
| Database failure | Block writes | Continue trading, queue writes |
| Memory pressure | Limit to 256MB | Graceful degradation |
| CPU spike | 100% CPU for 5s | Recover, no data loss |
| Clock drift | Skew time +5s | Detect and alert |
| Kill switch | Trigger randomly | All orders cancelled |

**Chaos Test Framework:**
```python
@chaos_test
async def test_websocket_disconnect():
    """System should reconnect and resume after disconnect."""
    # Start system
    system = await start_trading_system()

    # Verify trading
    assert system.is_quoting()

    # Inject failure
    await chaos.disconnect_websocket()

    # Verify recovery
    await asyncio.sleep(10)
    assert system.is_connected()
    assert system.is_quoting()

    # Verify no position issues
    assert system.positions_reconciled()
```

**Chaos Schedule:**

| Frequency | Test Set | Environment |
|-----------|----------|-------------|
| Per PR | Quick chaos (disconnect, timeout) | CI |
| Daily | Full chaos suite | Staging |
| Weekly | Extended chaos (multi-failure) | Staging |

**Configuration:**
```yaml
chaos:
  enabled: false               # Enable only in test environments
  scenarios:
    websocket_disconnect:
      probability: 0.01        # 1% chance per minute
      duration_seconds: 5
    latency_spike:
      probability: 0.005
      latency_ms: 500
      duration_seconds: 10
```

**Acceptance Criteria:**
- [ ] All chaos scenarios have automated tests
- [ ] System recovers from each scenario without data loss
- [ ] Recovery time documented for each scenario
- [ ] Chaos tests run in isolated environment
- [ ] Production has chaos injection disabled

#### NFR-604: Environment Parity
Development, staging, and production environments SHALL be as similar as possible.

**Environment Matrix:**

| Aspect | Local | Staging | Production |
|--------|-------|---------|------------|
| Docker image | Same | Same | Same |
| Config structure | Same | Same | Same |
| Exchange | Kalshi (paper) | Kalshi (paper) | Kalshi (live) |
| Database | SQLite | SQLite | SQLite (or RDS) |
| Secrets | .env file | Secrets Manager | Secrets Manager |
| Monitoring | Optional | Full | Full |

**Acceptance Criteria:**
- [ ] Same Docker image across all environments
- [ ] Environment-specific config via env vars only
- [ ] Staging tests against real exchange (paper mode)
- [ ] Production deployment identical to staging

---

## 4. Risk Control Requirements

### 4.1 Capital Protection (RCR-100)

#### RCR-101: Hard Limits
These limits MUST be enforced and cannot be overridden without code changes:

| Limit | Default | Description |
|-------|---------|-------------|
| Max Position Per Market | 1,000 contracts | Absolute maximum inventory |
| Max Order Size | 500 contracts | Single order size cap |
| Max Daily Loss | $100 | Kill switch trigger |
| Max Hourly Loss | $50 | Kill switch trigger |

#### RCR-102: Soft Limits
These limits trigger warnings and throttling:

| Limit | Default | Action |
|-------|---------|--------|
| Position Warning | 80% of max | Reduce quote sizes |
| Hourly Loss Warning | 50% of max | Widen spreads |
| High Volatility | 2x normal σ | Widen spreads, reduce size |

### 4.2 Settlement Protection (RCR-200)

#### RCR-201: Pre-Settlement Cutoff
- Stop new orders 3 minutes before settlement
- Cancel all open orders at cutoff
- Log remaining inventory for manual review

#### RCR-202: Settlement Handling
- Track settlement results
- Update realized PnL on settlement
- Clear positions for settled markets

### 4.3 Operational Safety (RCR-300)

#### RCR-301: Paper Trading Gate
- All new features MUST be validated in paper trading first
- Minimum paper trading period: 24 hours
- Paper trading results reviewed before live deployment

#### RCR-302: Gradual Rollout
- Start with minimum position sizes
- Scale up only after validation
- Configuration-controlled (not code changes)

---

## 5. Acceptance Criteria Summary

### 5.1 Minimum Viable Product (MVP)

The MVP is complete when:

- [ ] **Exchange Connectivity**: WebSocket connects, receives order book updates
- [ ] **Market Data**: Maintains accurate order book state for one market
- [ ] **Strategy**: Generates A-S style quotes with inventory skew
- [ ] **Risk**: Enforces position limits and time-based cutoff
- [ ] **Paper Trading**: Simulates fills against live data
- [ ] **State**: Tracks positions and PnL accurately
- [ ] **Logging**: All actions logged for debugging

### 5.2 Production Ready

Production readiness requires MVP plus:

- [ ] **Live Execution**: Places and manages real orders
- [ ] **Kill Switch**: Tested and functional
- [ ] **Persistence**: Orders and PnL persisted to database
- [ ] **Reconciliation**: Positions reconciled with exchange
- [ ] **Deployment**: Runs reliably in AWS
- [ ] **Monitoring**: Metrics and alerts configured

### 5.3 Validation Criteria

| Metric | Target | Measurement |
|--------|--------|-------------|
| Paper Trading PnL | Positive over 1 week | Simulated PnL log |
| Fill Simulation Accuracy | >90% match to live | Compare ghost mode vs actual |
| Uptime | >99% during market hours | System monitoring |
| Reconciliation Drift | 0 discrepancies | Reconciliation logs |
| Kill Switch Response | <1 second | Kill switch test |

---

## 6. Glossary

| Term | Definition |
|------|------------|
| **Avellaneda-Stoikov (A-S)** | Market making model that adjusts quotes based on inventory and volatility |
| **Binary Contract** | Contract that pays $1 if event occurs, $0 otherwise |
| **Inventory** | Net position (YES contracts - NO contracts) |
| **Kill Switch** | Emergency mechanism to halt all trading |
| **Mid-Price** | Average of best bid and best ask |
| **Paper Trading** | Simulated trading without real money |
| **Reservation Price** | Fair value adjusted for inventory risk |
| **Skew** | Adjustment to quotes based on inventory |
| **Spread** | Difference between ask and bid prices |
| **Volatility (σ)** | Standard deviation of price changes |
| **Exchange Adapter** | Component that abstracts exchange-specific API details |
| **Polymarket** | Decentralized prediction market on Polygon (planned future integration) |
| **CLOB** | Central Limit Order Book (Polymarket's order matching system) |

---

## 7. References

1. Avellaneda, M., & Stoikov, S. (2008). "High-frequency trading in a limit order book"
2. Glosten, L. R., & Milgrom, P. R. (1985). "Bid, ask and transaction prices in a specialist market with heterogeneously informed traders"
3. Kalshi API Documentation: https://trading-api.readme.io/
4. Polymarket CLOB API Documentation: https://docs.polymarket.com/
5. C4 Architecture Diagrams: `docs/architecture/`

---

## 8. Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-01-17 | Initial | Initial requirements based on design discussions |
| 1.1 | 2026-01-17 | Initial | Added FR-110 series for exchange abstraction layer (Polymarket extensibility) |
