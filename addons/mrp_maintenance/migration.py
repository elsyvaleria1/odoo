"""Import legacy equipment composition without inventing owning identities."""

from odoo.db.schema import column_exists, table_exists


def migrate_equipment_resources(env):
    cr = env.cr
    if not table_exists(cr, "maintenance_equipment") or not all(
        column_exists(cr, "maintenance_equipment", column)
        for column in ("asset_id", "workcenter_id")
    ):
        return
    env.flush_all()
    cr.execute("""
        SELECT DISTINCT workcenter.resource_id, thing.id
          FROM maintenance_equipment equipment
          LEFT JOIN mrp_workcenter workcenter ON workcenter.id = equipment.workcenter_id
          LEFT JOIN resource_resource thing ON thing.id = equipment.asset_id
         WHERE equipment.asset_id IS NOT NULL AND equipment.workcenter_id IS NOT NULL
    """)
    pairs = cr.fetchall()
    if any(not parent or not member for parent, member in pairs):
        raise ValueError(
            "Equipment composition migration: missing work center or asset identity"
        )
    relations = env["resource.relation"].with_context(active_test=False)
    parents_by_member = {}
    for parent, member in pairs:
        if parent != member:
            parents_by_member.setdefault(member, set()).add(parent)
    contained = set(
        relations.search(
            [
                ("member_id", "in", list(parents_by_member)),
                ("relation_type", "=", "contains"),
            ]
        ).member_id.ids
    )
    for member, parents in parents_by_member.items():
        if len(parents) > 1 and member not in contained:
            raise ValueError(
                "Equipment composition migration: conflicting work center membership"
            )
    for parent, member in sorted(set(pairs)):
        if parent == member:
            continue
        if member in contained:
            continue
        relations.create(
            {"parent_id": parent, "member_id": member, "date_start": False}
        )
