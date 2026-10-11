import { mailModels } from "@mail/../tests/mail_test_helpers";
import { beforeEach, describe, expect, test } from "@odoo/hoot";
import { click, queryAll, queryFirst } from "@odoo/hoot-dom";
import { animationFrame, mockDate } from "@odoo/hoot-mock";
import { fields, mountView, onRpc } from "@web/../tests/web_test_helpers";

import { definePlanningModels, planningModels } from "./planning_mock_models.js";

describe.current.tags("desktop");

class PlanningSlot extends planningModels.PlanningSlot {
    resource_roles = fields.One2many({ relation: "resource.role" });

    _records = [
        {
            display_name: "Planning Slot tester 1",
            resource_id: 1,
            resource_type: "material",
            resource_roles: [1],
            user_id: false,
            start_datetime: "2023-11-09 00:00:00",
            end_datetime: "2023-11-09 22:00:00",
        },
        {
            display_name: "Planning slot integration tester",
            resource_id: 2,
            resource_type: "material",
            resource_roles: [1, 2],
            user_id: false,
            start_datetime: "2023-11-09 00:00:00",
            end_datetime: "2023-11-09 22:00:00",
        },
        {
            display_name: "Planning slot Marie",
            resource_id: 3,
            resource_type: "human",
            resource_roles: [1],
            user_id: false,
            start_datetime: "2023-11-09 00:00:00",
            end_datetime: "2023-11-09 22:00:00",
        },
        {
            display_name: "Planning Slot Pierre",
            resource_id: 4,
            resource_type: "human",
            resource_roles: [2],
            user_id: 1,
            start_datetime: "2023-11-09 00:00:00",
            end_datetime: "2023-11-09 22:00:00",
        },
    ];
}

class ResourceRole extends planningModels.ResourceRole {
    _records = [
        {
            id: 1,
            name: "Tester",
            color: 1,
        },
        {
            id: 2,
            name: "It Specialist",
            color: 2,
        },
    ];
}

class ResourceResource extends planningModels.ResourceResource {
    _records = [
        {
            id: 1,
            name: "Continuity testing computer",
            type: "material",
            role_ids: [1],
        },
        {
            id: 2,
            name: "Integration testing computer",
            type: "material",
            role_ids: [1, 2],
        },
        {
            id: 3,
            name: "Marie",
            type: "human",
            role_ids: [1],
        },
        {
            id: 4,
            name: "Pierre",
            type: "human",
            role_ids: [2],
            user_id: 1,
            im_status: "online",
        },
    ];
}

class HrEmployee extends planningModels.HrEmployee {
    _records = [
        {
            id: 1,
            name: "Marie",
            resource_id: 3,
        },
        {
            id: 2,
            name: "Pierre",
            resource_id: 4,
            user_id: 1,
            partner_id: 1,
        },
    ];
}

definePlanningModels({ PlanningSlot, ResourceRole, ResourceResource, HrEmployee });

onRpc("get_avatar_card_data", function ({ args }) {
    const [ids, fields] = args[0];
    return this.env["resource.resource"].read(ids, fields);
});

beforeEach(() => {
    mailModels.ResUsers._records.push({
        id: 1,
        name: "Pierre",
        partner_id: 1,
    });
});

test("many2one_avatar_resource widget in kanban view", async () => {
    await mountView({
        resModel: "planning.slot",
        type: "kanban",
        arch: `<kanban>
                <templates>
                    <t t-name="card">
                        <field name="display_name"/>
                        <field name="resource_id" widget="many2one_avatar_resource"/>
                    </t>
                </templates>
            </kanban>
        `,
    });

    expect(".o_m2o_avatar").toHaveCount(4);

    expect(".o_m2o_avatar > span.o_resource_icon > i.fa-wrench").toHaveCount(2, {
        message:
            "material icon should be displayed for the first two gantt rows (material resources)",
    });

    expect(".o_field_many2one_avatar_resource img").toHaveCount(2);
    expect(
        queryFirst(
            ".o_kanban_record:nth-of-type(3) .o_field_many2one_avatar_resource img",
        ).getAttribute("data-src"),
    ).toBe("/web/image/resource.resource/3/avatar_128", {
        message:
            "There should be the ID 3 in the URL as it is the one of resource 'Marie'",
    });
    expect(
        queryFirst(
            ".o_kanban_record:nth-of-type(4) .o_field_many2one_avatar_resource img",
        ).getAttribute("data-src"),
    ).toBe("/web/image/resource.resource/4/avatar_128", {
        message:
            "There should be the ID 4 in the URL as it is the one of resource 'Pierre'",
    });

    await click(".o_kanban_record:nth-of-type(1) .o_m2o_avatar i");
    await animationFrame();
    expect(".o_avatar_card").toHaveCount(0);

    await click(".o_kanban_record:nth-of-type(2) .o_m2o_avatar i");
    await animationFrame();
    expect(".o_avatar_card").toHaveCount(1);
    expect(".o_avatar_card .o_avatar > img").toHaveCount(0, {
        message: "There should not be any avatar for material resource",
    });
    expect(".o_avatar_card_buttons button").toHaveCount(0);
    expect(".o_avatar_card .o_resource_roles_tags .o_tag").toHaveCount(2, {
        message: "Roles should be listed in the card",
    });

    await click(".o_kanban_record:nth-of-type(3) .o_m2o_avatar img");
    await animationFrame();
    expect(".o_card_user_infos span:first").toHaveText("Marie");

    await click(".o_kanban_record:nth-of-type(4) .o_m2o_avatar img");
    await animationFrame();
    expect(".o_card_user_infos span:first").toHaveText("Pierre");
});

