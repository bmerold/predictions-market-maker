# Requirements Documentation

This directory contains formal requirements for the Predictions Market Maker system.

## Requirements Index

| ID | Title | Status | Description |
|----|-------|--------|-------------|
| [REQ-001](REQ-001-market-maker-core.md) | Market Maker Core | Draft | Core system requirements for Kalshi market making |

## Requirements Structure

Each requirements document follows this structure:

1. **Overview** - Purpose, scope, target market
2. **Functional Requirements (FR)** - What the system must do
3. **Non-Functional Requirements (NFR)** - Performance, reliability, security
4. **Risk Control Requirements (RCR)** - Capital protection measures
5. **Acceptance Criteria** - How we know it's complete
6. **Glossary** - Term definitions
7. **References** - External resources

## Requirement ID Conventions

- **FR-XXX** - Functional Requirement
- **NFR-XXX** - Non-Functional Requirement
- **RCR-XXX** - Risk Control Requirement

### Numbering Scheme

| Range | Category |
|-------|----------|
| FR-100 | Exchange Adapter (Kalshi-specific) |
| FR-110 | Exchange Abstraction Layer (multi-exchange support) |
| FR-200 | Market Data Handler |
| FR-300 | Volatility Estimator |
| FR-400 | Strategy Engine |
| FR-500 | Risk Manager |
| FR-600 | Execution Engine |
| FR-700 | State Store |
| FR-800 | Persistence |

## Design Principles

### Multi-Exchange Extensibility

The system is designed from day one to support multiple exchanges:

1. **Abstract Interfaces** - Core components depend on `ExchangeAdapter` ABC, not concrete implementations
2. **Exchange-Agnostic Models** - Domain models (Price, Order, Fill, etc.) contain no exchange-specific fields
3. **Configuration-Driven** - Exchange selection via config file, not code changes
4. **Adapter Pattern** - Each exchange has its own adapter that handles API specifics

**Current:** Kalshi
**Planned:** Polymarket

## Workflow

1. **All work flows from requirements** - Before implementing, confirm the requirement exists
2. **Requirements are versioned** - Changes tracked in revision history
3. **Acceptance criteria drive tests** - Each FR should have corresponding test(s)
4. **Status progression**: Draft → Review → Approved → Implemented

## Adding New Requirements

When adding features or changes:

1. Create or update the relevant REQ-XXX document
2. Add acceptance criteria with checkboxes
3. Update the index in this README
4. Reference the requirement in commit messages and PRs
