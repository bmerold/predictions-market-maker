"""FastAPI routes for monitoring and control.

Provides REST API for:
- Viewing trading state
- Monitoring positions and PnL
- Runtime configuration control
- Health checks
- Web dashboard
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

if TYPE_CHECKING:
    from market_maker.core.controller import TradingController
    from market_maker.state.store import StateStore

logger = logging.getLogger(__name__)

# API models


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    timestamp: str
    uptime_seconds: float


class MarketStatus(BaseModel):
    """Status for a single market."""

    market_id: str
    is_active: bool
    yes_position: int
    no_position: int
    net_inventory: int
    realized_pnl: float
    unrealized_pnl: float
    total_pnl: float
    open_orders: int
    last_quote_time: str | None


class StatusResponse(BaseModel):
    """Overall status response."""

    running: bool
    mode: str
    markets: list[MarketStatus]
    total_pnl: float
    start_time: str
    current_time: str


class OrderInfo(BaseModel):
    """Order information."""

    id: str
    market_id: str
    side: str
    order_side: str
    price: float
    size: int
    filled_size: int
    status: str
    created_at: str


class FillInfo(BaseModel):
    """Fill information."""

    id: str
    order_id: str
    market_id: str
    side: str
    order_side: str
    price: float
    size: int
    timestamp: str
    is_simulated: bool


class ConfigUpdate(BaseModel):
    """Configuration update request."""

    gamma: float | None = None
    min_spread: float | None = None
    max_inventory: int | None = None
    kill_switch: bool | None = None


class ConfigResponse(BaseModel):
    """Current configuration response."""

    gamma: float
    sigma: float
    min_spread: float
    max_inventory: int
    kill_switch_active: bool


# Router factory


def create_monitoring_router(
    controller: TradingController | None = None,
    state_store: StateStore | None = None,
    start_time: datetime | None = None,
    mode: str = "paper",
) -> APIRouter:
    """Create monitoring API router.

    Args:
        controller: Trading controller (optional)
        state_store: State store for position/PnL data
        start_time: Application start time
        mode: Trading mode (paper/live)

    Returns:
        FastAPI router
    """
    router = APIRouter(prefix="/api/v1", tags=["monitoring"])
    _start_time = start_time or datetime.now(UTC)

    @router.get("/health", response_model=HealthResponse)
    async def health_check() -> HealthResponse:
        """Health check endpoint."""
        now = datetime.now(UTC)
        uptime = (now - _start_time).total_seconds()
        return HealthResponse(
            status="healthy",
            timestamp=now.isoformat(),
            uptime_seconds=uptime,
        )

    @router.get("/status", response_model=StatusResponse)
    async def get_status() -> StatusResponse:
        """Get overall trading status."""
        now = datetime.now(UTC)
        markets: list[MarketStatus] = []

        if state_store:
            for market_id in state_store.get_market_ids():
                position = state_store.get_position(market_id)
                pnl = state_store.get_pnl(market_id)

                markets.append(
                    MarketStatus(
                        market_id=market_id,
                        is_active=True,
                        yes_position=position.yes_quantity if position else 0,
                        no_position=position.no_quantity if position else 0,
                        net_inventory=(
                            position.net_inventory() if position else 0
                        ),
                        realized_pnl=float(pnl.realized if pnl else 0),
                        unrealized_pnl=float(pnl.unrealized if pnl else 0),
                        total_pnl=float(pnl.total if pnl else 0),
                        open_orders=0,  # Would need execution engine access
                        last_quote_time=None,
                    )
                )

        total_pnl = sum(m.total_pnl for m in markets)

        return StatusResponse(
            running=controller.is_running if controller else False,
            mode=mode,
            markets=markets,
            total_pnl=total_pnl,
            start_time=_start_time.isoformat(),
            current_time=now.isoformat(),
        )

    @router.get("/markets/{market_id}/orders", response_model=list[OrderInfo])
    async def get_orders(market_id: str) -> list[OrderInfo]:
        """Get open orders for a market."""
        if not controller:
            raise HTTPException(status_code=503, detail="Controller not available")

        orders = controller.get_open_orders(market_id)
        return [
            OrderInfo(
                id=o.id,
                market_id=o.market_id,
                side=o.side.value,
                order_side=o.order_side.value,
                price=float(o.price.value),
                size=o.size.value,
                filled_size=o.filled_size,
                status=o.status.value,
                created_at=o.created_at.isoformat(),
            )
            for o in orders
        ]

    @router.get("/markets/{market_id}/fills", response_model=list[FillInfo])
    async def get_fills(market_id: str, limit: int = 100) -> list[FillInfo]:
        """Get recent fills for a market."""
        if not controller:
            raise HTTPException(status_code=503, detail="Controller not available")

        fills = controller.get_fills(market_id)
        return [
            FillInfo(
                id=f.id,
                order_id=f.order_id,
                market_id=f.market_id,
                side=f.side.value,
                order_side=f.order_side.value,
                price=float(f.price.value),
                size=f.size.value,
                timestamp=f.timestamp.isoformat(),
                is_simulated=f.is_simulated,
            )
            for f in fills[-limit:]
        ]

    @router.get("/markets/{market_id}/position")
    async def get_position(market_id: str) -> dict[str, Any]:
        """Get position for a market."""
        if not state_store:
            raise HTTPException(status_code=503, detail="State store not available")

        position = state_store.get_position(market_id)
        if not position:
            raise HTTPException(status_code=404, detail="Market not found")

        return {
            "market_id": market_id,
            "yes_quantity": position.yes_quantity,
            "no_quantity": position.no_quantity,
            "net_inventory": position.net_inventory(),
            "avg_yes_price": (
                float(position.avg_yes_price.value)
                if position.avg_yes_price
                else None
            ),
            "avg_no_price": (
                float(position.avg_no_price.value)
                if position.avg_no_price
                else None
            ),
        }

    @router.get("/markets/{market_id}/pnl")
    async def get_pnl(market_id: str) -> dict[str, Any]:
        """Get PnL for a market."""
        if not state_store:
            raise HTTPException(status_code=503, detail="State store not available")

        pnl = state_store.get_pnl(market_id)
        if not pnl:
            raise HTTPException(status_code=404, detail="Market not found")

        return {
            "market_id": market_id,
            "realized": float(pnl.realized),
            "unrealized": float(pnl.unrealized),
            "total": float(pnl.total),
        }

    @router.get("/config", response_model=ConfigResponse)
    async def get_config() -> ConfigResponse:
        """Get current configuration."""
        if not controller:
            raise HTTPException(status_code=503, detail="Controller not available")

        config = controller.get_config()
        return ConfigResponse(
            gamma=float(config.get("gamma", 0.1)),
            sigma=float(config.get("sigma", 0.05)),
            min_spread=float(config.get("min_spread", 0.02)),
            max_inventory=int(config.get("max_inventory", 100)),
            kill_switch_active=bool(config.get("kill_switch_active", False)),
        )

    @router.post("/config")
    async def update_config(update: ConfigUpdate) -> dict[str, str]:
        """Update configuration at runtime."""
        if not controller:
            raise HTTPException(status_code=503, detail="Controller not available")

        updates: dict[str, Any] = {}
        if update.gamma is not None:
            updates["gamma"] = Decimal(str(update.gamma))
        if update.min_spread is not None:
            updates["min_spread"] = Decimal(str(update.min_spread))
        if update.max_inventory is not None:
            updates["max_inventory"] = update.max_inventory
        if update.kill_switch is not None:
            updates["kill_switch_active"] = update.kill_switch

        if updates:
            controller.update_config(updates)
            logger.info(f"Config updated: {updates}")

        return {"status": "updated", "changes": str(updates)}

    @router.post("/kill-switch/activate")
    async def activate_kill_switch() -> dict[str, str]:
        """Activate kill switch - cancel all orders and stop trading."""
        if not controller:
            raise HTTPException(status_code=503, detail="Controller not available")

        await controller.activate_kill_switch()
        logger.warning("Kill switch activated via API")
        return {"status": "kill_switch_activated"}

    @router.post("/kill-switch/deactivate")
    async def deactivate_kill_switch() -> dict[str, str]:
        """Deactivate kill switch - resume trading."""
        if not controller:
            raise HTTPException(status_code=503, detail="Controller not available")

        controller.deactivate_kill_switch()
        logger.info("Kill switch deactivated via API")
        return {"status": "kill_switch_deactivated"}

    return router


def create_app(
    controller: TradingController | None = None,
    state_store: StateStore | None = None,
    mode: str = "paper",
) -> Any:
    """Create FastAPI application.

    Args:
        controller: Trading controller
        state_store: State store
        mode: Trading mode

    Returns:
        FastAPI application
    """
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware

    app = FastAPI(
        title="Market Maker Monitoring API",
        description="API for monitoring and controlling the market maker",
        version="1.0.0",
    )

    # Add CORS middleware for web dashboard
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Add monitoring router
    router = create_monitoring_router(
        controller=controller,
        state_store=state_store,
        mode=mode,
    )
    app.include_router(router)

    # Serve dashboard
    dashboard_path = Path(__file__).parent.parent / "dashboard" / "index.html"

    @app.get("/", response_class=HTMLResponse)
    async def serve_dashboard() -> FileResponse:
        """Serve the web dashboard."""
        if dashboard_path.exists():
            return FileResponse(dashboard_path, media_type="text/html")
        return HTMLResponse(
            content="<h1>Dashboard not found</h1><p>Looking for: {}</p>".format(
                dashboard_path
            ),
            status_code=404,
        )

    return app
