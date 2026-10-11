def get_publishable_key(provider_sudo):
    return provider_sudo.stripe_publishable_key


def get_secret_key(provider_sudo):
    return provider_sudo.stripe_secret_key


def get_webhook_secret(provider_sudo):
    return provider_sudo.stripe_webhook_secret


def include_shipping_address(tx_sudo):
    tx_sudo.check_singleton()

    if "sale_order_ids" in tx_sudo._fields and tx_sudo.sale_order_ids:
        order = tx_sudo.sale_order_ids[:1]
        return format_shipping_address(order.partner_shipping_id)
    elif "invoice_ids" in tx_sudo._fields and tx_sudo.invoice_ids:
        invoice = tx_sudo.invoice_ids[:1]
        return format_shipping_address(invoice.partner_shipping_id)
    return {}


def format_shipping_address(shipping_partner):
    return {
        "shipping[address][city]": shipping_partner.city or "",
        "shipping[address][country]": shipping_partner.country_id.code or "",
        "shipping[address][line1]": shipping_partner.street or "",
        "shipping[address][line2]": shipping_partner.street2 or "",
        "shipping[address][postal_code]": shipping_partner.zip or "",
        "shipping[address][state]": shipping_partner.state_id.name or "",
        "shipping[name]": shipping_partner.name
        or shipping_partner.parent_id.name
        or "",
    }
