/** @odoo-module native */
import { AccountReport } from "@report_formula/components/account_report/account_report";
import { AccountReportFilters } from "@report_formula/components/account_report/filters/filters";
import { _t } from "@web/core/translation";

export class FiscalFleetFilters extends AccountReportFilters {
    get filterExtraOptionsData() {
        return {
            ...super.filterExtraOptionsData,
            vehicle_split: {
                name: _t("Vehicle Split"),
            },
        };
    }
}

AccountReport.registerCustomComponent(FiscalFleetFilters);
