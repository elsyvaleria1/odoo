from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    requests = env["approval.request"].search([("state", "=", "pending")])
    for request in requests.filtered(
        lambda request: (
            request.approver_ids.step_ids
            and not any(
                "id" in entry
                for entry in (request.category_snapshot or {}).get("steps", ())
            )
        )
    ):
        request.category_snapshot = dict(
            request.category_snapshot or {},
            steps=request._prepare_step_snapshot(
                request._sort_routed_steps(request.approver_ids.step_ids)
            ),
        )
