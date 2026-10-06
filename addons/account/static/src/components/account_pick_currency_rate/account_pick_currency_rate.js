/** @odoo-module native */
import { Component, useProps } from "@odoo/owl";
import { useDateTimePicker } from "@web/components/datetime";
import { toISODate } from "@web/core/l10n/dates";
import { registry } from "@web/core/registry";
import { elementRef } from "@web/core/utils/element_ref";
import { useService } from "@web/core/utils/hooks";
import { standardWidgetProps } from "@web/views/widgets";

export class AccountPickCurrencyDate extends Component {
    static template = "account.AccountPickCurrencyDate";
    static props = { ...standardWidgetProps };
    props = useProps(this.constructor.props);

    setup() {
        this.orm = useService("orm");
        this.endDateRef = elementRef();
        this.startDateRef = elementRef();
        this.datetimePickerTargetRef = elementRef();
        this.dateTimePicker = useDateTimePicker({
            endDateRef: this.endDateRef,
            startDateRef: this.startDateRef,
            target: this.datetimePickerTargetRef,
            onApply: async (date) => {
                const record = this.props.record;
                const rate = await this.orm.call("account.move", "get_currency_rate", [
                    record.resId,
                    record.data.company_id.id,
                    record.data.currency_id.id,
                    toISODate(date),
                ]);
                this.props.record.update({ invoice_currency_rate: rate });
                await this.props.record.save();
            },
            get pickerProps() {
                return {
                    type: "date",
                };
            },
        });
    }
}

export const accountPickCurrencyDate = {
    component: AccountPickCurrencyDate,
};

registry
    .category("view_widgets")
    .add("account_pick_currency_date", accountPickCurrencyDate);
