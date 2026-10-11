import { defineHrPayrollModels } from "@hr_payroll/../tests/hr_payroll_test_helpers";
import { HrPayslip } from "@hr_payroll/../tests/mock_server/mock_models/hr_payslip";
import { beforeEach, describe, expect, test } from "@odoo/hoot";
import { mockDate } from "@odoo/hoot-mock";
import {
    contains,
    defineModels,
    models,
    mountView,
} from "@web/../tests/web_test_helpers";

describe.current.tags("desktop");

const definition = (count) =>
    Array.from({ length: count }, (_, i) => ({
        name: `bonus_${i}`,
        type: "float",
        string: `Bonus ${i}`,
    }));

class HrPayrollStructure extends models.ServerModel {
    _name = "hr.payroll.structure";

    _records = [
        {
            id: 1,
            name: "Structure A",
            display_name: "Structure A",
            payslip_properties_definition: definition(6),
        },
        {
            id: 2,
            name: "Structure B",
            display_name: "Structure B",
            payslip_properties_definition: definition(6),
        },
    ];
}

defineHrPayrollModels();
defineModels({ HrPayrollStructure });

const ARCH = `
    <list js_class="hr_payroll_payslip_list">
        <field name="employee_id"/>
        <field name="struct_id" column_invisible="1"/>
        <field name="payslip_properties"/>
        <field name="net_wage" optional="hide"/>
    </list>
`;

const propertyHeaders = () =>
    [...document.querySelectorAll("thead th[data-name^='payslip_properties.']")].map(
        (th) => th.dataset.name,
    );

const payslip = (id, structId) => ({
    id,
    struct_id: structId,
    payslip_properties: Object.fromEntries(
        definition(6).map((d, i) => [d.name, 10 * i + id]),
    ),
});

beforeEach(() => {
    mockDate("2025-01-01 12:00:00", +0);
});

test("one structure shows the first four benefits", async () => {
    HrPayslip._records = [payslip(1, 1), payslip(2, 1)];
    await mountView({ type: "list", resModel: "hr.payslip", arch: ARCH });
    expect(propertyHeaders()).toEqual([
        "payslip_properties.bonus_0",
        "payslip_properties.bonus_1",
        "payslip_properties.bonus_2",
        "payslip_properties.bonus_3",
    ]);
});

test("mixed structures offer no benefit column at all", async () => {
    HrPayslip._records = [payslip(1, 1), payslip(2, 2)];
    await mountView({ type: "list", resModel: "hr.payslip", arch: ARCH });
    expect(propertyHeaders()).toEqual([]);
    await contains(".o_optional_columns_dropdown .dropdown-toggle").click();
    expect(".o-dropdown--menu input").toHaveCount(1);
    expect(".o-dropdown--menu input[name^='payslip_properties.']").toHaveCount(0);
});
