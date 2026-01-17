# Infrastructure

**Last Updated:** 2026-01-17

## Overview

This document describes the infrastructure for running the Predictions Market Maker locally and in AWS.

**Design Principles:**
- Start simple and cheap
- Local development mirrors production
- SQLite for persistence until scale demands otherwise
- Docker for consistency across environments

---

## Deployment Phases

| Phase | Environment | Database | Monthly Cost |
|-------|-------------|----------|--------------|
| 1. Development | Local | SQLite | $0 |
| 2. Validation | AWS EC2 t3.micro | SQLite | ~$5-12 |
| 3. Production | AWS EC2 t3.small | SQLite or RDS | ~$15-30 |

---

## Phase 1: Local Development

### Architecture

```
┌─────────────────────────────────────────────────────┐
│                   Local Machine                      │
│                                                      │
│   ┌─────────────────────────────────────────────┐   │
│   │            Docker Compose                    │   │
│   │                                              │   │
│   │   ┌─────────────────────────────────────┐   │   │
│   │   │        market-maker container        │   │   │
│   │   │                                      │   │   │
│   │   │   ┌──────────────────────────────┐  │   │   │
│   │   │   │      Python Application       │  │   │   │
│   │   │   │                               │  │   │   │
│   │   │   │  • Trading Core               │  │   │   │
│   │   │   │  • Kalshi WebSocket           │  │   │   │
│   │   │   │  • Paper Trading Engine       │  │   │   │
│   │   │   └──────────────────────────────┘  │   │   │
│   │   │                 │                    │   │   │
│   │   │                 ▼                    │   │   │
│   │   │   ┌──────────────────────────────┐  │   │   │
│   │   │   │    SQLite (./data/mm.db)     │  │   │   │
│   │   │   └──────────────────────────────┘  │   │   │
│   │   └─────────────────────────────────────┘   │   │
│   └─────────────────────────────────────────────┘   │
│                                                      │
│   Volume: ./data → /app/data (persists SQLite)      │
└─────────────────────────────────────────────────────┘
           │
           │ WebSocket (wss://)
           ▼
    ┌──────────────┐
    │    Kalshi    │
    │   (live)     │
    └──────────────┘
```

### Running Locally

```bash
# Start in paper trading mode (default)
docker-compose up

# Or run directly with Python
python -m market_maker --mode paper

# View logs
docker-compose logs -f

# Stop
docker-compose down
```

### Local Files

| Path | Purpose |
|------|---------|
| `./data/mm.db` | SQLite database |
| `./data/logs/` | Application logs |
| `.env` | Environment variables (credentials) |

### Environment Variables

```bash
# .env (never commit this file)
KALSHI_API_KEY=your_api_key
KALSHI_API_SECRET=your_api_secret

# Optional overrides
MM_MODE=paper                    # paper or live
MM_LOG_LEVEL=INFO               # DEBUG, INFO, WARNING, ERROR
MM_DATABASE_PATH=./data/mm.db   # SQLite path
```

---

## Phase 2: AWS Validation

### Architecture

