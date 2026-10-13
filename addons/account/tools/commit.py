from odoo import modules, tools


def can_commit() -> bool:
    return not (tools.config["test_enable"] or modules.module.current_test)
