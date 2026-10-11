import { describe, expect, test } from "@odoo/hoot";
import { animationFrame } from "@odoo/hoot-mock";
import {
    contains,
    makeMockServer,
    mountView,
    onRpc,
} from "@web/../tests/web_test_helpers";

import { definePlanningHolidaysModels } from "./planning_holidays_test_helpers.js";

describe.current.tags("desktop");
definePlanningHolidaysModels();

test("many2one_avatar_resource widget in list view with time-off idle", async () => {
    const { env } = await makeMockServer();

    const [lucindaPartnerId, cardenioPartnerID] = env["res.partner"].create([
        { name: "Lucinda" },
        { name: "Cardenio" },
    ]);

    const [lucindaUserId, cardenioUserId] = env["res.users"].create([
        {
            name: "Lucinda",
            partner_id: lucindaPartnerId,
            im_status: "leave_online",
        },
        {
            name: "Cardenio",
            partner_id: cardenioPartnerID,
            im_status: "leave_away",
        },
    ]);

    const [resDoro, resFer, resluci, resCar] = env["resource.resource"].create([
        {
            name: "Dorothea",
            type: "human",
        },
        {
            name: "Fernando",
            type: "human",
        },
        {
            name: "Lucinda",
            type: "human",
            user_id: lucindaUserId,
        },
        {
            name: "Cardenio",
            type: "human",
            user_id: cardenioUserId,
        },
    ]);

    const employeeDorotheaData = {
        name: "Dorothea",
        hr_icon_display: "presence_holiday_present",
        show_hr_icon_display: true,
    };
    const employeeFernandoData = {
        name: "Fernando",
        hr_icon_display: "presence_holiday_absent",
        show_hr_icon_display: true,
    };
    const employeeLucindaData = {
        name: "Lucinda",
        user_id: lucindaUserId,
        partner_id: lucindaPartnerId,
    };
    const employeeCardenioData = {
        name: "Cardenio",
        user_id: cardenioUserId,
        partner_id: cardenioPartnerID,
    };
    env["hr.employee"].create([
        { ...employeeDorotheaData, resource_id: resDoro },
        { ...employeeFernandoData, resource_id: resFer },
        { ...employeeLucindaData, resource_id: resluci },
        { ...employeeCardenioData, resource_id: resCar },
    ]);
    env["resource.resource"]._applyComputesAndValidate();

    env["hr.employee"].create([
        employeeDorotheaData,
        employeeFernandoData,
        employeeLucindaData,
        employeeCardenioData,
    ]);

    env["planning.slot"].create([
        {
            display_name: "Planning slot Dorothea",
            resource_id: resDoro,
            resource_type: "human",
            user_id: false,
        },
        {
            display_name: "Planning slot Fernando",
            resource_id: resFer,
            resource_type: "human",
            user_id: false,
        },
        {
            display_name: "Planning Slot Lucinda",
            resource_id: resluci,
            resource_type: "human",
            user_id: lucindaUserId,
        },
        {
            display_name: "Planning Slot Cardenio",
            resource_id: resCar,
            resource_type: "human",
            user_id: cardenioUserId,
        },
    ]);
    onRpc("has_group", () => false);
    onRpc("resource.resource", "get_avatar_card_data", (params) => {
        const resourceIdArray = params.args[0];
        const resourceId = resourceIdArray[0];
        const resources = env["resource.resource"].search_read([
            ["id", "=", resourceId],
        ]);
        const result = resources.map((resource) => ({
            name: resource.name,
            employee_id: resource.employee_id,
            user_id: resource.user_id,
            show_hr_icon_display: resource.show_hr_icon_display,
            hr_icon_display: resource.hr_icon_display,
            im_status: resource.im_status,
        }));
        return result;
    });
    await mountView({
        type: "list",
        resModel: "planning.slot",
        arch: `
        <list>
            <field name="display_name"/>
            <field name="resource_id" widget="many2one_avatar_resource"/>
        </list>`,
    });

    await contains(".o_m2o_avatar > img").click();
    await animationFrame();
    expect(".o_card_user_infos span").toHaveText("Dorothea");
    expect(".o_employee_presence_status .fa-plane.text-success").toHaveCount(1, {
        message: "The idle icon of a present employee on leave should be a green plane",
    });

    await contains(".o_m2o_avatar:eq(1) > img").click();
    await animationFrame();
    expect(".o_card_user_infos span").toHaveText("Fernando");
    expect(".o_employee_presence_status .fa-plane.text-warning").toHaveCount(1, {
        message:
            "The idle icon of an absent employee on leave should be an orange plane",
    });

    await contains(".o_m2o_avatar:eq(2) > img").click();
    await animationFrame();
    expect(".o_card_user_infos span").toHaveText("Lucinda");
    expect(".o_user_im_status .fa-plane.text-success").toHaveCount(1, {
        message: "The idle icon of a connected user on leave should be a green plane",
    });

    await contains(".o_m2o_avatar:eq(3) > img").click();
    await animationFrame();
    expect(".o_card_user_infos span").toHaveText("Cardenio");
    expect(".o_user_im_status .fa-plane.text-warning").toHaveCount(1, {
        message: "The idle icon of a afk user on leave should be an orange plane",
    });
});
