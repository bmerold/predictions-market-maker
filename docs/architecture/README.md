# Architecture Documentation

This directory contains C4 model architecture diagrams for the Predictions Market Maker bot.

## Viewing the Diagrams

These diagrams are written in PlantUML using the [C4-PlantUML](https://github.com/plantuml-stdlib/C4-PlantUML) extension.

### Options to render:

1. **VS Code**: Install the "PlantUML" extension, then use `Alt+D` to preview
2. **IntelliJ IDEA**: Install the "PlantUML Integration" plugin
3. **Online**: Paste contents into [PlantUML Web Server](http://www.plantuml.com/plantuml/uml/)
4. **CLI**: `plantuml *.puml` (requires Java + PlantUML jar)

---

## C4 Model Overview

The [C4 model](https://c4model.com/) provides four levels of abstraction:

1. **Context** - How the system fits in the world
2. **Container** - High-level technology building blocks
3. **Component** - Components within containers
4. **Code** - Class/code level (optional)

---

## Diagram Index

### Level 1: System Context
| File | Description |
|------|-------------|
| [c4-1-context.puml](c4-1-context.puml) | Shows the Market Maker Bot in relation to external systems (Kalshi, Polymarket) and users (Trader) |

### Level 2: Container
| File | Description |
|------|-------------|
| [c4-2-container.puml](c4-2-container.puml) | Shows high-level containers: Trading Core, Web Dashboard, Database, Configuration |

### Level 3: Component
| File | Description |
|------|-------------|
| [c4-3-component-core.puml](c4-3-component-core.puml) | Components within Trading Core: Controller, Market Data, Strategy, Risk, Execution, State |
| [c4-3-component-exchange.puml](c4-3-component-exchange.puml) | Exchange adapter layer showing abstraction for Kalshi/Polymarket extensibility |
| [c4-3-component-strategy.puml](c4-3-component-strategy.puml) | Strategy, Risk Management, and Execution pipeline details |

### Behavioral Diagrams
| File | Description |
|------|-------------|
| [sequence-trading-loop.puml](sequence-trading-loop.puml) | Main trading loop: market data → strategy → risk → execution |
| [sequence-paper-trading.puml](sequence-paper-trading.puml) | Paper trading flow: simulated fill logic |
| [sequence-recording-replay.puml](sequence-recording-replay.puml) | Recording, replay, and backtest modes |
| [state-order-lifecycle.puml](state-order-lifecycle.puml) | Order state machine: Pending → Open → Filled/Cancelled |

### Data Model
| File | Description |
|------|-------------|
| [class-domain-models.puml](class-domain-models.puml) | Core domain models: Price, Order, Position, Quote, Fill, etc. |

### Infrastructure
| File | Description |
|------|-------------|
| [infrastructure.md](infrastructure.md) | Deployment architecture: local, AWS, database strategy |

---

## Key Architectural Decisions

### 1. Exchange Abstraction
The `ExchangeAdapter` interface abstracts exchange-specific details, enabling:
- Kalshi support now
- Polymarket support later
- Easy testing with mock adapters

### 2. Paper/Live Execution Modes
`ExecutionEngine` has two implementations:
- `PaperExecutionEngine`: Simulates fills against live market data
- `LiveExecutionEngine`: Real order management with rate limiting

Both share the same interface, allowing seamless switching via configuration.

### 3. Event-Driven Architecture
Components communicate via events:
- `BookUpdate` - Order book changes
- `FillEvent` - Order fills (real or simulated)
- `QuoteSet` - Strategy output

This decouples components and enables easy testing.

### 4. Risk as a Filter
Risk Manager sits between Strategy and Execution:
- Strategy proposes quotes freely
- Risk Manager filters/modifies/blocks
- Clean separation of concerns

### 5. State Store as Single Source of Truth
All position/inventory/PnL queries go through `StateStore`:
- No direct exchange queries for current state
- Enables paper trading
- Enables reconciliation

---

## Data Flow Summary

```
Kalshi WebSocket
      │
      ▼
Exchange Adapter (normalize)
      │
      ▼
Market Data Handler (maintain book state)
      │
      ├──────────────────┐
      ▼                  ▼
Volatility Estimator   Strategy Engine
      │                  │
      └──────────────────┤
                         ▼
                   Risk Manager (filter)
                         │
                         ▼
                  Execution Engine
                         │
          ┌──────────────┴──────────────┐
          ▼                             ▼
    Paper Mode                      Live Mode
  (simulate fills)              (Kalshi REST API)
          │                             │
          └──────────────┬──────────────┘
                         ▼
                    State Store
                         │
                         ▼
                     Database
```

---

## Next Steps

After reviewing these diagrams:

1. Confirm the architecture aligns with your mental model
2. Identify any missing components or flows
3. Proceed to implementation following TDD workflow
