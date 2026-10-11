import {
    defineHrSkillModels,
    hrSkillModels,
} from "@hr_skills/../tests/hr_skills_test_helpers";
import { describe, expect, test } from "@odoo/hoot";
import { click, queryAllTexts } from "@odoo/hoot-dom";
import { animationFrame } from "@odoo/hoot-mock";
import { expectRowsCoverHeaderGrid } from "@web/../tests/views/list/list_grid_test_helpers";
import { defineModels, models, mountView, onRpc } from "@web/../tests/web_test_helpers";

describe.current.tags("desktop");
defineHrSkillModels();

class HrSkillType extends models.ServerModel {
    _name = "hr.skill.type";
}
class HrSkillLevel extends models.ServerModel {
    _name = "hr.skill.level";
}
class HrEmployeeSkillHistoryReport extends models.ServerModel {
    _name = "hr.employee.skill.history.report";
}
defineModels({ HrSkillType, HrSkillLevel, HrEmployeeSkillHistoryReport });

const SKILLS_ARCH = `
    <form>
        <field name="employee_id" invisible="1"/>
        <field mode="list" nolabel="1" name="current_employee_skill_ids" widget="skills_one2many">
            <list>
                <field name="skill_id"/>
                <field name="skill_level_id"/>
                <field name="skill_type_id"/>
            </list>
        </field>
    </form>`;

function seedEmployeeWithTwoHomonymTypes() {
    const { HrEmployee, HrEmployeeSkill, HrSkill } = hrSkillModels;
    const [spokenId, signedId] = HrSkillType._records.push(
        { id: 101, name: "Languages" },
        { id: 102, name: "Languages" },
    ) && [101, 102];
    HrSkillLevel._records.push({ id: 201, name: "Fluent", skill_type_id: spokenId });
    HrSkillLevel._records.push({ id: 202, name: "Fluent", skill_type_id: signedId });
    HrSkill._records.push({ id: 301, name: "French", skill_type_id: spokenId });
    HrSkill._records.push({ id: 302, name: "LSF", skill_type_id: signedId });
    HrEmployeeSkill._records.push(
        { id: 401, skill_id: 301, skill_level_id: 201, skill_type_id: spokenId },
        { id: 402, skill_id: 302, skill_level_id: 202, skill_type_id: signedId },
    );
    const employeeId = HrEmployee._records.length + 1;
    HrEmployee._records.push({
        id: employeeId,
        name: "Polyglot",
        employee_id: employeeId,
        employee_skill_ids: [401, 402],
        current_employee_skill_ids: [401, 402],
    });
    return employeeId;
}

test("two skill types sharing a name are two groups", async () => {
    const employeeId = seedEmployeeWithTwoHomonymTypes();
    await mountView({
        type: "form",
        resModel: "hr.employee",
        resId: employeeId,
        arch: SKILLS_ARCH,
    });
    expect(".o_skill_table .o_group_header").toHaveCount(2);
    expect(queryAllTexts(".o_skill_table .o_group_name span")).toEqual([
        "Languages",
        "Languages",
    ]);
    expect(".o_skill_table .o_data_row").toHaveCount(2);
    expect(queryAllTexts(".o_skill_table .o_data_row [name=skill_id]")).toEqual([
        "French",
        "LSF",
    ]);
});

test("a skill row is the list's row component, editable on click", async () => {
    const employeeId = seedEmployeeWithTwoHomonymTypes();
    await mountView({
        type: "form",
        resModel: "hr.employee",
        resId: employeeId,
        arch: SKILLS_ARCH.replace("<list>", '<list editable="bottom">'),
    });
    expect(".o_skill_table .o_data_row.o_selected_row").toHaveCount(0);
    await click(".o_skill_table .o_data_row:eq(1) [name=skill_level_id]");
    await animationFrame();
    expect(".o_skill_table .o_data_row:eq(1)").toHaveClass("o_selected_row");
    expect(".o_skill_table .o_data_row:eq(1) [name=skill_level_id] input").toHaveCount(
        1,
    );
});

test("opening the skills widget asks the server two questions, not four", async () => {
    const employeeId = seedEmployeeWithTwoHomonymTypes();
    onRpc("hr.employee.skill.history.report", "search_count", ({ args }) => {
        expect(args[0]).toEqual([["employee_id", "=", employeeId]]);
        return 3;
    });
    const calls = [];
    onRpc(({ model, method }) => {
        if (
            [
                "hr.skill.type",
                "hr.employee.skill.history.report",
                "res.users",
                "hr.employee",
            ].includes(model)
        ) {
            calls.push(`${model}/${method}`);
        }
    });
    await mountView({
        type: "form",
        resModel: "hr.employee",
        resId: employeeId,
        arch: SKILLS_ARCH,
    });
    expect(calls.filter((c) => c === "hr.skill.type/search_count")).toHaveLength(1);
    expect(
        calls.filter((c) => c === "hr.employee.skill.history.report/search_count"),
    ).toHaveLength(1);
    expect(calls.filter((c) => c.startsWith("res.users/"))).toHaveLength(0);
    expect(calls.filter((c) => c === "hr.employee/search_read")).toHaveLength(0);
    expect(".skills_header a").toHaveCount(1);
});

test("the timeline link is hidden when the report has nothing for this employee", async () => {
    const employeeId = seedEmployeeWithTwoHomonymTypes();
    onRpc("hr.employee.skill.history.report", "search_count", () => 0);
    await mountView({
        type: "form",
        resModel: "hr.employee",
        resId: employeeId,
        arch: SKILLS_ARCH,
    });
    expect(".skills_header a").toHaveCount(0);
});

const SHIPPED_SKILLS_LIST = `
    <field name="skill_id"/>
    <field name="skill_level_id"/>
    <field name="level_progress" widget="progressbar"/>
    <field name="skill_type_id" optional="hide"/>
    <field name="valid_to" column_invisible="1"/>
    <field name="is_certification" column_invisible="1"/>
`;

describe("skill group rows cover the header grid", () => {
    const configs = {
        "as the employee form declares it": { list: "<list>" },
        "editable list": { list: '<list editable="bottom">' },
        "optional column shown": {
            list: "<list>",
            columns: SHIPPED_SKILLS_LIST.replace('optional="hide"', 'optional="show"'),
        },
        "readonly field": { list: "<list>", fieldAttrs: 'readonly="1"' },
        "no optional column, delete refused": {
            list: '<list delete="0">',
            columns: SHIPPED_SKILLS_LIST.replace(' optional="hide"', ""),
        },
    };
    for (const [
        label,
        { list, columns = SHIPPED_SKILLS_LIST, fieldAttrs = "" },
    ] of Object.entries(configs)) {
        test(label, async () => {
            const employeeId = seedEmployeeWithTwoHomonymTypes();
            await mountView({
                type: "form",
                resModel: "hr.employee",
                resId: employeeId,
                arch: `
                    <form>
                        <field name="employee_id" invisible="1"/>
                        <field mode="list" nolabel="1" name="current_employee_skill_ids"
                               widget="skills_one2many" ${fieldAttrs}>
                            ${list}${columns}</list>
                        </field>
                    </form>`,
            });
            expect(".o_skill_table .o_group_header").toHaveCount(2);
            expectRowsCoverHeaderGrid({
                table: ".o_skill_table",
                rows: ".o_group_header, .o_data_row",
            });
        });
    }
});
