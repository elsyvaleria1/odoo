from odoo import api, fields, models


class ProjectSaleLineEmployeeMap(models.Model):
    _inherit = "project.sale.line.employee.map"

    timesheet_product_id = fields.Many2one(
        comodel_name="product.product",
        string="Service",
        domain="""[
            ('type', '=', 'service'),
            ('invoice_policy', '=', 'transferred'),
            ('service_type', '=', 'timesheet'),
        ]""",
        check_company=True,
    )
    price_unit = fields.Float(readonly=False)

    @api.depends("partner_id")
    def _compute_sale_line_id(self) -> None:
        fsm_mappings = self.filtered(lambda map_entry: map_entry.project_id.is_fsm)
        if fsm_mappings:
            price_unit_field = self._fields["price_unit"]
            currency_id_field = self._fields["currency_id"]
            self.env.remove_to_compute(price_unit_field, fsm_mappings)
            self.env.remove_to_compute(currency_id_field, fsm_mappings)
        super(ProjectSaleLineEmployeeMap, self - fsm_mappings)._compute_sale_line_id()

    @api.depends("sale_line_id.price_unit", "timesheet_product_id")
    def _compute_price_unit(self) -> None:
        mappings_with_product_and_no_sol = self.filtered(
            lambda mapping: not mapping.sale_line_id and mapping.timesheet_product_id
        )
        for line in mappings_with_product_and_no_sol:
            line.price_unit = line.timesheet_product_id.lst_price
        super(
            ProjectSaleLineEmployeeMap, self - mappings_with_product_and_no_sol
        )._compute_price_unit()

    @api.depends("sale_line_id.price_unit", "timesheet_product_id")
    def _compute_currency_id(self) -> None:
        fsm_project_mappings = self.filtered(lambda mapping: mapping.project_id.is_fsm)
        for mapping in fsm_project_mappings:
            mapping.currency_id = (
                mapping.timesheet_product_id.currency_id
                if mapping.timesheet_product_id
                else False
            )
        super(
            ProjectSaleLineEmployeeMap, self - fsm_project_mappings
        )._compute_currency_id()
