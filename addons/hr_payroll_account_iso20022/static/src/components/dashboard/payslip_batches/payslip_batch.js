/** @odoo-module native */
import { PayrollDashboardPayslipBatch } from "@hr_payroll/components/dashboard/payslip_batch/payslip_batch";
import { patch } from "@web/core/utils/patch";
import { BinaryField } from "@web/fields/media/binary/binary_field";
import { Record } from "@web/model/record";

patch(PayrollDashboardPayslipBatch.prototype, {
    /**
     * @returns {boolean} Whether any batch has a sepa export to display
     */
    _hasSepaExport() {
        return this.props.batches.find((elem) => elem.sepa_export);
    },

    getRecordProps(batch) {
        const fields = {
            sepa_export: { name: "sepa_export", type: "binary" },
            sepa_export_filename: { name: "sepa_export_filename", type: "char" },
        };
        return {
            resModel: "hr.payslip.run",
            resId: batch.id,
            fields,
            fieldNames: Object.keys(fields),
            values: {
                sepa_export: "coucou==\n",
                sepa_export_filename: "SEPA",
            },
        };
    },
});

PayrollDashboardPayslipBatch.components = Object.assign(
    {},
    PayrollDashboardPayslipBatch.components,
    { BinaryField, Record },
);
