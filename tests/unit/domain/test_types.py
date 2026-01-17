"""Tests for domain value objects: Price, Quantity, Side, OrderSide."""

from decimal import Decimal

import pytest

from market_maker.domain.types import OrderSide, Price, Quantity, Side


class TestPrice:
    """Tests for Price value object."""

    def test_create_valid_price(self) -> None:
        """Price accepts valid values between 0.01 and 0.99."""
        price = Price(Decimal("0.50"))
        assert price.value == Decimal("0.50")

    def test_create_price_at_minimum(self) -> None:
        """Price accepts minimum value 0.01."""
        price = Price(Decimal("0.01"))
        assert price.value == Decimal("0.01")

    def test_create_price_at_maximum(self) -> None:
        """Price accepts maximum value 0.99."""
        price = Price(Decimal("0.99"))
        assert price.value == Decimal("0.99")

    def test_create_price_below_minimum_raises(self) -> None:
        """Price rejects values below 0.01."""
        with pytest.raises(ValueError, match="Price must be between 0.01 and 0.99"):
            Price(Decimal("0.00"))

    def test_create_price_above_maximum_raises(self) -> None:
        """Price rejects values above 0.99."""
        with pytest.raises(ValueError, match="Price must be between 0.01 and 0.99"):
            Price(Decimal("1.00"))

    def test_create_price_negative_raises(self) -> None:
        """Price rejects negative values."""
        with pytest.raises(ValueError, match="Price must be between 0.01 and 0.99"):
            Price(Decimal("-0.50"))

    def test_as_cents(self) -> None:
        """Price converts to cents correctly."""
        price = Price(Decimal("0.45"))
        assert price.as_cents() == 45

    def test_as_cents_rounds_correctly(self) -> None:
        """Price converts to cents with rounding."""
        price = Price(Decimal("0.455"))
        assert price.as_cents() == 46  # Rounds to nearest

    def test_as_probability(self) -> None:
        """Price returns value as probability (same as value for binary contracts)."""
        price = Price(Decimal("0.65"))
        assert price.as_probability() == Decimal("0.65")

    def test_from_cents(self) -> None:
        """Price can be created from cents."""
        price = Price.from_cents(45)
        assert price.value == Decimal("0.45")

    def test_from_cents_minimum(self) -> None:
        """Price from cents at minimum."""
        price = Price.from_cents(1)
        assert price.value == Decimal("0.01")

    def test_from_cents_maximum(self) -> None:
        """Price from cents at maximum."""
        price = Price.from_cents(99)
        assert price.value == Decimal("0.99")

    def test_from_cents_zero_raises(self) -> None:
        """Price from cents rejects zero."""
        with pytest.raises(ValueError, match="Price must be between 0.01 and 0.99"):
            Price.from_cents(0)

    def test_from_cents_over_99_raises(self) -> None:
        """Price from cents rejects > 99."""
        with pytest.raises(ValueError, match="Price must be between 0.01 and 0.99"):
            Price.from_cents(100)

    def test_price_is_immutable(self) -> None:
        """Price should be immutable (frozen)."""
        price = Price(Decimal("0.50"))
        with pytest.raises((AttributeError, TypeError)):
            price.value = Decimal("0.60")  # type: ignore[misc]

    def test_price_equality(self) -> None:
        """Prices with same value are equal."""
        p1 = Price(Decimal("0.50"))
        p2 = Price(Decimal("0.50"))
        assert p1 == p2

    def test_price_hash(self) -> None:
        """Prices with same value have same hash."""
        p1 = Price(Decimal("0.50"))
        p2 = Price(Decimal("0.50"))
        assert hash(p1) == hash(p2)

    def test_price_repr(self) -> None:
        """Price has useful string representation."""
        price = Price(Decimal("0.50"))
        assert "0.50" in repr(price)

    def test_complement(self) -> None:
        """Price complement returns 1 - price (for YES/NO conversion)."""
        price = Price(Decimal("0.45"))
        complement = price.complement()
        assert complement.value == Decimal("0.55")

    def test_complement_at_boundary(self) -> None:
        """Price complement works at boundary values."""
        price = Price(Decimal("0.01"))
        complement = price.complement()
        assert complement.value == Decimal("0.99")


class TestQuantity:
    """Tests for Quantity value object."""

    def test_create_valid_quantity(self) -> None:
        """Quantity accepts positive integers."""
        qty = Quantity(100)
        assert qty.value == 100

    def test_create_quantity_of_one(self) -> None:
        """Quantity accepts minimum value 1."""
        qty = Quantity(1)
        assert qty.value == 1

    def test_create_zero_quantity_raises(self) -> None:
        """Quantity rejects zero."""
        with pytest.raises(ValueError, match="Quantity must be positive"):
            Quantity(0)

    def test_create_negative_quantity_raises(self) -> None:
        """Quantity rejects negative values."""
        with pytest.raises(ValueError, match="Quantity must be positive"):
            Quantity(-10)

    def test_quantity_is_immutable(self) -> None:
        """Quantity should be immutable (frozen)."""
        qty = Quantity(100)
        with pytest.raises((AttributeError, TypeError)):
            qty.value = 200  # type: ignore[misc]

    def test_quantity_equality(self) -> None:
        """Quantities with same value are equal."""
        q1 = Quantity(100)
        q2 = Quantity(100)
        assert q1 == q2

    def test_quantity_hash(self) -> None:
        """Quantities with same value have same hash."""
        q1 = Quantity(100)
        q2 = Quantity(100)
        assert hash(q1) == hash(q2)

    def test_quantity_repr(self) -> None:
        """Quantity has useful string representation."""
        qty = Quantity(100)
        assert "100" in repr(qty)


class TestSide:
    """Tests for Side enum."""

    def test_side_yes(self) -> None:
        """Side has YES value."""
        assert Side.YES.value == "yes"

    def test_side_no(self) -> None:
        """Side has NO value."""
        assert Side.NO.value == "no"

    def test_side_opposite_yes(self) -> None:
        """YES opposite is NO."""
        assert Side.YES.opposite() == Side.NO

    def test_side_opposite_no(self) -> None:
        """NO opposite is YES."""
        assert Side.NO.opposite() == Side.YES


class TestOrderSide:
    """Tests for OrderSide enum."""

    def test_order_side_buy(self) -> None:
        """OrderSide has BUY value."""
        assert OrderSide.BUY.value == "buy"

    def test_order_side_sell(self) -> None:
        """OrderSide has SELL value."""
        assert OrderSide.SELL.value == "sell"

    def test_order_side_opposite_buy(self) -> None:
        """BUY opposite is SELL."""
        assert OrderSide.BUY.opposite() == OrderSide.SELL

    def test_order_side_opposite_sell(self) -> None:
        """SELL opposite is BUY."""
        assert OrderSide.SELL.opposite() == OrderSide.BUY
