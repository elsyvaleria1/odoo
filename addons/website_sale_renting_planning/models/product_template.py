from collections import defaultdict
from datetime import UTC

from odoo import fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class ProductTemplate(models.Model):
    _inherit = "product.template"

    def _search_get_detail(self, website, order, options):
        search_details = super()._search_get_detail(website, order, options)
        if (
            (from_date := options.get("from_date"))
            and (to_date := options.get("to_date"))
            and (
                planning_roles := self.env["resource.role"]
                .sudo()
                .search_fetch(
                    [("sync_shift_rental", "=", True)],
                    ["resource_ids"],
                )
            )
        ):
            unavailable_resources = (
                self.env["planning.slot"]
                .sudo()
                ._read_group(
                    [
                        ("start_datetime", "<=", to_date),
                        ("end_datetime", ">=", from_date),
                        ("resource_id", "in", planning_roles.resource_ids.ids),
                    ],
                    [],
                    ["resource_id:recordset"],
                )[0][0]
            )
            unavailable_intervals_per_resource_id = defaultdict(list)
            if human_resources := planning_roles.resource_ids.filtered(
                lambda r: r.type == "human" and r not in unavailable_resources
            ):
                min_date_in_utc = fields.Datetime.to_datetime(from_date).replace(
                    tzinfo=UTC
                )
                max_date_in_utc = fields.Datetime.to_datetime(to_date).replace(
                    tzinfo=UTC
                )
                unavailable_intervals_per_resource_id = (
                    human_resources._unavailable_intervals_by_resource(
                        min_date_in_utc, max_date_in_utc
                    )
                )
            if _debug.pipeline.enabled:
                _debug.pipeline(
                    "rental_search_filtered",
                    roles=planning_roles,
                    busy_resources=unavailable_resources,
                    resources_unavailable=sum(
                        1
                        for intervals in unavailable_intervals_per_resource_id.values()
                        if intervals
                    ),
                )
            search_details["base_domain"].append(
                [
                    "|",
                    ("planning_enabled", "=", False),
                    (
                        "planning_role_id",
                        "in",
                        planning_roles.filtered(
                            lambda r: (
                                r.resource_ids.filtered(
                                    lambda r: (
                                        not unavailable_intervals_per_resource_id[r.id]
                                    )
                                )
                                - unavailable_resources
                            )
                        ).ids,
                    ),
                ]
            )
        return search_details