```
┌─────────────────────────────────────────────────────┐
│                  AWS us-east-1                       │
│                                                      │
│   ┌─────────────────────────────────────────────┐   │
│   │           EC2 t3.micro                       │   │
│   │                                              │   │
│   │   ┌─────────────────────────────────────┐   │   │
│   │   │        Docker Compose                │   │   │
│   │   │        (same as local)               │   │   │
│   │   └─────────────────────────────────────┘   │   │
│   │                     │                        │   │
│   │                     ▼                        │   │
│   │   ┌─────────────────────────────────────┐   │   │
│   │   │         EBS Volume 20GB              │   │   │
│   │   │         (SQLite + logs)              │   │   │
│   │   └─────────────────────────────────────┘   │   │
│   └─────────────────────────────────────────────┘   │
│                                                      │
│   ┌─────────────────────────────────────────────┐   │
│   │           Secrets Manager                    │   │
│   │   • KALSHI_API_KEY                          │   │
│   │   • KALSHI_API_SECRET                       │   │
│   └─────────────────────────────────────────────┘   │
│                                                      │
│   ┌─────────────────────────────────────────────┐   │
│   │           CloudWatch Logs                    │   │
│   │           (optional)                         │   │
│   └─────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

### Cost Breakdown

| Component | Monthly Cost |
|-----------|--------------|
| EC2 t3.micro (free tier or $8.35) | $0-8.35 |
| EBS 20GB gp3 | $1.60 |
| Secrets Manager (2 secrets) | $0.80 |
| Data transfer (minimal) | ~$1 |
| **Total** | **$3-12** |

### Why us-east-1?

Kalshi's servers are in us-east-1. Deploying there minimizes latency:
- Local → Kalshi: ~50-100ms
- us-east-1 → Kalshi: ~1-5ms

For market making, lower latency means better fill rates.

---

## Phase 3: Production (Future)

When ready for live trading with real capital:

### Option A: Stay on EC2 + SQLite

If SQLite handles the load (likely for single-market):

```
EC2 t3.small ($15/mo) + EBS ($2/mo) = ~$17/mo
```

Add automated backups:
```bash
# Cron job to backup SQLite to S3
0 * * * * sqlite3 /app/data/mm.db ".backup '/tmp/mm-backup.db'" && aws s3 cp /tmp/mm-backup.db s3://your-bucket/backups/mm-$(date +%Y%m%d-%H%M).db
```

### Option B: Upgrade to RDS

If you need:
- Multi-instance access
- Automated backups
- Point-in-time recovery

```
EC2 t3.small ($15/mo) + RDS db.t3.micro ($13/mo) = ~$28/mo
```

---

## Session Recording Storage (FR-900)

Session recordings enable replay and backtesting. Storage requirements:

### File Sizes (Estimated)

| Duration | Events/sec | Raw Size | Compressed |
|----------|------------|----------|------------|
| 1 hour | ~10 | ~5 MB | ~500 KB |
| 1 day | ~10 | ~120 MB | ~12 MB |
| 1 week | ~10 | ~840 MB | ~84 MB |
| 1 month | ~10 | ~3.5 GB | ~350 MB |

### Directory Structure

```
./data/
├── mm.db                          # SQLite database
├── sessions/                      # Recorded sessions
│   ├── 2026/
│   │   ├── 01/
│   │   │   ├── session_BTC-hourly_20260117_1400.jsonl.gz
│   │   │   ├── session_BTC-hourly_20260117_1500.jsonl.gz
│   │   │   └── ...
│   │   └── 02/
│   └── ...
└── backtest/                      # Backtest results
    ├── report_20260117_sweep.json
    └── ...
```

### Storage Management

```yaml
# config/recording.yaml
recording:
  output_dir: ./data/sessions
  compression: gzip
  retention_days: 30        # Auto-delete after 30 days
  max_storage_mb: 5000      # 5GB limit

  # Archive old sessions to S3 (AWS only)
  archive:
    enabled: false
    bucket: my-bucket
    prefix: market-maker/sessions/
```

### Local vs AWS

| Environment | Storage | Retention |
|-------------|---------|-----------|
| Local | `./data/sessions/` | Manual cleanup |
| AWS | EBS + optional S3 archive | 30 days local, indefinite S3 |

---

## Database Schema

SQLite schema supports all persistence requirements (FR-800):

```sql
-- Orders (FR-801)
CREATE TABLE orders (
    id TEXT PRIMARY KEY,
    client_order_id TEXT UNIQUE,
    market_id TEXT NOT NULL,
    side TEXT NOT NULL,          -- YES/NO
    order_side TEXT NOT NULL,    -- BUY/SELL
    price DECIMAL(4,2) NOT NULL,
    size INTEGER NOT NULL,
    filled_size INTEGER DEFAULT 0,
    status TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Fills (FR-801)
CREATE TABLE fills (
    id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL REFERENCES orders(id),
    price DECIMAL(4,2) NOT NULL,
    size INTEGER NOT NULL,
    timestamp TIMESTAMP NOT NULL
);

-- PnL Snapshots (FR-802)
CREATE TABLE pnl_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TIMESTAMP NOT NULL,
    market_id TEXT NOT NULL,
    realized_pnl DECIMAL(10,2) NOT NULL,
    unrealized_pnl DECIMAL(10,2) NOT NULL,
    yes_position INTEGER NOT NULL,
    no_position INTEGER NOT NULL
);

