"""Shipping cost estimation service.

Estimates shipping costs from the US to Russia via Shopfans using a tiered
pricing system based on item value and weight. Includes handling fees for
light and heavy items and uses keyword-based weight estimation.
"""

import re
from decimal import Decimal

from ..config import Config
from ..models import ShippingQuote


class ShippingService:
    def __init__(self, config: Config):
        self.config = config

    def estimate_shopfans_shipping(
        self,
        item_title: str | None,
        order_value: Decimal | None = None
    ) -> ShippingQuote:
        """Estimate Shopfans shipping cost from US to Russia with tiered pricing.

        Implements a tiered shipping system based on order value:
        - < $200: Europe route (30.86$/kg)
        - >= $200: Turkey route (35.27$/kg)
        - >= $1000: Kazakhstan route (41.89$/kg)

        Also applies handling fees based on estimated weight:
        - <= 1.36kg: $3 handling fee
        - > 1.36kg: $5 handling fee

        Args:
            item_title: Item title for weight estimation.
            order_value: Total order value (item price + US shipping).

        Returns:
            ShippingQuote with estimated weight, cost, and description.
        """
        # Estimate weight based on item title
        weight_kg = self._estimate_weight(item_title)

        if order_value is None:
            order_value = Decimal("0")
        else:
            order_value = self._to_decimal(order_value, order_value)

        shipping_params = self._resolve_shipping_params()

        # Select shipping route based on order value
        if order_value >= shipping_params["kazakhstan_threshold"]:
            per_kg_rate = shipping_params["per_kg_rate_kazakhstan"]
            route_name = "Kazakhstan"
        elif order_value >= shipping_params["turkey_threshold"]:
            per_kg_rate = shipping_params["per_kg_rate_turkey"]
            route_name = "Turkey"
        else:
            per_kg_rate = shipping_params["per_kg_rate_europe"]
            route_name = "Europe"

        # Calculate base shipping cost
        base_shipping_cost = max(
            shipping_params["base_cost"],
            per_kg_rate * weight_kg
        )

        # Add handling fee based on weight
        if weight_kg <= shipping_params["light_threshold"]:
            handling_fee = shipping_params["light_handling_fee"]
        else:
            handling_fee = shipping_params["heavy_handling_fee"]

        total_cost = (base_shipping_cost + handling_fee).quantize(Decimal('0.01'))

        description = (
            f"Shopfans ({route_name} route): "
            f"base ${base_shipping_cost:.2f} + handling ${handling_fee:.2f}"
        )

        return ShippingQuote(
            weight_kg=weight_kg,
            cost_usd=total_cost,
            description=description
        )

    def _estimate_weight(self, item_title: str | None) -> Decimal:
        """Estimate item weight in kg based on keywords in title.

        Uses a predefined list of patterns and associated weights from the
        shipping_table.yml configuration file.

        Args:
            item_title: Item title to analyze.

        Returns:
            Estimated weight in kilograms as a Decimal.
        """
        title_lower = (item_title or "").lower()

        for item in self.config.shipping_patterns:
            pattern = item.get('pattern')
            weight = item.get('weight')

            if pattern and weight is not None:
                try:
                    if re.search(r'\b' + pattern + r'\b', title_lower):
                        return Decimal(str(weight))
                except re.error:
                    # Handle invalid regex patterns in config
                    continue

        # Return default weight if no pattern matches
        default_weight = getattr(self.config, "default_shipping_weight", 0.60)
        return self._to_decimal(default_weight, Decimal("0.60"))

    def _resolve_shipping_params(self) -> dict[str, Decimal]:
        """Resolve shipping configuration with sensible fallbacks."""
        shipping_conf = getattr(self.config, "shipping", None)

        def value(name: str, default: float) -> Decimal:
            raw = getattr(shipping_conf, name, None) if shipping_conf else None
            return self._to_decimal(raw, Decimal(str(default)))

        per_kg_rate = value("per_kg_rate", 30.86)

        params = {
            "base_cost": value("base_cost", 13.99),
            "per_kg_rate_europe": value("per_kg_rate_europe", per_kg_rate),
            "per_kg_rate_turkey": value("per_kg_rate_turkey", per_kg_rate + Decimal("4.41")),
            "per_kg_rate_kazakhstan": value("per_kg_rate_kazakhstan", per_kg_rate + Decimal("11.03")),
            "turkey_threshold": value("turkey_threshold", 200.0),
            "kazakhstan_threshold": value("kazakhstan_threshold", 1000.0),
            "light_threshold": value("light_threshold", 1.36),
            "light_handling_fee": value("light_handling_fee", 3.0),
            "heavy_handling_fee": value("heavy_handling_fee", 5.0),
        }

        # Ensure turkey/kazakhstan rates not lower than Europe
        params["per_kg_rate_turkey"] = max(params["per_kg_rate_turkey"], params["per_kg_rate_europe"])
        params["per_kg_rate_kazakhstan"] = max(
            params["per_kg_rate_kazakhstan"],
            params["per_kg_rate_turkey"]
        )

        return params

    def _to_decimal(self, value: object, default: Decimal | float) -> Decimal:
        """Convert arbitrary value to Decimal with fallback."""
        if isinstance(value, Decimal):
            return value
        if value is None:
            return Decimal(str(default))

        try:
            return Decimal(str(value))
        except Exception:
            return Decimal(str(default))


