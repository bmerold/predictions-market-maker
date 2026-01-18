"""Entry point for the market maker application.

Usage:
    python -m market_maker --config config/strategy.yaml
    python -m market_maker --mode paper --market KXBTC-25JAN15H
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from market_maker.core.config import (
    ExchangeType,
    ExecutionMode,
    MarketConfig,
    TradingConfig,
    load_config,
)
from market_maker.core.controller import TradingController


def setup_logging(level: str, log_file: str | None = None) -> None:
    """Configure logging for the application.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR)
        log_file: Optional file to write logs to
    """
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]

    if log_file:
        handlers.append(logging.FileHandler(log_file))

    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        handlers=handlers,
    )

    # Reduce noise from third-party libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("websockets").setLevel(logging.WARNING)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Predictions Market Maker",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        "--config",
        "-c",
        type=str,
        help="Path to configuration file",
    )

    parser.add_argument(
        "--mode",
        "-m",
        choices=["paper", "live"],
        help="Execution mode (overrides config)",
    )

    parser.add_argument(
        "--exchange",
        "-e",
        choices=["kalshi", "mock"],
        help="Exchange to use (overrides config)",
    )

    parser.add_argument(
        "--market",
        "-M",
        type=str,
        action="append",
        help="Market ticker to trade (can specify multiple)",
    )

    parser.add_argument(
        "--demo",
        action="store_true",
        help="Use demo/sandbox environment",
    )

    parser.add_argument(
        "--log-level",
        "-l",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Log level",
    )

    parser.add_argument(
        "--log-file",
        type=str,
        help="Log file path",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Load config and validate without starting",
    )

    return parser.parse_args()


def build_config(args: argparse.Namespace) -> TradingConfig:
    """Build configuration from file and command line args.

    Args:
        args: Parsed command line arguments

    Returns:
        Merged configuration
    """
    # Load base config
    config = load_config(args.config)

    # Override with command line args
    if args.mode:
        config.mode = ExecutionMode(args.mode)

    if args.exchange:
        config.exchange.type = ExchangeType(args.exchange)

    if args.demo:
        config.exchange.demo = True

    if args.market:
        config.markets = [MarketConfig(ticker=m) for m in args.market]

    if args.log_level:
        config.log_level = args.log_level

    if args.log_file:
        config.log_file = args.log_file

    return config


async def main_async(config: TradingConfig) -> int:
    """Async main entry point.

    Args:
        config: Trading configuration

    Returns:
        Exit code
    """
    controller = TradingController(config)

    try:
        await controller.start()
        return 0
    except KeyboardInterrupt:
        await controller.stop()
        return 0
    except Exception as e:
        logging.error(f"Fatal error: {e}", exc_info=True)
        return 1


def main() -> int:
    """Main entry point."""
    args = parse_args()

    # Build configuration
    try:
        config = build_config(args)
    except Exception as e:
        print(f"Error loading configuration: {e}", file=sys.stderr)
        return 1

    # Set up logging
    setup_logging(config.log_level, config.log_file)

    logger = logging.getLogger(__name__)
    logger.info("Market Maker starting")
    logger.info(f"Mode: {config.mode.value}")
    logger.info(f"Exchange: {config.exchange.type.value}")
    logger.info(f"Markets: {[m.ticker for m in config.markets]}")

    # Dry run - just validate config
    if args.dry_run:
        logger.info("Dry run - configuration valid")
        return 0

    # Validate we have markets
    if not config.markets:
        logger.error("No markets specified. Use --market or configure in YAML.")
        return 1

    # Run the application
    return asyncio.run(main_async(config))


if __name__ == "__main__":
    sys.exit(main())
