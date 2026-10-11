/** @odoo-module native */
import { proxy } from "@odoo/owl";
import { useDateTimePicker } from "@web/components/datetime";
import { DATE_SHORT, serializeDate, today, toLocaleString } from "@web/core/l10n/dates";
import { elementRef } from "@web/core/utils/element_ref";
import { ListController } from "@web/views/list";

import { useAccrualContext } from "./accrual_list_search_model.js";

export class AccrualListController extends ListController {
    setup() {
        super.setup();
        this.accrualContext = useAccrualContext();
        this.state = proxy({
            date: today(),
        });
        this.dateAsString = serializeDate(this.state.date);
        if (this.model.config.resModel === "purchase.order.line") {
            this.model.config.fields.qty_transferred_at_date.aggregator = "sum";
        } else {
            this.model.config.fields.qty_transferred_at_date.aggregator = "sum";
        }
        this.model.config.fields.qty_invoiced_at_date.aggregator = "sum";
        this.model.config.fields.amount_to_invoice_at_date.aggregator = "sum";
        this.filterDateRef = elementRef();
        const getPickerProps = () => {
            const pickerProps = {
                value: this.state.date,
                type: "date",
            };
            return pickerProps;
        };
        this.endDateRef = elementRef();
        this.startDateRef = elementRef();
        this.dateTimePicker = useDateTimePicker({
            endDateRef: this.endDateRef,
            startDateRef: this.startDateRef,
            target: this.filterDateRef,
            get pickerProps() {
                return getPickerProps();
            },
            onApply: (newDate) => {
                if (newDate) {
                    this.setDate(newDate);
                }
            },
        });
    }

    async openRecord(record) {
        const res_model = record.model.config.fields.order_id.relation;
        this.actionService.doAction({
            name: record.data.order_id.display_name,
            type: "ir.actions.act_window",
            res_model,
            res_id: record.data.order_id.id,
            views: [[false, "form"]],
            target: "current",
        });
    }

    async setDate(date) {
        this.dateAsString = serializeDate(date);
        this.model.config.context.accrual_entry_date = this.dateAsString;
        this.accrualContext.accrual_entry_date = this.dateAsString;
        this.state.date = date;

        if (this.model.config.groups) {
            for (const group of Object.values(this.model.config.groups)) {
                group.context.accrual_entry_date = this.dateAsString;
            }
        }

        await this.model.root.load();
        this.model.notify();
    }

    get date() {
        return toLocaleString(this.state.date, DATE_SHORT);
    }

    onDateClick() {
        this.dateTimePicker.open();
    }

    async beforeExecuteActionButton(clickParams) {
        if (this.dateAsString) {
            clickParams.buttonContext.default_date = this.dateAsString;
        }
        return super.beforeExecuteActionButton(...arguments);
    }
}
