// @ts-check

import { beforeEach, disableAnimations, expect, test } from "@odoo/hoot";
import { click, queryOne } from "@odoo/hoot-dom";
import { animationFrame } from "@odoo/hoot-mock";
import { Component, proxy, useProps, xml } from "@odoo/owl";
import { makeMockEnv, mountWithCleanup } from "@web/../tests/web_test_helpers";
import { Offcanvas } from "@web/ui/offcanvas/offcanvas";

beforeEach(async () => {
    disableAnimations();
    await makeMockEnv();
});

class Parent extends Component {
    static components = { Offcanvas };
    static props = null;
    static template = xml`
        <button class="opener" t-on-click="() => this.state.open = true">Open</button>
        <Offcanvas
            open="this.state.open"
            placement="this.props.placement or 'end'"
            onClose="() => this.onClose()"
            class="'panel'"
        >
            <div class="body">content</div>
        </Offcanvas>
    `;
    props = useProps(this.constructor.props);

    /** @type {{ open: boolean }} */
    state;

    setup() {
        this.state = proxy({ open: false });
    }

    onClose() {
        this.state.open = false;
        expect.step("close");
    }
}

test("starts closed and is not in the top layer", async () => {
    await mountWithCleanup(Parent);

    expect(".panel").toHaveCount(1);
    expect(queryOne(".panel").matches(":popover-open")).toBe(false);
});

test("opens into the top layer and takes the show class", async () => {
    await mountWithCleanup(Parent);

    await click(".opener");
    await animationFrame();

    expect(queryOne(".panel").matches(":popover-open")).toBe(true);
    expect(".panel").toHaveClass("show");
});

test("reports a dismissal it did not initiate through onClose", async () => {
    await mountWithCleanup(Parent);

    await click(".opener");
    await animationFrame();
    expect(queryOne(".panel").matches(":popover-open")).toBe(true);

    queryOne(".panel").hidePopover();
    await animationFrame();

    expect.verifySteps(["close"]);
    expect(queryOne(".panel").matches(":popover-open")).toBe(false);
    expect(".panel").not.toHaveClass("show");
});

test("applies the placement class", async () => {
    await mountWithCleanup(Parent, { props: { placement: "start" } });

    expect(".panel").toHaveClass("offcanvas-start");
    expect(".panel").not.toHaveClass("offcanvas-end");
});

test("the panel carries the naming attributes a dialog needs", async () => {
    class Named extends Component {
        static components = { Offcanvas };
        static props = null;
        static template = xml`
            <Offcanvas open="true" id="'panel_id'" ariaLabelledBy="'title_id'" class="'panel'">
                <h5 id="title_id">Operators</h5>
            </Offcanvas>`;
        props = useProps(this.constructor.props);
    }
    await mountWithCleanup(Named);

    const panel = queryOne(".panel");
    expect(panel).toHaveAttribute("id", "panel_id");
    expect(panel).toHaveAttribute("role", "dialog");
    expect(panel).toHaveAttribute("aria-labelledby", "title_id");
    expect(panel).toHaveAttribute("tabindex", "-1");
});

test("aria-label names the panel when there is no title element", async () => {
    class Labelled extends Component {
        static components = { Offcanvas };
        static props = null;
        static template = xml`
            <Offcanvas open="true" ariaLabel="'Your Cart'" class="'panel'">
                <div class="body"/>
            </Offcanvas>`;
        props = useProps(this.constructor.props);
    }
    await mountWithCleanup(Labelled);
    expect(queryOne(".panel")).toHaveAttribute("aria-label", "Your Cart");
});

test("an empty role leaves no role attribute behind", async () => {
    class Roleless extends Component {
        static components = { Offcanvas };
        static props = null;
        static template = xml`
            <Offcanvas open="true" role="''" class="'panel'">
                <div class="body"/>
            </Offcanvas>`;
        props = useProps(this.constructor.props);
    }
    await mountWithCleanup(Roleless);
    expect(queryOne(".panel")).not.toHaveAttribute("role");
});

test("opening the panel moves focus into it", async () => {
    await mountWithCleanup(Parent);
    const opener = queryOne(".opener");
    opener.focus();
    expect(document.activeElement).toBe(opener);

    await click(".opener");
    await animationFrame();
    expect(document.activeElement).toBe(queryOne(".panel"));
});

test("opening does not steal focus from content that already has it", async () => {
    class Autofocusing extends Component {
        static components = { Offcanvas };
        static props = null;
        static template = xml`
            <Offcanvas open="this.state.open" ariaLabel="'Panel'" class="'panel'">
                <button class="inside">Inside</button>
            </Offcanvas>`;
        props = useProps(this.constructor.props);

        /** @type {{ open: boolean }} */
        state;

        setup() {
            this.state = proxy({ open: false });
        }
    }
    const parent = await mountWithCleanup(Autofocusing);
    parent.state.open = true;
    await animationFrame();

    const inside = queryOne(".inside");
    inside.focus();
    expect(document.activeElement).toBe(inside);

    parent.__owl__.render(true);
    await animationFrame();
    expect(document.activeElement).toBe(inside);
});
