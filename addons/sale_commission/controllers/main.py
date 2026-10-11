from odoo.http import Controller, prepare_content_disposition_header, request, route
from odoo.libs.debug_log import DebugLog
from odoo.libs.documents import Document, extension_for, mimetype_for

XLSX_MIMETYPE = mimetype_for("xlsx")

_debug = DebugLog(__name__)


class SaleCommissionTargetExportController(Controller):
    @route(
        "/sale_commission/export/targets/<int:plan_id>",
        type="http",
        auth="user",
        readonly=True,
    )
    def export_targets(self, plan_id):
        plan = request.env["sale.commission.plan"].browse(plan_id)
        target_ids = plan.target_commission_ids
        headers = [
            request.env._("Performance"),
            request.env._("Commission"),
            request.env._("Currency"),
        ]
        _debug.pipeline("commission_targets_exported", plan=plan, targets=target_ids)
        return self._generate_xlsx(
            filename=plan.name, target_ids=target_ids, headers=headers
        )

    def _interpolate_target(self, target_rate, sorted_rates, values_by_rate):
        for rate in sorted_rates:
            if rate > target_rate:
                x2 = rate
                y2 = values_by_rate[rate][1]
                break
            x1 = rate
            y1 = values_by_rate[rate][1]
        if x1 is None or x2 is None or x2 == x1:
            _debug.logic("target_interpolation_skipped", rate=target_rate)
            return 0
        return y1 + (y2 - y1) / (x2 - x1) * (target_rate - x1)

    def _generate_rows(self, target_ids):
        if not target_ids:
            return []
        rows = []
        values_by_rate = {}
        sorted_rates = []
        currency_name = target_ids[0].currency_id.name
        for target in target_ids.sorted("target_rate"):
            row = [target.target_rate * 100, target.amount, currency_name]
            values_by_rate[target.target_rate] = row
            sorted_rates.append(target.target_rate)
            rows.append(row)
        target_max = target.target_rate + 0.1
        all_rate = [
            x / 100
            for x in range(0, int(target_max * 100), 10)
            if x / 100 <= target.target_rate
        ] + sorted_rates
        all_rate = set(all_rate)
        all_rate = sorted(all_rate)
        all_rows = []
        for target_val in all_rate:
            row_val = values_by_rate.get(target_val)
            if not row_val:
                amount = self._interpolate_target(
                    target_val, sorted_rates, values_by_rate
                )
                row_val = [target_val * 100, amount, currency_name]
            all_rows.append(row_val)
        return all_rows

    def _generate_xlsx(self, filename="", target_ids=None, headers=None):
        document = Document.of(
            rows=self._generate_rows(target_ids),
            mimetype=XLSX_MIMETYPE,
            columns_headers=headers,
            env=request.env,
        )
        return request.prepare_response(
            document.data,
            [
                ("Content-Type", XLSX_MIMETYPE),
                (
                    "Content-Disposition",
                    prepare_content_disposition_header(
                        f"Targets - {filename}.{extension_for(XLSX_MIMETYPE)}"
                    ),
                ),
            ],
        )
