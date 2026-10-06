/** @odoo-module native */
import { FormController } from "@web/views/form";

export class SalaryCalculatorFormController extends FormController {
    get modelParams() {
        const params = super.modelParams;
        params.hooks.lifecycle.onRecordChanged = (record) => {
            record.save();
        };
        return params;
    }
}
