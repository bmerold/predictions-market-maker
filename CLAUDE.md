# Claude Code Guidelines - Predictions Market Maker

## Project Philosophy

This is a **capital-at-risk trading system**. Bugs can directly cause financial loss. All development must prioritize:

1. **Correctness over speed** - Take time to get it right
2. **Explicit over implicit** - No magic, no hidden behavior
3. **Testable over clever** - Simple code that can be verified
4. **Defense in depth** - Multiple layers of protection

## Development Workflow

### Requirements-Driven Development

- All work flows from documented requirements in `docs/requirements/`
- Before implementing, confirm the requirement is documented
- If a requirement is ambiguous, ask for clarification before proceeding
- Changes to requirements require explicit approval

### Test-Driven Development (TDD)

Follow red-green-refactor strictly:

1. **Red**: Write a failing test that defines expected behavior
2. **Green**: Write minimal code to make the test pass
3. **Refactor**: Clean up while keeping tests green

Test hierarchy:
- **Unit tests**: Fast, isolated, mock external dependencies
- **Integration tests**: Test component interactions, use test doubles for exchanges
- **Paper trading tests**: End-to-end with simulated execution
- **Smoke tests**: Verify live connectivity without placing real orders

### Trunk-Based Development

- Work directly on `main` for small changes
- Use short-lived feature branches (< 1 day) for larger work
- No long-running branches
- Use feature flags to hide incomplete work from production paths
- Every commit should leave `main` in a deployable state

### Version Control Practices

- Commit early and often with meaningful messages
- Tag releases with semantic versioning (once stable)
- Before risky changes, create a tag: `git tag -a pre-<feature> -m "Before <feature>"`
- Never force push to main

## Code Standards

### Python

- Python 3.11+
- Type hints required on all function signatures
- Use `pydantic` for data validation and settings
- Use `asyncio` for concurrent operations
- Format with `black`, lint with `ruff`
- Target 90%+ test coverage for core trading logic

### Project Structure

```
src/
  market_maker/
    adapters/       # Exchange adapters (Kalshi, Polymarket)
    core/           # Domain models, interfaces
    strategy/       # Trading strategies
    risk/           # Risk management
    execution/      # Order execution (paper/live)
    state/          # State management, persistence
tests/
  unit/
  integration/
  e2e/
docs/
  requirements/     # Formal requirements
  architecture/     # C4 diagrams, design docs
  runbooks/         # Operational procedures
```

### Error Handling

- Use explicit error types, not generic exceptions
- Trading errors must be logged with full context
- Never silently swallow exceptions in trading paths
- All errors that could affect positions must trigger alerts

## Capital Protection

### Hard Limits (enforced in code)

These limits MUST be enforced at multiple layers:

- Maximum position size per market
- Maximum total exposure across all markets
- Maximum single order size
- Daily loss limit (kill switch trigger)
- Per-hour loss limit

### Paper Trading Gate

- ALL new features must be validated in paper trading mode first
- Paper trading must use live market data
- Minimum paper trading period before live: configurable, default 24 hours
- Paper vs live is a configuration switch, not a code change

### Kill Switch

- Must be tested regularly (add to CI)
- Triggers: daily loss limit, anomaly detection, manual
- Action: cancel all orders, block new orders, alert operator
- Recovery requires explicit manual intervention

### Reconciliation

- Periodically compare local state to exchange state
- Alert on any divergence
- Log all state transitions for audit trail

## Deployment

### Environments

- **Local**: Full functionality with paper trading against live data
- **AWS Dev**: Integration testing environment
- **AWS Prod**: Live trading (future)

### Infrastructure

- Infrastructure as Code (Terraform or CDK)
- Docker containers for consistency
- Environment parity: local should mirror prod as closely as possible
- Secrets via AWS Secrets Manager, never in code or config files

## Working with Claude

### Before Writing Code

1. Confirm the requirement being addressed
2. Discuss approach if non-trivial
3. Identify what tests will be written

### When Writing Code

