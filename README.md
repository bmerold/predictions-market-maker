# Predictions Market Maker

Automated market maker for binary prediction markets (Kalshi, Polymarket).

## Development

```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/

# Type checking
mypy src/

# Lint
ruff check src/ tests/
```

See `CLAUDE.md` for development guidelines.
