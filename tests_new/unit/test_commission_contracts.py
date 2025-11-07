"""Contract tests for commission calculation logic.

These tests define the expected behavior of the commission calculation
system and serve as regression tests for critical business logic.
"""

from decimal import Decimal

from app.bot.utils import calculate_final_price


class TestCommissionContracts:
    """Test the commission calculation contracts."""

    def test_commission_calculation_contract(self, commission_test_cases, mock_config):
        """Test that commission calculation follows the defined contract."""
        for (
            item_price,
            us_shipping,
            expected_commission,
            _commission_type,
            description,
        ) in commission_test_cases:
            # Arrange
            item_price_decimal = Decimal(str(item_price))
            us_shipping_decimal = Decimal(str(us_shipping))
            ru_shipping_decimal = Decimal("25.00")  # Standard Russia shipping

            # Act
            result = calculate_final_price(
                item_price_decimal, us_shipping_decimal, ru_shipping_decimal
            )

            # Assert
            assert result.commission == Decimal(str(expected_commission)), (
                f"Commission calculation failed for case: {description}\n"
                f"Input: item=${item_price}, us_shipping=${us_shipping}\n"
                f"Expected commission: ${expected_commission}\n"
                f"Actual commission: ${result.commission}\n"
                f"Commission base: ${item_price + us_shipping}"
            )

            # Verify structured breakdown consistency
            expected_subtotal = (
                item_price_decimal + us_shipping_decimal + result.commission
            ).quantize(Decimal("0.01"))
            assert (
                result.subtotal == expected_subtotal
            ), f"Subtotal mismatch for case: {description}"
            assert result.shipping_russia == ru_shipping_decimal
            assert result.additional_costs == (result.customs_duty + ru_shipping_decimal).quantize(
                Decimal("0.01")
            )
            assert result.final_price_usd == (result.subtotal + result.additional_costs).quantize(
                Decimal("0.01")
            ), f"Total price calculation inconsistent for case: {description}"

    def test_commission_threshold_boundary(self, mock_config):
        """Test commission calculation at the $150 threshold boundary."""
        # Test cases around the threshold
        boundary_cases = [
            # (item_price, us_shipping, expected_commission, description)
            (149.99, 0.00, 15.00, "Just below threshold, no shipping"),
            (150.00, 0.00, 15.00, "Exactly at threshold, no shipping"),
            (150.01, 0.00, 15.00, "Just above threshold, no shipping"),
            (100.00, 49.99, 15.00, "Below threshold with shipping pushing close"),
            (100.00, 50.00, 15.00, "Exactly at threshold with shipping"),
            (100.00, 50.01, 15.00, "Above threshold due to shipping"),
            (0.01, 149.99, 15.00, "Minimal item, max shipping at threshold"),
            (0.01, 150.00, 15.00, "Minimal item, shipping above threshold"),
        ]

        for item_price, us_shipping, expected_commission, description in boundary_cases:
            result = calculate_final_price(
                Decimal(str(item_price)), Decimal(str(us_shipping)), Decimal("25.00")
            )

            commission_base = item_price + us_shipping
            expected_type = "fixed" if commission_base < 150 else "percentage"

            if expected_type == "percentage":
                expected_commission = commission_base * 0.10

            assert result.commission == Decimal(str(expected_commission)).quantize(
                Decimal("0.01")
            ), (
                f"Boundary test failed: {description}\n"
                f"Commission base: ${commission_base}\n"
                f"Expected: ${expected_commission}, Got: ${result.commission}"
            )

    def test_commission_calculation_precision(self, mock_config):
        """Test that commission calculations maintain proper decimal precision."""
        test_cases = [
            # Cases that might have precision issues
            (166.67, 33.33, Decimal("20.00")),  # 200.00 * 0.10 = 20.00
            (123.45, 67.89, Decimal("19.13")),  # 191.34 * 0.10 = 19.13 (rounded)
            (99.99, 0.01, Decimal("10.00")),  # 100.00 * 0.10 = 10.00
        ]

        for item_price, us_shipping, expected_commission in test_cases:
            result = calculate_final_price(
                Decimal(str(item_price)), Decimal(str(us_shipping)), Decimal("25.00")
            )

            assert result.commission == expected_commission, (
                f"Precision test failed for ${item_price} + ${us_shipping}\n"
                f"Expected: ${expected_commission}, Got: ${result.commission}"
            )

    def test_commission_zero_values(self, mock_config):
        """Test commission calculation with zero values."""
        # Test with zero item price
        result = calculate_final_price(Decimal("0.00"), Decimal("100.00"), Decimal("25.00"))
        assert result.commission == Decimal("15.00"), "Zero item price should use fixed commission"

        # Test with zero shipping
        result = calculate_final_price(Decimal("200.00"), Decimal("0.00"), Decimal("25.00"))
        assert result.commission == Decimal(
            "20.00"
        ), "Zero shipping should calculate on item price only"

        # Test with both zero (edge case)
        result = calculate_final_price(Decimal("0.00"), Decimal("0.00"), Decimal("25.00"))
        assert result.commission == Decimal("15.00"), "Zero values should use fixed commission"

    def test_commission_large_values(self, mock_config):
        """Test commission calculation with large values."""
        # Test very large values
        result = calculate_final_price(Decimal("9999.99"), Decimal("999.99"), Decimal("25.00"))

        expected_commission = (Decimal("9999.99") + Decimal("999.99")) * Decimal("0.10")
        assert result.commission == expected_commission.quantize(Decimal("0.01"))

        # Verify total doesn't overflow
        assert result.final_price_usd > Decimal("0")
        assert str(result.final_price_usd).count(".") == 1  # Proper decimal format

    def test_price_calculation_model_fields(self, mock_config):
        """Test that PriceCalculation model fields are correctly populated."""
        result = calculate_final_price(Decimal("100.00"), Decimal("15.00"), Decimal("20.00"))

        # Verify all fields are set
        assert result.item_price == Decimal("100.00")
        assert result.shipping_us == Decimal("15.00")
        assert result.shipping_russia == Decimal("20.00")
        assert result.total_cost == Decimal("135.00")  # 100 + 15 + 20
        assert result.commission == Decimal("11.50")  # (100 + 15) * 0.10
        assert result.subtotal == Decimal("126.50")  # 100 + 15 + 11.50
        assert result.additional_costs == (result.customs_duty + Decimal("20.00")).quantize(
            Decimal("0.01")
        )
        assert result.final_price_usd == (result.subtotal + result.additional_costs).quantize(
            Decimal("0.01")
        )

        # Optional fields should be None by default
        assert result.final_price_rub is None
        assert result.exchange_rate is None