- Write tests first (TDD)
- Make small, incremental changes
- Explain non-obvious decisions in comments
- Run tests after each change

### Code Review Checklist

Before considering code complete:

- [ ] Tests pass
- [ ] Type hints present
- [ ] Error cases handled
- [ ] Logging appropriate for debugging
- [ ] No hardcoded secrets or credentials
- [ ] Risk limits enforced where applicable
- [ ] Documentation updated if needed

### Communication Style

- Be direct and concise
- Flag concerns or risks proactively
- Ask clarifying questions rather than assuming
- Propose alternatives when appropriate

### Exploratory Work

- All exploratory scripts, experiments, and throwaway code should be written to `/tmp`
- This keeps the repository clean and focused on production code
- Only move code into the repo when it's ready to be part of the project foundation
- Examples of exploratory work: API testing, data analysis, proof-of-concept scripts

## Commands Reference

```bash
# Run tests
pytest tests/

# Run with coverage
pytest --cov=src tests/

# Format code
black src/ tests/

# Lint
ruff check src/ tests/

# Type check
mypy src/

# Run paper trading locally
python -m market_maker --mode paper

# Run with specific config
python -m market_maker --config config/local.yaml
```

---

## Current Project State

**Last Updated:** 2026-01-17

### Completed

1. **Architecture Documentation** (`docs/architecture/`)
   - C4 Level 1: System Context diagram
   - C4 Level 2: Container diagram
   - C4 Level 3: Component diagrams (Core, Exchange, Strategy - with pluggable components)
   - Sequence diagrams (Trading Loop, Paper Trading, Recording/Replay)
   - State diagram (Order Lifecycle)
   - Class diagram (Domain Models)
   - Infrastructure documentation (local, AWS, SQLite)

2. **Requirements Documentation** (`docs/requirements/`)
   - REQ-001: Market Maker Core System (v2.0)
     - Functional requirements (FR-100 to FR-1400)
     - Exchange abstraction layer (FR-110 series)
     - Pluggable strategy components (FR-410 series)
     - Pluggable risk rules (FR-510 series)
     - Recording and replay (FR-900 series)
     - Hot configuration reload (FR-1000 series)
     - Graceful shutdown (FR-1100 series)
     - Crash recovery (FR-1200 series)
     - Multi-market support (FR-1300 series)
     - Inventory initialization (FR-1400 series)
     - Non-functional requirements (NFR-100 to NFR-600)
     - Risk control requirements (RCR-100 to RCR-300)

3. **Project Configuration**
   - CLAUDE.md (this file) with working guidelines
   - docker-compose.yml for local development
   - Dockerfile for containerization
   - config/strategy.example.yaml with full configuration options
   - .env.example for credentials

### Next Steps

1. Set up Python project structure (`pyproject.toml`, `src/`, `tests/`)
2. Implement domain models (FR-111) with TDD
3. Implement exchange adapter interfaces (FR-110)
4. Implement pluggable component interfaces (FR-410 series)
5. Implement Kalshi adapter (FR-101, FR-102, FR-103)
6. Implement mock adapter for testing (FR-114)

### Key Design Decisions

- **Strategy**: Avellaneda-Stoikov market making with inventory skew
- **Architecture**: Pluggable components for volatility, reservation price, skew, spread, sizing
- **Risk**: Pluggable risk rules with configurable pipeline
- **Target**: Kalshi crypto hourly markets (single market initially, multi-market ready)
- **Extensibility**: Abstract exchange adapter for future Polymarket support
- **Capital**: $250-$750 for testing, $5k+ for production
- **Infrastructure**: SQLite locally and on AWS, same Docker image everywhere
- **Operations**: Hot reload, graceful shutdown, crash recovery, session recording

### Reference Documents

- Requirements: `docs/requirements/REQ-001-market-maker-core.md`
- Architecture: `docs/architecture/README.md`
- Infrastructure: `docs/architecture/infrastructure.md`
- Configuration: `config/strategy.example.yaml`
