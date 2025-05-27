from decimal import Decimal, ROUND_HALF_UP
import re

_SHIPPING_TABLE = {
    # TOPS
    r"long sleeve t-?shirt|longsleeve":        (Decimal("0.30"),),
    r"short sleeve t-?shirt|t-?shirt|tee":     (Decimal("0.20"),),
    r"polo":                                   (Decimal("0.25"),),
    r"shirt|button.?up|button.?down|oxford":   (Decimal("0.35"),),
    r"sweater|knit|cardigan":                  (Decimal("0.60"),),
    r"sweatshirt|hoodie":                      (Decimal("0.70"),),
    r"tank top|sleeveless|singlet":            (Decimal("0.18"),),
    r"jersey":                                 (Decimal("0.30"),),
    # BOTTOMS
    r"casual pants|pants|trousers":            (Decimal("0.60"),),
    r"cropped pants|cropped trousers":         (Decimal("0.55"),),
    r"denim|jeans":                            (Decimal("0.70"),),
    r"leggings":                               (Decimal("0.25"),),
    r"overalls|jumpsuit|romper":               (Decimal("0.60"),),
    r"shorts":                                 (Decimal("0.30"),),
    r"sweatpants|joggers":                     (Decimal("0.65"),),
    r"swimwear|swim trunk":                    (Decimal("0.15"),),
    # OUTERWEAR
    r"bomber( jacket)?":                       (Decimal("0.90"),),
    r"cloak|cape":                             (Decimal("1.00"),),
    r"denim jacket":                           (Decimal("1.00"),),
    r"heavy coat|overcoat|wool coat":          (Decimal("1.30"),),
    r"leather jacket":                         (Decimal("1.50"),),
    r"light jacket|windbreaker":               (Decimal("0.80"),),
    r"parka":                                  (Decimal("1.40"),),
    r"raincoat|trench coat":                   (Decimal("1.10"),),
    r"vest":                                   (Decimal("0.40"),),
    # FOOTWEAR
    r"boots":                                  (Decimal("1.80"),),
    r"casual leather shoe|loafers":            (Decimal("1.10"),),
    r"formal shoe|dress shoes|oxford":         (Decimal("1.20"),),
    r"hi[- ]?top sneaker|high[- ]?top":        (Decimal("1.60"),),
    r"low[- ]?top sneaker":                    (Decimal("1.30"),),
    r"sneakers|running shoes":                 (Decimal("1.40"),),
    r"sandals":                                (Decimal("0.50"),),
    r"slip.?on|slides":                        (Decimal("0.90"),),
    # ACCESSORIES
    r"bag|backpack|tote|duffle|weekender|messenger bag|briefcase|"
    r"crossbody|shoulder bag|belt bag|fanny pack|camera bag|laptop bag":
                                                (Decimal("0.70"),),
    r"luggage|suitcase":                       (Decimal("3.00"),),
    r"belt":                                   (Decimal("0.25"),),
    r"glasses|eyeglasses|sunglass":            (Decimal("0.10"),),
    r"gloves|mittens":                         (Decimal("0.12"),),
    r"scarf|scarves":                          (Decimal("0.20"),),
    r"hat|cap|beanie":                         (Decimal("0.15"),),
    r"jewelry|ring|bracelet|necklace|watch":   (Decimal("0.15"),),
    r"wallet":                                 (Decimal("0.15"),),
    r"socks":                                  (Decimal("0.05"),),
    r"underwear|boxers|briefs":                (Decimal("0.10"),),
    r"tie|necktie|bow tie|pocket square":      (Decimal("0.08"),),
    # TAILORING
    r"blazer|sport coat":                      (Decimal("0.80"),),
    r"formal shirt|formal shirting":           (Decimal("0.35"),),
    r"formal trousers":                        (Decimal("0.65"),),
    r"suit(?!case)|suit jacket":               (Decimal("1.20"),),
    r"tuxedo":                                 (Decimal("2.50"),),
    r"waistcoat|formal vest":                  (Decimal("0.40"),),
}

_DEFAULT_WEIGHT = Decimal("0.60")  # если ничего не сматчилось

def _calc_shopfans_price(weight: Decimal) -> Decimal:
    base = max(Decimal("13.99"), Decimal("14") * weight)
    handling = Decimal("3") if weight <= Decimal("0.45") else Decimal("5")
    return (base + handling).quantize(Decimal("0.01"), ROUND_HALF_UP)

def estimate_shopfans_shipping(title: str) -> Decimal:
    title_lc = title.lower()
    for pattern, (wt,) in _SHIPPING_TABLE.items():
        if re.search(pattern, title_lc):
            return _calc_shopfans_price(wt)
    return _calc_shopfans_price(_DEFAULT_WEIGHT)