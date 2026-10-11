import { ControlPanelButtons } from "@mrp_workorder/mrp_display/control_panel";
import { describe, expect, test } from "@odoo/hoot";
import { animationFrame } from "@odoo/hoot-mock";
import { Component, useProps, xml } from "@odoo/owl";
import { makeMockEnv, mountWithCleanup } from "@web/../tests/web_test_helpers";

describe.current.tags("desktop");

const WORKCENTERS = [
    { id: 1, display_name: "Assembly Line 1" },
    { id: 2, display_name: "Assembly Line 2" },
    { id: 3, display_name: "Packing Station" },
    { id: 4, display_name: "Quality Control" },
    { id: 5, display_name: "Shipping Bay" },
];

class Parent extends Component {
    static components = { ControlPanelButtons };
    static props = null;
    static template = xml`
        <div t-attf-style="width: {{this.props.width}}px">
            <ControlPanelButtons
                activeWorkcenter="0"
                productionCount="0"
                selectWorkcenter="() => {}"
                toggleWorkcenter="() => {}"
                workcenters="this.props.workcenters"
                workorders="[]"
                relevantCount="0"
                adminWorkorders="[]"
                hideNewWorkcenterButton="false"
            />
        </div>
    `;
    props = useProps(this.constructor.props);
}

async function mountBar(width) {
    await makeMockEnv();
    await mountWithCleanup(Parent, { props: { width, workcenters: WORKCENTERS } });
    await animationFrame();
    await animationFrame();
}

test("every workcenter stays on the bar when they all fit", async () => {
    await mountBar(2000);

    expect(".o_work_center_btn").toHaveCount(WORKCENTERS.length);
    expect(".o_work_center_dropdown_toggle").toHaveCount(0);
});

test("workcenters that do not fit move into the overflow dropdown", async () => {
    await mountBar(220);

    expect(".o_work_center_dropdown_toggle").toHaveCount(1);
    const inline = document.querySelectorAll(".o_work_centers > .o_work_center_btn");
    expect(inline.length).toBeLessThan(WORKCENTERS.length);
});

test("the bar keeps rendering its own buttons rather than relocating DOM nodes", async () => {
    await mountBar(220);

    const inline = document.querySelectorAll(".o_work_centers > .o_work_center_btn");
    expect(inline.length).toBeGreaterThan(0);
    for (const el of inline) {
        expect(el.classList.contains("dropdown-item")).toBe(false);
    }
});
