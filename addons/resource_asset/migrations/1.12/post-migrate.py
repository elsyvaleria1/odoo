from odoo import SUPERUSER_ID, api, fields
from odoo.db import schema
from odoo.tools import SQL

from odoo.addons.resource_asset.table_inheritance import _tables_of_tree


def migrate(cr, version):
    if not version or not schema.column_exists(
        cr, "resource_asset", "legacy_parent_id"
    ):
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    Relation = env["resource.relation"]
    cr.execute("""
        SELECT child.id, child.resource_id, parent.resource_id
          FROM resource_asset child
          LEFT JOIN resource_asset parent ON parent.id = child.legacy_parent_id
         WHERE child.legacy_parent_id IS NOT NULL ORDER BY child.id
    """)
    links = cr.fetchall()
    values = []
    at = fields.Datetime.now()
    for asset_id, member_id, parent_id in links:
        if not parent_id:
            raise ValueError(
                f"Asset composition migration: missing parent of asset {asset_id}"
            )
        history = Relation.search(
            [
                ("member_id", "=", member_id),
                ("relation_type", "=", "contains"),
            ]
        )
        if history:
            current = history.filtered(
                lambda row: (
                    (not row.date_start or row.date_start <= at)
                    and (not row.date_end or row.date_end > at)
                )
            )
            if len(current) != 1 or current.parent_id.id != parent_id:
                raise ValueError(
                    f"Asset composition migration: resource history conflicts with asset {asset_id}; reconcile the membership before upgrading"
                )
            continue
        values.append(
            {
                "parent_id": parent_id,
                "member_id": member_id,
                "relation_type": "contains",
                "date_start": False,
            }
        )
    if values:
        Relation.create(values)
    # Physical subtypes may retain local copies of an inherited column.
    for table in _tables_of_tree(cr):
        if schema.column_exists(cr, table, "legacy_parent_id"):
            cr.execute(
                SQL(
                    "ALTER TABLE %s DROP COLUMN legacy_parent_id", SQL.identifier(table)
                )
            )
