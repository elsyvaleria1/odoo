from odoo import api, fields, models
from odoo.tools import SQL


class AssetComplianceReport(models.Model):
    _name = "asset.compliance.report"
    _inherit = "document.compliance.report"
    _description = "Asset Compliance Report"
    # Restated because the metaclass reads _log_access from this class's own body,
    # defaulting it to True for a model that only inherits _auto = False.
    _auto = False
    _rec_name = "asset_name"
    _order = "compliance_percentage"

    entity_name = fields.Char(
        string="Asset Name",
        help="Name of the asset (product template name)",
    )

    product_tmpl_id = fields.Many2one(
        comodel_name="product.template",
        readonly=True,
        help="The asset product template",
    )
    product_name = fields.Char(
        readonly=True,
        help="Name of the asset",
    )
    asset_kind_id = fields.Many2one(
        comodel_name="resource.kind",
        readonly=True,
        help="Kind of the asset",
    )

    asset_id = fields.Many2one(
        comodel_name="resource.asset",
        readonly=True,
    )
    asset_name = fields.Char(
        string="Serial Number",
        readonly=True,
        help="Serial number or lot name",
    )

    location_id = fields.Many2one(
        comodel_name="stock.location",
        string="Current Location",
        readonly=True,
        help="Current storage location of this asset",
    )

    total_documents = fields.Integer(
        readonly=True,
        help="Total number of documents attached to this asset",
    )

    next_expiry_date = fields.Date(
        string="Next Expiry",
        readonly=True,
        help="Date of the next expiring document",
    )
    last_verification_date = fields.Date(
        string="Last Verification",
        readonly=True,
        help="Date when any document was last verified",
    )

    compliance_status = fields.Selection(
        selection=[
            ("compliant", "Compliant"),
            ("partial", "Partial Compliance"),
            ("non_compliant", "Non-Compliant"),
            ("no_requirements", "No Requirements"),
        ],
        readonly=True,
        help="Overall compliance status for this asset",
    )

    def _with_cte(self) -> SQL:
        return SQL(
            """
            assets AS (
                SELECT
                    pt.id as product_tmpl_id,
                    pt.name as product_name,
                    rr.kind_id AS asset_kind_id,
                    ra.company_id,
                    ra.id as asset_id,
                    ra.name as asset_name,
                    sq.location_id
                FROM resource_asset ra
                JOIN resource_resource rr ON rr.id = ra.resource_id
                JOIN product_product pp ON pp.id = rr.product_id
                JOIN product_template pt ON pt.id = pp.product_tmpl_id
                LEFT JOIN product_trace sl ON sl.id = rr.trace_id
                LEFT JOIN stock_quant sq ON sq.trace_id = sl.id AND sq.quantity > 0
                WHERE rr.kind_id IS NOT NULL
                    AND ra.active = true
            ),
            asset_documents AS (
                SELECT
                    a.asset_id,
                    dd.id as document_id,
                    dd.document_type_id,
                    dd.expiration_state,
                    dd.date_expiration,
                    dd.date_verification
                FROM assets a
                JOIN document_document dd ON (
                    dd.res_model = %(asset_reference)s
                    AND dd.res_id = a.asset_id
                    AND dd.active = true
                )
            ),
            asset_requirements AS (
                SELECT
                    a.product_tmpl_id,
                    a.product_name,
                    a.asset_kind_id,
                    a.company_id,
                    a.asset_id,
                    a.asset_name,
                    a.location_id,
                    dt.id as document_type_id,
                    dt.is_mandatory
                FROM assets a
                CROSS JOIN document_type dt
                WHERE dt.active = true
                    AND dt.is_mandatory = true
                    AND dt.applies_to IN ('all', 'resource.asset')
                    AND (dt.company_id = a.company_id OR dt.company_id IS NULL)
            ),
            asset_doc_types AS (
                SELECT
                    ar.product_tmpl_id,
                    ar.product_name,
                    ar.asset_kind_id,
                    ar.company_id,
                    ar.asset_id,
                    ar.asset_name,
                    ar.location_id,
                    ar.document_type_id,
                    ar.is_mandatory,
                    COUNT(ad.document_id) as document_count,
                    MAX(CASE WHEN ad.expiration_state = 'valid' THEN 1 ELSE 0 END) as is_valid,
                    CASE
                        WHEN COUNT(ad.document_id) = 0 THEN 0
                        WHEN MAX(CASE WHEN ad.expiration_state = 'valid' THEN 1 ELSE 0 END) = 1 THEN 0
                        WHEN MAX(CASE WHEN ad.expiration_state = 'expired' THEN 1 ELSE 0 END) = 1 THEN 1
                        ELSE 0
                    END as is_expired,
                    CASE
                        WHEN MAX(CASE WHEN ad.expiration_state = 'expiring_soon' THEN 1 ELSE 0 END) = 1
                            AND MAX(CASE WHEN ad.expiration_state = 'valid' THEN 1 ELSE 0 END) = 0 THEN 1
                        ELSE 0
                    END as is_expiring,
                    CASE WHEN COUNT(ad.document_id) = 0 THEN 1 ELSE 0 END as is_missing,
                    MIN(ad.date_expiration) FILTER (
                        WHERE ad.expiration_state != 'valid'
                        AND ad.date_expiration IS NOT NULL
                    ) as earliest_expiry,
                    MAX(ad.date_verification) as last_verification
                FROM asset_requirements ar
                LEFT JOIN asset_documents ad ON
                    ad.asset_id = ar.asset_id
                    AND ad.document_type_id = ar.document_type_id
                GROUP BY
                    ar.product_tmpl_id,
                    ar.product_name,
                    ar.asset_kind_id,
                    ar.company_id,
                    ar.asset_id,
                    ar.asset_name,
                    ar.location_id,
                    ar.document_type_id,
                    ar.is_mandatory
            )
            """,
            asset_reference=self.env["resource.asset"]._get_reference_model_name(),
        )

    def _get_fields_select(self) -> dict:
        return {
            "id": "ROW_NUMBER() OVER (ORDER BY adt.product_tmpl_id, adt.asset_id)",
            "entity_name": "adt.product_name",
            "entity_type": "'resource.asset'",
            "entity_id": "adt.asset_id",
            "product_tmpl_id": "adt.product_tmpl_id",
            "product_name": "adt.product_name",
            "asset_kind_id": "adt.asset_kind_id",
            "asset_id": "adt.asset_id",
            "asset_name": "adt.asset_name",
            "location_id": "adt.location_id",
            "total_documents": "SUM(adt.document_count)",
            "total_required": "COUNT(adt.document_type_id)",
            "total_valid": "SUM(adt.is_valid)",
            "total_expired": "SUM(adt.is_expired)",
            "total_expiring": "SUM(adt.is_expiring)",
            "total_missing": "SUM(adt.is_missing)",
            "total_present": "SUM(CASE WHEN adt.document_count > 0 THEN 1 ELSE 0 END)",
            "compliance_percentage": """CASE
                    WHEN COUNT(adt.document_type_id) = 0 THEN 0.0
                    ELSE (SUM(adt.is_valid)::float / COUNT(adt.document_type_id)::float) * 100
                END""",
            "is_compliant": """CASE
                    WHEN SUM(adt.is_valid) = COUNT(adt.document_type_id) THEN true
                    ELSE false
                END""",
            "compliance_state": """CASE
                    WHEN COUNT(adt.document_type_id) = 0 THEN 'no_requirements'
                    WHEN SUM(adt.is_valid) = COUNT(adt.document_type_id) THEN 'compliant'
                    WHEN SUM(adt.is_valid) > 0 THEN 'partial'
                    ELSE 'non_compliant'
                END""",
            "compliance_status": """CASE
                    WHEN COUNT(adt.document_type_id) = 0 THEN 'no_requirements'
                    WHEN SUM(adt.is_valid) = COUNT(adt.document_type_id) THEN 'compliant'
                    WHEN SUM(adt.is_valid) > 0 THEN 'partial'
                    ELSE 'non_compliant'
                END""",
            "earliest_expiry": "MIN(adt.earliest_expiry)",
            "next_expiry_date": "MIN(adt.earliest_expiry)",
            "last_verification": "MAX(adt.last_verification)",
            "last_verification_date": "MAX(adt.last_verification)",
            "company_id": "adt.company_id",
        }

    def _get_from_tables(self) -> list:
        return [
            ("asset_doc_types", "adt", None, None),
        ]

    def _get_where_conditions(self) -> list:
        return []

    def _get_fields_group_by(self) -> list:
        return [
            "adt.product_tmpl_id",
            "adt.product_name",
            "adt.asset_kind_id",
            "adt.asset_id",
            "adt.asset_name",
            "adt.location_id",
            "adt.company_id",
        ]

    @api.model
    def get_asset_compliance_by_kind(self) -> list:
        domain = [("company_id", "=", self.env.company.id)]
        rows = self._read_group(
            domain,
            ["asset_kind_id"],
            [
                "__count",
                "compliance_percentage:avg",
                "total_expired:sum",
                "total_expiring:sum",
            ],
            order="asset_kind_id",
        )
        compliant_by_kind = dict(
            self._read_group(
                [*domain, ("is_compliant", "=", True)],
                ["asset_kind_id"],
                ["__count"],
            )
        )
        return [
            {
                "asset_kind": asset_kind.display_name if asset_kind else None,
                "asset_kind_id": asset_kind.id if asset_kind else False,
                "total_assets": total_assets,
                "compliant_assets": compliant_by_kind.get(asset_kind, 0),
                "avg_compliance": avg_compliance,
                "total_expired": total_expired,
                "total_expiring": total_expiring,
            }
            for (
                asset_kind,
                total_assets,
                avg_compliance,
                total_expired,
                total_expiring,
            ) in rows
        ]

    @api.readonly
    def action_view_asset_documents(self) -> dict:
        self.check_singleton()
        reference = self.env["resource.asset"]._get_reference_model_name()
        return {
            "name": f"Documents: {self.product_name}",
            "type": "ir.actions.act_window",
            "res_model": "document.document",
            "view_mode": "kanban,list",
            "domain": [
                "|",
                ("product_tmpl_id", "=", self.product_tmpl_id.id),
                "&",
                ("res_model", "=", reference),
                (
                    ("res_id", "=", self.asset_id.id)
                    if self.asset_id
                    else ("id", "=", False)
                ),
            ],
            "context": {
                "default_asset_id": self.product_tmpl_id.id,
                "default_res_model": reference if self.asset_id else False,
                "default_res_id": self.asset_id.id if self.asset_id else False,
            },
        }

    @api.readonly
    def action_view_missing_documents(self) -> dict:
        self.check_singleton()

        return {
            "type": "ir.actions.act_window",
            "name": f"Missing Documents for {self.product_name}",
            "res_model": "document.type",
            "view_mode": "list",
            "domain": [
                ("is_mandatory", "=", True),
            ],
        }