-- Market Data Samples (FR-803, optional)
CREATE TABLE market_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TIMESTAMP NOT NULL,
    market_id TEXT NOT NULL,
    best_bid DECIMAL(4,2),
    best_ask DECIMAL(4,2),
    mid_price DECIMAL(4,2)
);

-- Indexes
CREATE INDEX idx_orders_market ON orders(market_id);
CREATE INDEX idx_orders_status ON orders(status);
CREATE INDEX idx_fills_order ON fills(order_id);
CREATE INDEX idx_pnl_timestamp ON pnl_snapshots(timestamp);
```

---

## SQLite Considerations

### Why SQLite Works Here

| Concern | Why It's OK |
|---------|-------------|
| Concurrent writes | Single process, sequential writes |
| Data volume | ~1000 orders/day max = tiny |
| Query complexity | Simple queries, no joins needed |
| Backups | Just copy the file |

### SQLite Limits

| Metric | SQLite Limit | Our Usage |
|--------|--------------|-----------|
| Database size | 281 TB | < 1 GB |
| Concurrent readers | Unlimited | 1 |
| Write transactions/sec | ~1000 | < 10 |

### When to Upgrade to PostgreSQL

- Multiple market maker instances
- Need concurrent write access
- Database file > 1GB
- Need advanced queries/analytics

---

## Secrets Management

### Local Development

Use `.env` file (gitignored):

```bash
# .env
KALSHI_API_KEY=xxxxx
KALSHI_API_SECRET=xxxxx
```

### AWS

Use Secrets Manager:

```bash
# Create secrets
aws secretsmanager create-secret \
    --name market-maker/kalshi \
    --secret-string '{"api_key":"xxx","api_secret":"xxx"}'

# Application reads at startup
aws secretsmanager get-secret-value \
    --secret-id market-maker/kalshi
```

---

## Monitoring

### Local

```bash
# View logs
tail -f ./data/logs/market-maker.log

# Check SQLite
sqlite3 ./data/mm.db "SELECT * FROM pnl_snapshots ORDER BY timestamp DESC LIMIT 10;"
```

### AWS (Minimal)

CloudWatch Logs integration (optional):

```yaml
# docker-compose.aws.yml
services:
  market-maker:
    logging:
      driver: awslogs
      options:
        awslogs-group: /market-maker
        awslogs-region: us-east-1
```

---

## Disaster Recovery

### Backup Strategy

| Phase | Backup Method | Frequency |
|-------|---------------|-----------|
| Local | Git (code), manual (data) | As needed |
| AWS | EBS snapshots | Daily |
| Production | EBS + S3 | Hourly |

### Recovery Procedures

**Scenario: EC2 instance fails**

1. Launch new EC2 from AMI
2. Attach EBS volume (or restore from snapshot)
3. Start docker-compose
4. System resumes from last state

**Scenario: SQLite corruption**

1. Stop application
2. Restore from most recent backup
3. Reconcile positions with Kalshi
4. Resume trading

---

## Upgrade Path

```
Phase 1          Phase 2              Phase 3
Local            AWS EC2              AWS Production
────────────────────────────────────────────────────►

SQLite           SQLite               SQLite or RDS
(./data/)        (EBS volume)         (EBS or RDS)

$0/mo            $5-12/mo             $15-30/mo
```

Each phase uses the same Docker image and configuration, only changing:
- Where it runs (local vs EC2)
- Where secrets come from (.env vs Secrets Manager)
- Whether logs go to CloudWatch
