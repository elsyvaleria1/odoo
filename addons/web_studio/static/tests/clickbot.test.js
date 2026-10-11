import { describe, expect, test } from "@odoo/hoot";
import { animationFrame, Deferred } from "@odoo/hoot-mock";
import { Component, useProps, xml } from "@odoo/owl";
import {
    mountWithCleanup,
    onRpc,
    patchWithCleanup,
} from "@web/../tests/web_test_helpers";
import { browser } from "@web/core/browser/browser";
import { registry } from "@web/core/registry";
import { ControlPanel } from "@web/search/control_panel/control_panel";
import { SearchBar } from "@web/search/search_bar/search_bar";
import { SUCCESS_SIGNAL } from "@web/webclient/clickbot/clickbot";
import { WebClient } from "@web/webclient/webclient";

import { defineStudioEnvironment } from "./studio_tests_context.js";

describe.current.tags("desktop").timeout(10000);

defineStudioEnvironment();

test("clickbot clickeverywhere test", async () => {
    const def = new Deferred();

    onRpc("grid_unavailability", () => ({}));

    if (!registry.category("views").contains("grid")) {
        class StubGridController extends Component {
            static template = xml`
                <div class="o_grid_view">
                    <ControlPanel>
                        <t t-set-slot="layout-actions">
                            <SearchBar />
                        </t>
                    </ControlPanel>
                </div>`;
            static components = { ControlPanel, SearchBar };
            static props = null;
            props = useProps(this.constructor.props);
        }
        registry.category("views").add("grid", {
            type: "grid",
            Controller: StubGridController,
        });
    }

    patchWithCleanup(browser, {
        console: {
            log: (msg) => {
                expect.step(msg);
                if (msg === SUCCESS_SIGNAL) {
                    def.resolve();
                }
            },
            error: (msg) => {
                expect.step(msg);
                def.resolve();
            },
        },
    });

    const webClient = await mountWithCleanup(WebClient);
    patchWithCleanup(odoo, {
        info: {
            isEnterprise: 1,
        },
        __WOWL_DEBUG__: { root: webClient },
    });
    await animationFrame();

    window.clickEverywhere();
    await def;
    expect.verifySteps([
        "Testing app menu: app_1",
        "Testing menu Partners 1 app_1",
        'Clicking on: menu item "Partners 1"',
        "Clicking on: entering studio",
        "Clicking on: leaving studio",
        "Clicking on: search bar menu dropdown",
        "Testing 0 filters",
        "Testing view switch: list",
        "Clicking on: list view switcher",
        "Clicking on: entering studio",
        "Clicking on: leaving studio",
        "Clicking on: search bar menu dropdown",
        "Testing 0 filters",
        "Testing view switch: grid",
        "Clicking on: grid view switcher",
        "Clicking on: entering studio",
        "Clicking on: leaving studio",
        "Clicking on: search bar menu dropdown",
        "Testing 0 filters",
        "Testing view switch: pivot",
        "Clicking on: pivot view switcher",
        "Clicking on: entering studio",
        "Clicking on: leaving studio",
        "Clicking on: search bar menu dropdown",
        "Testing 0 filters",
        "Testing menu Partners 11 menu_11",
        'Clicking on: menu item "Partners 11"',
        "Clicking on: entering studio",
        "Clicking on: leaving studio",
        "Clicking on: search bar menu dropdown",
        "Testing 0 filters",
        "Testing view switch: list",
        "Clicking on: list view switcher",
        "Clicking on: entering studio",
        "Clicking on: leaving studio",
        "Clicking on: search bar menu dropdown",
        "Testing 0 filters",
        "Testing view switch: grid",
        "Clicking on: grid view switcher",
        "Clicking on: entering studio",
        "Clicking on: leaving studio",
        "Clicking on: search bar menu dropdown",
        "Testing 0 filters",
        "Testing view switch: pivot",
        "Clicking on: pivot view switcher",
        "Clicking on: entering studio",
        "Clicking on: leaving studio",
        "Clicking on: search bar menu dropdown",
        "Testing 0 filters",
        "Testing menu Partners 12 menu_12",
        'Clicking on: menu item "Partners 12"',
        "Clicking on: entering studio",
        "Clicking on: leaving studio",
        "Clicking on: search bar menu dropdown",
        "Testing 0 filters",
        "Testing view switch: kanban",
        "Clicking on: kanban view switcher",
        "Clicking on: entering studio",
        "Clicking on: leaving studio",
        "Clicking on: search bar menu dropdown",
        "Testing 0 filters",
        "Testing view switch: grid",
        "Clicking on: grid view switcher",
        "Clicking on: entering studio",
        "Clicking on: leaving studio",
        "Clicking on: search bar menu dropdown",
        "Testing 0 filters",
        "Clicking on: home menu toggle button",
        "Testing app menu: app_2",
        "Testing menu Ponies app_2",
        'Clicking on: menu item "Ponies"',
        "Clicking on: entering studio",
        "Clicking on: leaving studio",
        "Clicking on: search bar menu dropdown",
        "Testing 1 filters",
        'Clicking on: filter "apple"',
        "Clicking on: home menu toggle button",
        "Testing app menu: app_3",
        "Testing menu Dogs app_3",
        'Clicking on: menu item "Dogs"',
        "Clicking on: entering studio",
        "Clicking on: leaving studio",
        "Clicking on: search bar menu dropdown",
        "Testing 0 filters",
        "Testing view switch: kanban",
        "Clicking on: kanban view switcher",
        "Clicking on: entering studio",
        "Clicking on: leaving studio",
        "Clicking on: search bar menu dropdown",
        "Testing 0 filters",
        "Clicking on: home menu toggle button",
        "Testing app menu: app_4",
        "Testing menu Settings app_4",
        'Clicking on: menu item "Settings"',
        "Clicking on: search bar menu dropdown",
        "Testing 0 filters",
        "Successfully tested 4 apps",
        "Successfully tested 2 menus",
        "Successfully tested 0 modals",
        "Successfully tested 1 filters",
        "Successfully tested 14 views in Studio",
        SUCCESS_SIGNAL,
    ]);
});
