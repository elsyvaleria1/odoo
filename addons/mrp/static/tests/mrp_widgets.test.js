import { openFormView, start, startServer } from "@mail/../tests/mail_test_helpers";
import { defineMrpModels } from "@mrp/../tests/mrp_test_helpers";
import { MrpTimer } from "@mrp/widgets/timer";
import { describe, expect, test } from "@odoo/hoot";
import { advanceTime, animationFrame } from "@odoo/hoot-mock";
import { Component, proxy, useProps, xml } from "@odoo/owl";
import {
    contains,
    mountView,
    mountWithCleanup,
    onRpc,
} from "@web/../tests/web_test_helpers";
import { registry } from "@web/core/registry";

describe.current.tags("desktop");
defineMrpModels();

const formatMinutes = registry.category("formatters").get("mrp_timer");

const LIVE_ARCH = `
    <form>
        <field name="state" invisible="1"/>
        <field name="duration_live" invisible="1"/>
        <field name="duration" widget="mrp_timer" readonly="1"/>
    </form>`;

test("ensure the rendering is based on minutes and seconds", async () => {
    const pyEnv = await startServer();
    const fakeId = pyEnv["res.fake"].create({ duration: 150.5 });
    await start();
    await openFormView("res.fake", fakeId);
    expect(".o_field_mrp_timer").toHaveText("150:30");
});

test("mrp_timer shows the live duration from the record, without an RPC", async () => {
    const pyEnv = await startServer();
    const fakeId = pyEnv["res.fake"].create({
        duration: 10,
        duration_live: 42.5,
        state: "progress",
    });
    onRpc("get_duration", () => {
        expect.step("get_duration");
        return 0;
    });
    await start();
    await openFormView("res.fake", fakeId, { arch: LIVE_ARCH });
    expect(".o_field_mrp_timer").toHaveText("42:30");
    expect.verifySteps([]);
});

test("mrp_timer falls back to the bound field when the record is not in progress", async () => {
    const pyEnv = await startServer();
    const fakeId = pyEnv["res.fake"].create({
        duration: 10,
        duration_live: 42.5,
        state: "done",
    });
    await start();
    await openFormView("res.fake", fakeId, { arch: LIVE_ARCH });
    expect(".o_field_mrp_timer").toHaveText("10:00");
});

test("mrp_timer falls back to get_duration when the view omits duration_live", async () => {
    const pyEnv = await startServer();
    const fakeId = pyEnv["res.fake"].create({ duration: 10, state: "progress" });
    onRpc("get_duration", () => {
        expect.step("get_duration");
        return 42.5;
    });
    await start();
    await openFormView("res.fake", fakeId, {
        arch: `
            <form>
                <field name="state" invisible="1"/>
                <field name="duration" widget="mrp_timer" readonly="1"/>
            </form>`,
    });
    expect(".o_field_mrp_timer").toHaveText("42:30");
    expect.verifySteps(["get_duration"]);
});

test("formatMinutes renders mm:ss and carries a rounded-up second into the minutes", () => {
    expect(formatMinutes(150.5)).toBe("150:30");
    expect(formatMinutes(2.999)).toBe("03:00");
    expect(formatMinutes(0.999)).toBe("01:00");
    expect(formatMinutes(10.0083)).toBe("10:00");
    expect(formatMinutes(0)).toBe("00:00");
    expect(formatMinutes(-2.999)).toBe("-03:00");
    expect(formatMinutes(false)).toBe("");
});

test("MrpTimer ticks while ongoing and cleans up (no leaked timers)", async () => {
    class Parent extends Component {
        static components = { MrpTimer };
        static props = {};
        static template = xml`<div class="test-timer"><MrpTimer value="0" ongoing="true"/></div>`;
        props = useProps(this.constructor.props);
    }
    await mountWithCleanup(Parent);
    expect(".test-timer").toHaveText("00:00");
    await advanceTime(3000);
    expect(".test-timer").toHaveText("00:03");
});

test("MrpTimer stays frozen when not ongoing", async () => {
    class Parent extends Component {
        static components = { MrpTimer };
        static props = {};
        static template = xml`<div class="test-timer"><MrpTimer value="5" ongoing="false"/></div>`;
        props = useProps(this.constructor.props);
    }
    await mountWithCleanup(Parent);
    expect(".test-timer").toHaveText("05:00");
    await advanceTime(30000);
    expect(".test-timer").toHaveText("05:00");
});

test("MrpTimer counts elapsed time, not ticks, across a stalled minute", async () => {
    class Parent extends Component {
        static components = { MrpTimer };
        static props = {};
        static template = xml`<div class="test-timer"><MrpTimer value="0" ongoing="true"/></div>`;
        props = useProps(this.constructor.props);
    }
    await mountWithCleanup(Parent);
    await advanceTime(60000);
    expect(".test-timer").toHaveText("01:00");
});

test("MrpTimer shows a new value while stopped and restarts from it", async () => {
    class Parent extends Component {
        static components = { MrpTimer };
        static props = {};
        static template = xml`<div class="test-timer"><MrpTimer value="this.state.value" ongoing="this.state.ongoing"/></div>`;
        props = useProps(this.constructor.props);
        setup() {
            this.state = proxy({ value: 5, ongoing: false });
        }
    }
    const parent = await mountWithCleanup(Parent);
    expect(".test-timer").toHaveText("05:00");
    parent.state.value = 7;
    await animationFrame();
    expect(".test-timer").toHaveText("07:00");
    parent.state.ongoing = true;
    await animationFrame();
    await advanceTime(2000);
    expect(".test-timer").toHaveText("07:02");
    parent.state.value = 20;
    await animationFrame();
    expect(".test-timer").toHaveText("20:00");
});

test("a row's state dropdown changes only that row unless the row is selected", async () => {
    const pyEnv = await startServer();
    const [first, second] = pyEnv["res.fake"].create([
        { state: "ready" },
        { state: "ready" },
    ]);
    onRpc("has_group", () => true);
    onRpc("set_state", ({ args }) => {
        expect.step(args[0]);
        return true;
    });
    await start();
    await mountView({
        resModel: "res.fake",
        type: "list",
        arch: `<list><field name="state"/><widget name="wo_list_view_dropdown"/></list>`,
    });
    await contains(".o_data_row:eq(0) .o_list_record_selector input").click();
    await contains(".o_data_row:eq(1) .o_widget_wo_list_view_dropdown button").click();
    await contains(".o-dropdown-item:contains(In Progress)").click();
    expect.verifySteps([[second]]);
    await contains(".o_data_row:eq(0) .o_widget_wo_list_view_dropdown button").click();
    await contains(".o-dropdown-item:contains(In Progress)").click();
    expect.verifySteps([[first]]);
});
