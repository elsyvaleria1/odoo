

def to_comparable(price, *, unit, product, currency, company, date):
    if unit and product.uom_id:
        price = unit._get_price_in_unit(price, product.uom_id, raise_if_failure=False)
    if currency:
        price = currency._convert(
            price, company.currency_id, company, date, round=False
        )
    return price


def from_comparable(price, *, unit, product, currency, company, date):
    if currency:
        price = company.currency_id._convert(
            price, currency, company, date, round=False
        )
    if unit and product.uom_id:
        price = product.uom_id._get_price_in_unit(price, unit, raise_if_failure=False)
    return price
