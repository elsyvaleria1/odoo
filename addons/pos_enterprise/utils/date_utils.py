from odoo import fields


def compute_seconds_since(start_time):
    return (fields.Datetime.now() - start_time).total_seconds()
