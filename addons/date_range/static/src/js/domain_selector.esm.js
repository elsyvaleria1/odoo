/** @odoo-module native */

import { onWillStart } from "@odoo/owl";
import { DomainSelector } from "@web/components/domain_selector";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";

import { setDateRanges } from "./date_range_provider.js";

patch(DomainSelector.prototype, {
    setup() {
        super.setup(...arguments);
        this.dateRangeService = useService("date_range");
        this.notification = useService("notification");

        onWillStart(async () => {
            try {
                const { ranges } = await this.dateRangeService.loadDateRanges();
                setDateRanges(ranges);
            } catch {
                setDateRanges([]);
                this.notification.add(
                    _t(
                        "Date ranges could not be loaded. Date range filters will not be available.",
                    ),
                    { type: "warning", sticky: false },
                );
            }
        });
    },
});
