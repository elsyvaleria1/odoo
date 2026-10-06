def archive_maintenance_approval_categories(env) -> None:
    env["approval.category"].sudo().search(
        [("approval_type", "in", ("maintenance_preventive", "maintenance_corrective"))]
    ).active = False
