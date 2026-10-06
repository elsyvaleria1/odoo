import { defineHrPayrollModels } from "@hr_payroll/../tests/hr_payroll_test_helpers";
import { HrPayslipRun } from "@hr_payroll/../tests/mock_server/mock_models/hr_payslip_run";
import { describe, expect, test } from "@odoo/hoot";
import { mountView } from "@web/../tests/web_test_helpers";

describe.current.tags("desktop");
defineHrPayrollModels();

const ARCH = `
    <kanban>
        <templates>
            <t t-name="card">
                <field name="state" widget="hr_payroll_status_bubble"
                       options="{'remove_states': ['04_cancel']}"/>
            </t>
        </templates>
    </kanban>`;

async function mountPayRun(values) {
    HrPayslipRun._records = [{ id: 1, name: "Pay Run", state: "01_ready", ...values }];
    await mountView({ type: "kanban", resModel: "hr.payslip.run", arch: ARCH });
}

test("status bubble counts the pay run's payslips with issues", async () => {
    await mountPayRun({ payslips_with_issues: 3, has_error: false });
    expect(".state-bubbles .state:eq(0) span.small span").toHaveText("3 Issues");
    expect(".state-bubbles .state:eq(0) .rounded-circle").toHaveClass("bg-warning");
});

test("status bubble reports an erroring pay run", async () => {
    await mountPayRun({ payslips_with_issues: 0, has_error: true });
    expect(".state-bubbles .state:eq(0) span.small span").toHaveText("0 Issues");
    expect(".state-bubbles .state:eq(0) .rounded-circle").toHaveClass("bg-danger");
});

test("status bubble stays quiet on a clean pay run", async () => {
    await mountPayRun({ payslips_with_issues: 0, has_error: false, payslip_count: 3 });
    expect(".state-bubbles .state:eq(0) span.small span").toHaveCount(0);
    expect(".state-bubbles .state:eq(0) .rounded-circle").toHaveClass("bg-success");
});

test("status bubble drops the states the widget is told to remove", async () => {
    await mountPayRun({ payslips_with_issues: 0, has_error: false });
    expect(".state-bubbles .state").toHaveCount(3);
});

test("the current stage stays grey while the pay run has no payslip", async () => {
    await mountPayRun({ payslips_with_issues: 0, has_error: false, payslip_count: 0 });
    expect(".state-bubbles .state:eq(0) .rounded-circle").not.toHaveClass("bg-success");
});

test("the current stage turns green as soon as the pay run has payslips", async () => {
    await mountPayRun({ payslips_with_issues: 0, has_error: false, payslip_count: 3 });
    expect(".state-bubbles .state:eq(0) .rounded-circle").toHaveClass("bg-success");
});
