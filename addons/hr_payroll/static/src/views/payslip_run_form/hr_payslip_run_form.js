/** @odoo-module native */
import { markup } from "@odoo/owl";
import { serializeDate } from "@web/core/l10n/dates";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import {
    addFieldDependencies,
    extractFieldsFromArchInfo,
} from "@web/model/relational_model";
import { FormController, formView } from "@web/views/form";

export class PayslipBatchFormController extends FormController {
    setup() {
        super.setup();
        const { activeFields, fields } = extractFieldsFromArchInfo(
            this.archInfo,
            this.props.fields,
        );
        addFieldDependencies(activeFields, fields, [
            { name: this.archInfo.name, type: "string" },
        ]);
        this.actionService = useService("action");
    }

    get payRunValid() {
        return (
            this.model.root &&
            this.model.root.data.date_start &&
            this.model.root.data.date_end
        );
    }

    async selectEmployees() {
        const data = this.model.root.data;
        const employeeListAction = await this.orm.call(
            "hr.payslip.run",
            "action_payroll_hr_version_list_view_payrun",
            [
                [this.model.root.resId],
                serializeDate(data.date_start),
                serializeDate(data.date_end),
                data.structure_id?.id,
                data.company_id?.id,
                data.schedule_pay,
            ],
        );
        return this.actionService.doAction({
            ...employeeListAction,
            help: markup(employeeListAction.help),
            context: {
                // Pass a JSON-safe snapshot of the dialog fields, not the live
                // OWL record. Forwarding this.model.root.data leaked date
                // objects through the action context, where date_start
                // /date_end did not survive as parseable ISO strings; the list
                // controller's buildRawRecord() then produced null dates and
                // hr.payslip.run create() raised "set a start and end date".
                raw_record: this._payRunRawRecord(),
            },
        });
    }

    /**
     * Build the JSON-safe pay-run payload carried to the employee-selection
     * step. Dates are serialized to ISO strings and Many2one fields to ids so
     * the action context survives serialization. Localization layers override
     * this to contribute their own fields (see l10n_mx_edi_payslip).
     *
     * :return: plain object of pay-run create values
     * :rtype: object
     */
    _payRunRawRecord() {
        const data = this.model.root.data;
        return {
            date_start: serializeDate(data.date_start),
            date_end: serializeDate(data.date_end),
            schedule_pay: data.schedule_pay,
            structure_id: data.structure_id?.id,
            company_id: data.company_id?.id,
        };
    }
}

registry.category("views").add("hr_payslip_batch_form", {
    ...formView,
    Controller: PayslipBatchFormController,
    buttonTemplate: "hr_payroll.PayslipBatchFormView.Buttons",
});
