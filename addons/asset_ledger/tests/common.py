import unittest

from odoo import fields


def create_test_template(env, asset_kind=None, **vals):
    has_publish_date = ensure_publish_date_field(env)
    if asset_kind:
        vals["asset_kind_id"] = env.ref(f"resource.kind_{asset_kind}").id
    vals.setdefault("name", "Test Product")
    if vals.get("tracking", "none") != "none":
        vals.setdefault("is_storable", True)
    if has_publish_date:
        vals.setdefault("publish_date", fields.Datetime.now())
    return env["product.template"].create(vals)


def flush_tracking(env):
    env.flush_all()
    env.cr.precommit.run()


def create_test_product(env, asset_kind=None, **vals):
    template = create_test_template(env, asset_kind=asset_kind, **vals)
    return template.product_variant_ids[:1]


def ensure_publish_date_field(env):
    env.cr.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'product_template' AND column_name = 'publish_date'"
    )
    has_column = bool(env.cr.fetchone())
    has_publish_date = "publish_date" in env["product.template"]._fields
    if has_column and not has_publish_date:
        raise unittest.SkipTest(
            "publish_date NOT NULL constraint without website_sale loaded"
        )
    return has_publish_date
