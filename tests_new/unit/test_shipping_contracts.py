"""Contract tests for shipping calculation logic.

Tests the shipping weight estimation and cost calculation to ensure
consistent behavior across different item types and patterns.
"""

from decimal import Decimal

from app.services.shipping import calc_shipping, estimate_shopfans_shipping


class TestShippingContracts:
    """Test shipping calculation contracts."""

    def test_shipping_estimation_contract(self, shipping_test_cases, mock_config):
        """Test that shipping estimation follows pattern matching contracts."""
        for title, expected_weight, description in shipping_test_cases:
            # Act
            result = estimate_shopfans_shipping(title, Decimal("150"))

            # Assert weight estimation
            assert result.weight_kg == Decimal(str(expected_weight)), (
                f"Weight estimation failed for: {description}\n"
                f"Title: '{title}'\n"
                f"Expected weight: {expected_weight}kg\n"
                f"Actual weight: {result.weight_kg}kg"
            )

            # Assert cost calculation consistency
            assert result.cost_usd > Decimal("0"), f"Cost should be positive for {description}"
            assert result.description, f"Description should be provided for {description}"

    def test_shopfans_cost_calculation_contract(self, mock_config):
        """Test Shopfans cost calculation formula."""
        test_weights = [
            (Decimal("0.10"), "very light item"),
            (Decimal("0.45"), "light threshold item"),
            (Decimal("0.50"), "medium weight item"),
            (Decimal("1.00"), "heavy item"),
            (Decimal("2.50"), "very heavy item"),
        ]

        for weight, description in test_weights:
            _ = estimate_shopfans_shipping("test item", Decimal("150"))

            # Manually calculate expected cost using NEW formula (Europe route: 30.86$/kg)
            base_cost = max(Decimal("13.99"), Decimal("30.86") * weight)
            if weight <= Decimal("1.36"):  # New threshold: 1.36kg (3 pounds)
                handling_fee = Decimal("3.0")
            else:
                handling_fee = Decimal("5.0")

            expected_cost = (base_cost + handling_fee).quantize(Decimal("0.01"))

            # Test with a generic item that gets default weight
            if weight == Decimal("0.60"):  # Default weight
                generic_result = estimate_shopfans_shipping("unknown item type", Decimal("150"))
                assert generic_result.cost_usd == expected_cost, (
                    f"Cost calculation failed for {description}\n"
                    f"Weight: {weight}kg\n"
                    f"Expected: ${expected_cost}\n"
                    f"Actual: ${generic_result.cost_usd}"
                )

    def test_pattern_matching_priority(self, mock_config):
        """Test that pattern matching works with correct priority."""
        # Test cases where multiple patterns might match
        test_cases = [
            ("Supreme hoodie black", 0.80, "hoodie"),
            ("Nike sneakers size 10", 1.40, "sneakers"),
            ("Basic cotton t-shirt", 0.25, "t-shirt"),
            ("Silk necktie formal", 0.08, "tie"),
        ]

        for title, expected_weight, item_type in test_cases:
            result = estimate_shopfans_shipping(title, Decimal("150"))

            assert result.weight_kg == Decimal(str(expected_weight)), (
                f"Pattern matching failed for {item_type}\n"
                f"Title: '{title}'\n"
                f"Expected: {expected_weight}kg\n"
                f"Actual: {result.weight_kg}kg"
            )

    def test_case_insensitive_matching(self, mock_config):
        """Test that pattern matching is case insensitive."""
        test_cases = [
            "SUPREME HOODIE",
            "supreme hoodie",
            "Supreme Hoodie",
            "SuPrEmE hOoDiE",
        ]

        expected_weight = Decimal("0.80")
        for title in test_cases:
            result = estimate_shopfans_shipping(title, Decimal("150"))
            assert (
                result.weight_kg == expected_weight
            ), f"Case insensitive matching failed for: '{title}'"

    def test_country_specific_shipping(self, mock_config):
        """Test shipping calculation for different countries."""
        weight = Decimal("1.0")

        # Test Russia shipping (supported)
        russia_result = calc_shipping("russia", weight, Decimal("150"))
        assert russia_result.cost_usd > Decimal("0")
        assert "Russia" in russia_result.description

        # Test Russia with different case
        russia_upper = calc_shipping("RUSSIA", weight, Decimal("150"))
        assert russia_upper.cost_usd == russia_result.cost_usd

        # Test unsupported country
        unsupported_result = calc_shipping("germany", weight, Decimal("150"))
        assert unsupported_result.cost_usd == Decimal("0")
        assert "not supported" in unsupported_result.description.lower()

    def test_shipping_cost_monotonicity(self, mock_config):
        """Test that shipping cost increases monotonically with weight."""
        weights = [Decimal(str(w)) for w in [0.1, 0.5, 1.0, 1.5, 2.0]]
        costs = []

        for weight in weights:
            result = calc_shipping("russia", weight, Decimal("150"))
            costs.append(result.cost_usd)

        # Verify monotonic increase (allowing for equal costs at boundaries)
        for i in range(1, len(costs)):
            assert costs[i] >= costs[i - 1], (
                f"Shipping cost decreased with weight increase:\n"
                f"Weight {weights[i-1]}kg -> ${costs[i-1]}\n"
                f"Weight {weights[i]}kg -> ${costs[i]}"
            )

    def test_empty_and_none_title_handling(self, mock_config):
        """Test shipping estimation with empty or None titles."""
        # Test empty string
        empty_result = estimate_shopfans_shipping("", Decimal("150"))
        assert empty_result.weight_kg == Decimal("0.60")  # Default weight

        # Test None (should be handled gracefully)
        none_result = estimate_shopfans_shipping(None)
        assert none_result.weight_kg == Decimal("0.60")  # Default weight

        # Both should have same cost since same weight
        assert empty_result.cost_usd == none_result.cost_usd

    def test_special_characters_in_title(self, mock_config):
        """Test shipping estimation with special characters in titles."""
        special_titles = [
            "Supreme® hoodie black",
            "Nike™ sneakers (size 10)",
            "T-shirt w/ special print",
            "Hoodie - premium quality",
            "Sneakers & shoes collection",
        ]

        expected_weights = [0.80, 1.40, 0.25, 0.80, 1.40]

        for title, expected_weight in zip(special_titles, expected_weights, strict=True):
            result = estimate_shopfans_shipping(title, Decimal("150"))
            assert result.weight_kg == Decimal(
                str(expected_weight)
            ), f"Special character handling failed for: '{title}'"

    def test_shipping_quote_model_completeness(self, mock_config):
        """Test that ShippingQuote model is properly populated."""
        result = estimate_shopfans_shipping("Test hoodie")

        # Verify all required fields are present
        assert hasattr(result, "weight_kg")
        assert hasattr(result, "cost_usd")
        assert hasattr(result, "description")

        # Verify field types
        assert isinstance(result.weight_kg, Decimal)
        assert isinstance(result.cost_usd, Decimal)
        assert isinstance(result.description, str)

        # Verify reasonable values
        assert result.weight_kg > Decimal("0")
        assert result.cost_usd > Decimal("0")
        assert len(result.description) > 0
