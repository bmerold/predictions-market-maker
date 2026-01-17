"""Tests for domain error types."""


from market_maker.domain.errors import (
    ConfigurationError,
    ExchangeError,
    InsufficientBalanceError,
    OrderError,
    OrderNotFoundError,
    OrderRejectedError,
    RiskViolation,
    StaleDataError,
    TradingError,
)


class TestTradingError:
    """Tests for base TradingError."""

    def test_trading_error_is_exception(self) -> None:
        """TradingError inherits from Exception."""
        error = TradingError("Something went wrong")
        assert isinstance(error, Exception)

    def test_trading_error_message(self) -> None:
        """TradingError stores message."""
        error = TradingError("Test message")
        assert str(error) == "Test message"

    def test_trading_error_with_context(self) -> None:
        """TradingError can include context dictionary."""
        error = TradingError("Failed operation", context={"order_id": "123"})
        assert error.context == {"order_id": "123"}

    def test_trading_error_default_context(self) -> None:
        """TradingError has empty context by default."""
        error = TradingError("Test")
        assert error.context == {}


class TestExchangeError:
    """Tests for ExchangeError."""

    def test_exchange_error_is_trading_error(self) -> None:
        """ExchangeError inherits from TradingError."""
        error = ExchangeError("Exchange unavailable")
        assert isinstance(error, TradingError)

    def test_exchange_error_with_exchange_name(self) -> None:
        """ExchangeError stores exchange name."""
        error = ExchangeError("Connection failed", exchange="kalshi")
        assert error.exchange == "kalshi"

    def test_exchange_error_default_exchange(self) -> None:
        """ExchangeError has None exchange by default."""
        error = ExchangeError("Test")
        assert error.exchange is None


class TestOrderError:
    """Tests for order-related errors."""

    def test_order_error_is_trading_error(self) -> None:
        """OrderError inherits from TradingError."""
        error = OrderError("Order failed")
        assert isinstance(error, TradingError)

    def test_order_error_with_order_id(self) -> None:
        """OrderError stores order_id."""
        error = OrderError("Order failed", order_id="ord_123")
        assert error.order_id == "ord_123"

    def test_order_not_found_error(self) -> None:
        """OrderNotFoundError is specific order error."""
        error = OrderNotFoundError(order_id="ord_123")
        assert isinstance(error, OrderError)
        assert error.order_id == "ord_123"
        assert "ord_123" in str(error)

    def test_order_rejected_error(self) -> None:
        """OrderRejectedError stores reason."""
        error = OrderRejectedError("Price invalid", order_id="ord_123", reason="BAD_PRICE")
        assert isinstance(error, OrderError)
        assert error.reason == "BAD_PRICE"


class TestRiskViolation:
    """Tests for RiskViolation error."""

    def test_risk_violation_is_trading_error(self) -> None:
        """RiskViolation inherits from TradingError."""
        error = RiskViolation("Position limit exceeded")
        assert isinstance(error, TradingError)

    def test_risk_violation_with_rule_name(self) -> None:
        """RiskViolation stores rule name."""
        error = RiskViolation("Limit exceeded", rule_name="max_position")
        assert error.rule_name == "max_position"

    def test_risk_violation_with_details(self) -> None:
        """RiskViolation can include limit and actual values."""
        error = RiskViolation(
            "Position limit exceeded",
            rule_name="max_position",
            limit_value=1000,
            actual_value=1500,
        )
        assert error.limit_value == 1000
        assert error.actual_value == 1500


class TestStaleDataError:
    """Tests for StaleDataError."""

    def test_stale_data_error_is_trading_error(self) -> None:
        """StaleDataError inherits from TradingError."""
        error = StaleDataError("Market data stale")
        assert isinstance(error, TradingError)

    def test_stale_data_error_with_age(self) -> None:
        """StaleDataError stores data age."""
        error = StaleDataError("Market data stale", age_seconds=30.5, max_age_seconds=5.0)
        assert error.age_seconds == 30.5
        assert error.max_age_seconds == 5.0


class TestInsufficientBalanceError:
    """Tests for InsufficientBalanceError."""

    def test_insufficient_balance_is_trading_error(self) -> None:
        """InsufficientBalanceError inherits from TradingError."""
        error = InsufficientBalanceError("Not enough funds")
        assert isinstance(error, TradingError)

    def test_insufficient_balance_with_amounts(self) -> None:
        """InsufficientBalanceError stores required and available amounts."""
        error = InsufficientBalanceError(
            "Not enough funds",
            required=100.0,
            available=50.0,
        )
        assert error.required == 100.0
        assert error.available == 50.0


class TestConfigurationError:
    """Tests for ConfigurationError."""

    def test_configuration_error_is_trading_error(self) -> None:
        """ConfigurationError inherits from TradingError."""
        error = ConfigurationError("Invalid config")
        assert isinstance(error, TradingError)

    def test_configuration_error_with_field(self) -> None:
        """ConfigurationError stores field name."""
        error = ConfigurationError("Invalid value", field="max_position")
        assert error.field == "max_position"
