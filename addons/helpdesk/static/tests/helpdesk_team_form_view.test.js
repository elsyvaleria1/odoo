import { defineHelpdeskModels } from "@helpdesk/../tests/helpdesk_test_helpers";
import { describe, expect, test } from "@odoo/hoot";
import { click } from "@odoo/hoot-dom";
import { animationFrame } from "@odoo/hoot-mock";
import {
    clickSave,
    fieldInput,
    mockService,
    mountView,
    onRpc,
} from "@web/../tests/web_test_helpers";

import { HelpdeskTeam } from "./mock_server/mock_models/helpdesk_team.js";

describe.current.tags("desktop");
defineHelpdeskModels();

const formViewArch = `
   <form js_class="helpdesk_team_form">
        <sheet>
            <group>
                <field name="name"/>
                <field name="helpdesk_use_sla"/>
                <field name="helpdesk_use_alias"/>
                <field name="use_helpdesk_timesheet"/>
            </group>
        </sheet>
    </form>
`;

onRpc("team.team", "get_features_enabled", function ({ model, method }) {
    expect.step(method);
    let helpdesk_use_sla = false;
    let use_helpdesk_timesheet = false;
    let helpdesk_use_alias = false;
    for (const record of this.env[model]) {
        if (record.helpdesk_use_sla) {
            helpdesk_use_sla = true;
        }
        if (record.use_helpdesk_timesheet) {
            use_helpdesk_timesheet = true;
        }
        if (record.helpdesk_use_alias) {
            helpdesk_use_alias = true;
        }
    }
    return { helpdesk_use_sla, use_helpdesk_timesheet, helpdesk_use_alias };
});

onRpc("web_save", ({ method }) => expect.step(method));

test("reload the page when helpdesk_use_sla is disabled in all teams", async () => {
    onRpc(({ method, args }) => {
        if (method === "check_modules_to_install") {
            expect.step(method);
            expect(args[0]).toEqual(["helpdesk_use_sla"]);
            return false;
        }
    });
    mockService("action", {
        doAction(action) {
            if (action === "reload_context") {
                expect.step("reload_context");
            }
        },
    });

    await mountView({
        resModel: "team.team",
        type: "form",
        resIds: [1, 2],
        resId: 1,
        arch: formViewArch,
    });

    await click("div[name='helpdesk_use_sla'] input");
    await clickSave();

    expect.verifySteps([
        "get_features_enabled",
        "web_save",
        "get_features_enabled",
        "reload_context",
    ]);
});

test("reload the page when the feature use_timesheet is enabled in one team", async () => {
    onRpc("check_modules_to_install", ({ method, args }) => {
        expect.step(method);
        expect(args[0]).toEqual(["use_helpdesk_timesheet"]);
        return true;
    });
    mockService("action", {
        doAction(action) {
            if (action === "reload_context") {
                expect.step("reload_context");
            }
        },
    });

    await mountView({
        resModel: "team.team",
        type: "form",
        resId: 1,
        arch: formViewArch,
    });

    await fieldInput("use_helpdesk_timesheet").check();
    await clickSave();

    expect.verifySteps([
        "get_features_enabled",
        "check_modules_to_install",
        "web_save",
        "reload_context",
    ]);
});

test("do not reload if the feature is already installed", async () => {
    HelpdeskTeam._records[0].use_helpdesk_timesheet = true;
    onRpc("check_modules_to_install", ({ method, args }) => {
        expect.step(method);
        expect(args[0]).toEqual(["use_helpdesk_timesheet"]);
        return false;
    });
    mockService("action", {
        doAction(action) {
            if (action === "reload_context") {
                expect.step("reload_context");
            }
        },
    });

    await mountView({
        resModel: "team.team",
        type: "form",
        resId: 2,
        arch: formViewArch,
    });

    await fieldInput("use_helpdesk_timesheet").check();
    await clickSave();

    expect.verifySteps([
        "get_features_enabled",
        "check_modules_to_install",
        "web_save",
    ]);
});

test("reload when the feature is disabled in all teams", async () => {
    onRpc("check_modules_to_install", ({ method, args }) => {
        expect.step(method);
        expect(args[0]).toEqual(["helpdesk_use_alias"]);
        return false;
    });
    mockService("action", {
        doAction(action) {
            if (action === "reload_context") {
                expect.step("reload_context");
            }
        },
    });

    await mountView({
        resModel: "team.team",
        type: "form",
        resIds: [1, 2],
        resId: 1,
        arch: formViewArch,
    });

    await click("div[name='helpdesk_use_alias'] input");
    await clickSave();
    await click(".o_pager_next");
    await animationFrame();
    await click("div[name='helpdesk_use_alias'] input");
    await clickSave();

    expect.verifySteps([
        "get_features_enabled",
        "web_save",
        "get_features_enabled",
        "web_save",
        "get_features_enabled",
        "reload_context",
    ]);
});
