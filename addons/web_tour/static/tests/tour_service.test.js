/** @odoo-module native */

import { afterEach, beforeEach, describe, expect, test } from "@odoo/hoot";
import { advanceTime, animationFrame } from "@odoo/hoot-dom";
import { Component, useProps, xml } from "@odoo/owl";
import {
    clearRegistry,
    mountWithCleanup,
    onRpc,
    patchWithCleanup,
} from "@web/../tests/web_test_helpers";
import { browser } from "@web/core/browser/browser";
import { registry } from "@web/core/registry";
import { Macro } from "@web/core/utils/macro";
import { session } from "@web/session";
import { tourState } from "@web_tour/js/tour_state";

describe.current.tags("desktop");

const tourRegistry = registry.category("web_tour.tours");
let macro;

class Root extends Component {
    static components = {};
    static template = xml`<t><button class="button0">Button 0</button></t>`;
    static props = null;
    props = useProps(this.constructor.props);
}

async function pump(times = 6) {
    for (let i = 0; i < times; i++) {
        await animationFrame();
        await advanceTime(265);
    }
}

beforeEach(() => {
    clearRegistry(tourRegistry);
    tourState.clear();
    patchWithCleanup(Macro.prototype, {
        start() {
            super.start(...arguments);
            macro = this;
        },
    });
});

afterEach(() => {
    macro?.stop();
    macro = undefined;
    tourState.clear();
    browser.location.search = "";
});

describe("resuming a tour the registry does not have yet", () => {
    test("a tour registered after the service started still resumes", async () => {
        tourState.setCurrentTour("late_tour");
        tourState.setCurrentConfig({ mode: "auto", stepDelay: 0 });
        tourState.setCurrentIndex(0);

        await mountWithCleanup(Root);
        expect(tourRegistry.contains("late_tour")).toBe(false);

        tourRegistry.add("late_tour", {
            steps: () => [
                {
                    trigger: ".button0",
                    run() {
                        expect.step("late tour ran");
                    },
                },
            ],
        });
        await pump();
        expect.verifySteps(["late tour ran"]);
    });

    test("a manual tour absent from this page keeps its state and stays quiet", async () => {
        patchWithCleanup(browser.console, {
            error: (msg) => expect.step(`error: ${msg}`),
        });
        patchWithCleanup(session, { tour_enabled: true });
        tourState.setCurrentTour("elsewhere_tour");
        tourState.setCurrentConfig({ mode: "manual", stepDelay: 0 });

        await mountWithCleanup(Root);
        await advanceTime(31000);
        await animationFrame();

        expect(tourState.getCurrentTour()).toBe("elsewhere_tour");
        expect.verifySteps([]);
    });

    test("a tour nobody can produce is reported and its state dropped", async () => {
        patchWithCleanup(browser.console, {
            error: (msg) => expect.step(`error: ${msg}`),
        });
        tourState.setCurrentTour("no_such_tour");
        tourState.setCurrentConfig({ mode: "auto", stepDelay: 0 });

        await mountWithCleanup(Root);
        await advanceTime(31000);
        await animationFrame();

        expect(tourState.getCurrentTour()).toBe(null);
        expect.verifySteps([
            'error: Tour "no_such_tour" was resumed but is registered nowhere' +
                " (web_tour.tours registry). Its saved state has been dropped.",
        ]);
    });
});

describe("starting a tour from a ?tour= url param", () => {
    test("resumes the tour once, not twice", async () => {
        patchWithCleanup(session, { tour_enabled: true });
        browser.location.search = "?tour=url_tour";
        onRpc("web_tour.tour", "get_tour_json_by_name", () => {
            expect.step("get_tour_json_by_name");
            return {
                name: "url_tour",
                steps: [{ trigger: ".button0", run: "click" }],
            };
        });

        await mountWithCleanup(Root);
        await pump();

        expect.verifySteps(["get_tour_json_by_name"]);
        expect(".o_tour_pointer").toHaveCount(1);
    });

    test("wins over a tour left mid-run in localStorage", async () => {
        patchWithCleanup(session, { tour_enabled: true });
        browser.location.search = "?tour=url_tour";
        tourState.setCurrentTour("stale_tour");
        tourState.setCurrentConfig({ mode: "manual", stepDelay: 0 });
        tourState.setCurrentIndex(0);
        tourRegistry.add("stale_tour", {
            steps: () => [
                {
                    trigger: ".button0",
                    run() {
                        expect.step("stale tour ran");
                    },
                },
            ],
        });
        onRpc("web_tour.tour", "get_tour_json_by_name", ({ args }) => {
            expect.step(`fetched ${args[0]}`);
            return {
                name: "url_tour",
                steps: [{ trigger: ".button0", run: "click" }],
            };
        });

        await mountWithCleanup(Root);
        await pump();

        expect.verifySteps(["fetched url_tour"]);
        expect(tourState.getCurrentTour()).toBe("url_tour");
    });
});