test("Employee avatar in Gantt view", async () => {
    mockDate("2023-11-08 8:00:00", 0);
    onRpc("gantt_resource_work_interval", () => [
        {
            1: [
                ["2022-10-10 06:00:00", "2022-10-10 10:00:00"],
                ["2022-10-11 06:00:00", "2022-10-11 10:00:00"],
                ["2022-10-11 11:00:00", "2022-10-11 12:00:00"],
                ["2022-10-12 06:00:00", "2022-10-12 10:00:00"],
                ["2022-10-12 11:00:00", "2022-10-12 13:00:00"],
                ["2022-10-13 06:00:00", "2022-10-13 10:00:00"],
                ["2022-10-13 11:00:00", "2022-10-13 14:00:00"],
                ["2022-10-14 06:00:00", "2022-10-14 10:00:00"],
                ["2022-10-14 11:00:00", "2022-10-14 15:00:00"],
            ],
        },
    ]);
    onRpc("get_gantt_data", ({ kwargs, parent }) => {
        const result = parent();
        expect(kwargs.progress_bar_fields).toEqual(["resource_id"]);
        result.progress_bars.resource_id = {
            1: {
                value: 100,
                max_value: 100,
                resource_type: "material",
                resource_color: 1,
                has_several_roles: false,
                employee_id: false,
                work_intervals: [
                    ["2022-10-10 06:00:00", "2022-10-10 10:00:00"],
                    ["2022-10-11 06:00:00", "2022-10-11 10:00:00"],
                    ["2022-10-11 11:00:00", "2022-10-11 12:00:00"],
                    ["2022-10-12 06:00:00", "2022-10-12 10:00:00"],
                    ["2022-10-12 11:00:00", "2022-10-12 13:00:00"],
                    ["2022-10-13 06:00:00", "2022-10-13 10:00:00"],
                    ["2022-10-13 11:00:00", "2022-10-13 14:00:00"],
                    ["2022-10-14 06:00:00", "2022-10-14 10:00:00"],
                    ["2022-10-14 11:00:00", "2022-10-14 15:00:00"],
                ],
            },
            2: {
                value: 100,
                max_value: 100,
                resource_type: "material",
                resource_color: 1,
                has_several_roles: true,
                employee_id: false,
            },
            3: {
                value: 100,
                max_value: 100,
                resource_type: "human",
                resource_color: false,
                has_several_roles: false,
                employee_id: 1,
            },
            4: {
                value: 100,
                max_value: 100,
                resource_type: "human",
                resource_color: false,
                has_several_roles: false,
                employee_id: 2,
            },
        };
        return result;
    });
    await mountView({
        resModel: "planning.slot",
        type: "gantt",
        arch: `<gantt js_class="planning_gantt" date_start="start_datetime" date_stop="end_datetime" progress_bar="resource_id"/>`,
        groupBy: ["resource_id"],
    });
    expect(".o_gantt_row_title .o_avatar").toHaveCount(4);
    expect(".o_avatar .o_resource_icon .fa-wrench").toHaveCount(2, {
        message:
            "material icon should be displayed for the first two gantt rows (material resources)",
    });
    expect(".o_gantt_row_title .o_avatar img").toHaveCount(2, {
        message:
            "avatar should be displayed for the third and fourth gantt rows (human resources)",
    });
    expect(
        queryAll(".o_gantt_row_title .o_avatar img")[1].getAttribute("data-src"),
    ).toBe("/web/image/resource.resource/4/avatar_128", {
        message:
            "avatar of the employee associated to the human resource should be displayed on fourth row",
    });

    await click(".o_avatar .o_resource_icon .fa-wrench");
    await animationFrame();
    expect(".o_avatar_card").toHaveCount(0);

    await click(queryAll(".o_avatar .o_resource_icon .fa-wrench")[1]);
    await animationFrame();
    expect(".o_avatar_card").toHaveCount(1);
    expect(".o_avatar_card .o_avatar > img").toHaveCount(0, {
        message: "There should not be any avatar for material resource",
    });
    expect(".o_avatar_card_buttons button").toHaveCount(0);
    expect(".o_avatar_card .o_resource_roles_tags .o_tag").toHaveCount(2, {
        message: "Roles should be listed in the card",
    });

    await click(".o_gantt_row_title .o_avatar img");
    await animationFrame();
    expect(".o_card_user_infos span:first").toHaveText("Marie");
    expect(".o_avatar_card").toHaveCount(1, {
        message: "Only one popover resource card should be opened at a time",
    });

    await click(queryAll(".o_gantt_row_title .o_avatar img")[1]);
    await animationFrame();
    expect(".o_card_user_infos span:first").toHaveText("Pierre");
    expect(".o_avatar_card").toHaveCount(1, {
        message: "Only one popover resource card should be opened at a time",
    });
});
