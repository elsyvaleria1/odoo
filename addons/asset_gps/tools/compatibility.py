from odoo import Command


def register_legacy_gps_privileges(env):
    """Retain old XML IDs while moving their policy to the shared privilege."""
    group = env.ref("device_gps.privilege_read_resource_odometer")
    access = env.ref("device_gps.privilege_read_resource_odometer_logs")
    old_group = env.ref(
        "asset_gps.privilege_read_vehicle_gps", raise_if_not_found=False
    )
    old_access = env.ref(
        "asset_gps.privilege_read_vehicle_gps_logs", raise_if_not_found=False
    )
    if old_group and old_group != group:
        # Preserve extensions of the old policy rather than deleting their rows.
        env["ir.access"].search([("group_id", "=", old_group.id)]).write(
            {"group_id": group.id}
        )
        parents = env["res.groups"].search([("implied_ids", "in", old_group.ids)])
        parents.write(
            {"implied_ids": [Command.unlink(old_group.id), Command.link(group.id)]}
        )
        env["ir.model.data"].search(
            [("model", "=", "res.groups"), ("res_id", "=", old_group.id)]
        ).write({"res_id": group.id})
        old_group.unlink()
    if old_access and old_access != access:
        env["ir.model.data"].search(
            [("model", "=", "ir.access"), ("res_id", "=", old_access.id)]
        ).write({"res_id": access.id})
        old_access.unlink()
    env["ir.model.data"]._update_xmlids(
        [
            {
                "xml_id": "asset_gps.privilege_read_vehicle_gps",
                "record": group,
                "noupdate": True,
            },
            {
                "xml_id": "asset_gps.privilege_read_vehicle_gps_logs",
                "record": access,
                "noupdate": True,
            },
        ]
    )