_shipping_service: ShippingService | None = None


def get_shipping_service(config: Config | None = None) -> ShippingService:
    """Получить ленивый экземпляр сервиса доставки."""
    global _shipping_service
    if config is None:
        from ..config import config as global_config
        config = global_config

    if _shipping_service is None or _shipping_service.config is not config:
        _shipping_service = ShippingService(config)
    return _shipping_service


def estimate_shopfans_shipping(
    item_title: str | None,
    order_value: Decimal | None = None
) -> ShippingQuote:
    """Функциональная обёртка для обратной совместимости с прежним API."""
    service = get_shipping_service()
    return service.estimate_shopfans_shipping(item_title, order_value)


def calc_shipping(
    country: str,
    weight_kg: Decimal,
    order_value: Decimal | None = None
) -> ShippingQuote:
    """Рассчитать доставку в указанную страну (совместимость со старым API)."""
    normalized_country = (country or "").strip().lower()
    weight = Decimal(str(weight_kg))

    if order_value is None:
        order_value = Decimal("0")

    if normalized_country not in {"russia", "ru", "rus"}:
        return ShippingQuote(
            weight_kg=weight,
            cost_usd=Decimal("0"),
            description=f"Shipping to {country or 'unknown'} is not supported"
        )

    service = get_shipping_service()
    shipping_params = service._resolve_shipping_params()

    # Определяем маршрут по стоимости заказа
    if order_value >= shipping_params["kazakhstan_threshold"]:
        per_kg_rate = shipping_params["per_kg_rate_kazakhstan"]
        route_name = "Kazakhstan"
    elif order_value >= shipping_params["turkey_threshold"]:
        per_kg_rate = shipping_params["per_kg_rate_turkey"]
        route_name = "Turkey"
    else:
        per_kg_rate = shipping_params["per_kg_rate_europe"]
        route_name = "Europe"

    base_cost = max(
        shipping_params["base_cost"],
        per_kg_rate * weight
    )

    if weight <= shipping_params["light_threshold"]:
        handling_fee = shipping_params["light_handling_fee"]
    else:
        handling_fee = shipping_params["heavy_handling_fee"]

    total_cost = (base_cost + handling_fee).quantize(Decimal("0.01"))
    description = (
        f"Russia shipping ({route_name} route): "
        f"base ${base_cost:.2f} + handling ${handling_fee:.2f}"
    )

    return ShippingQuote(
        weight_kg=weight,
        cost_usd=total_cost,
        description=description
    )
