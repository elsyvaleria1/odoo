// @ts-check

import { expect, test } from "@odoo/hoot";
import { animationFrame } from "@odoo/hoot-mock";
import { Component, proxy, useProps, xml } from "@odoo/owl";
import { mountWithCleanup } from "@web/../tests/web_test_helpers";
import { SelectionBox } from "@web/views/view_components/selection_box";

function makeRoot() {
    return proxy({
        records: [{ selected: true }, { selected: true }, { selected: false }],
        get selection() {
            expect.step("selection");
            return this.records.filter((record) => record.selected);
        },
        isGrouped: false,
        count: 5,
        hasLimitedCount: false,
        isDomainSelected: false,
        isRecordCountTrustable: true,
        selectDomain() {},
    });
}

test.tags("desktop");
test("the selection is filtered once per render", async () => {
    const root = makeRoot();
    await mountWithCleanup(SelectionBox, { props: { root } });
    expect(".o_selection_box b").toHaveText("2");
    expect.verifySteps(["selection"]);

    root.records[2].selected = true;
    await animationFrame();
    expect(".o_selection_box b").toHaveText("3");
    expect(".o_select_domain").toHaveCount(1);
    expect.verifySteps(["selection"]);
});

test.tags("desktop");
test("a new root prop replaces the counted selection", async () => {
    const plainRoot = (selectedCount) =>
        proxy({
            records: [0, 1, 2].map((index) => ({ selected: index < selectedCount })),
            get selection() {
                return this.records.filter((record) => record.selected);
            },
            isGrouped: false,
            count: 5,
            hasLimitedCount: false,
            isDomainSelected: false,
            isRecordCountTrustable: true,
            selectDomain() {},
        });
    const state = proxy({ root: plainRoot(1) });
    class Parent extends Component {
        static template = xml`<SelectionBox root="this.state.root"/>`;
        static components = { SelectionBox };
        static props = null;
        props = useProps(this.constructor.props);
        state = state;
    }
    await mountWithCleanup(Parent);
    expect(".o_selection_box b").toHaveText("1");
    state.root = plainRoot(3);
    await animationFrame();
    expect(".o_selection_box b").toHaveText("3");
});
