from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    Template = env["product.template"]
    folded = Template.with_context(active_test=False).search(
        [("specification_line_ids", "!=", False)]
    )
    env.add_to_compute(Template._fields["has_configurable_attributes"], folded)
    env.flush_all()
