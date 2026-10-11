import { beforeEach, describe, expect, test } from "@odoo/hoot";
import { queryAll, queryFirst } from "@odoo/hoot-dom";
import { animationFrame, mockDate } from "@odoo/hoot-mock";
import { markup } from "@odoo/owl";
import {
    getService,
    mountWithCleanup,
    switchView,
    toggleMenuItem,
    toggleSearchBarMenu,
} from "@web/../tests/web_test_helpers";
import { Domain } from "@web/core/domain";
import { WebClient } from "@web/webclient/webclient";

import { defineGanttModels, Tasks } from "./gantt_mock_models.js";
import { mountGanttView, SELECTORS } from "./web_gantt_test_helpers.js";

describe.current.tags("desktop");

defineGanttModels();
beforeEach(() => mockDate("2018-12-20T08:00:00", +1));

test(`empty grouped gantt with sample="1"`, async () => {
    Tasks._views = {
        gantt: `<gantt date_start="start" date_stop="stop" sample="1"/>`,
    };

    await mountWithCleanup(WebClient);
    await getService("action").doAction({
        res_model: "tasks",
        type: "ir.actions.act_window",
        views: [
            [false, "gantt"],
            [false, "graph"],
        ],
        domain: Domain.FALSE.toList(),
        groupBy: ["project_id"],
    });
    await animationFrame();

    expect(SELECTORS.viewContent).toHaveClass("o_view_sample_data");
    expect(queryAll(SELECTORS.pill).length).toBeGreaterThan(0);
    expect(SELECTORS.noContentHelper).toHaveCount(1);

    const content = queryFirst(SELECTORS.viewContent).innerHTML;
    await switchView("gantt");
    await animationFrame();
    expect(SELECTORS.viewContent).toHaveClass("o_view_sample_data");
    expect(SELECTORS.viewContent).toHaveProperty("innerHTML", content);
    expect(SELECTORS.noContentHelper).toHaveCount(1);
});

test("empty gantt with sample data and default_group_by", async () => {
    Tasks._views = {
        gantt: `<gantt date_start="start" date_stop="stop" sample="1" default_group_by="project_id"/>`,
    };

    await mountWithCleanup(WebClient);
    await getService("action").doAction({
        res_model: "tasks",
        type: "ir.actions.act_window",
        views: [
            [false, "gantt"],
            [false, "graph"],
        ],
        domain: Domain.FALSE.toList(),
    });
    await animationFrame();

    expect(SELECTORS.viewContent).toHaveClass("o_view_sample_data");
    expect(queryAll(SELECTORS.pill).length).toBeGreaterThan(0);
    expect(SELECTORS.noContentHelper).toHaveCount(1);

    const content = queryFirst(SELECTORS.viewContent).innerHTML;
    await switchView("gantt");
    await animationFrame();

    expect(SELECTORS.viewContent).toHaveClass("o_view_sample_data");
    expect(SELECTORS.viewContent).toHaveProperty("innerHTML", content);
    expect(SELECTORS.noContentHelper).toHaveCount(1);
});

test("empty gantt with sample data and default_group_by (switch view)", async () => {
    Tasks._views = {
        gantt: `<gantt date_start="start" date_stop="stop" sample="1" default_group_by="project_id"/>`,
    };

    await mountWithCleanup(WebClient);
    await getService("action").doAction({
        res_model: "tasks",
        type: "ir.actions.act_window",
        views: [
            [false, "gantt"],
            [false, "list"],
        ],
        domain: Domain.FALSE.toList(),
    });
    await animationFrame();

    expect(SELECTORS.viewContent).toHaveClass("o_view_sample_data");
    expect(queryAll(SELECTORS.pill).length).toBeGreaterThan(0);
    expect(SELECTORS.noContentHelper).toHaveCount(1);
    expect(`.o_searchview_facet`).toHaveCount(1);
    expect(`.o_searchview_facet`).toHaveText("Project");
    const content = queryFirst(SELECTORS.viewContent).innerHTML;

    await switchView("list");
    expect(SELECTORS.view).toHaveCount(0);
    expect(`.o_searchview_facet`).toHaveCount(0);

    await switchView("gantt");
    await animationFrame();

    expect(SELECTORS.view).toHaveCount(1);
    expect(`.o_searchview_facet`).toHaveCount(1);
    expect(`.o_searchview_facet`).toHaveText("Project");

    expect(SELECTORS.viewContent).toHaveClass("o_view_sample_data");
    expect(SELECTORS.noContentHelper).toHaveCount(1);
    expect(SELECTORS.viewContent).toHaveProperty("innerHTML", content);
});

test(`empty gantt with sample="1"`, async () => {
    Tasks._views = {
        gantt: `<gantt date_start="start" date_stop="stop" sample="1"/>`,
    };

    await mountWithCleanup(WebClient);
    await getService("action").doAction({
        res_model: "tasks",
        type: "ir.actions.act_window",
        views: [
            [false, "gantt"],
            [false, "graph"],
        ],
        domain: Domain.FALSE.toList(),
    });
    await animationFrame();
    expect(SELECTORS.viewContent).toHaveClass("o_view_sample_data");
    expect(queryAll(SELECTORS.pill).length).toBeGreaterThan(0);
    expect(SELECTORS.noContentHelper).toHaveCount(1);

    const content = queryFirst(SELECTORS.viewContent).innerHTML;

    await switchView("gantt");
    await animationFrame();
    expect(SELECTORS.viewContent).toHaveClass("o_view_sample_data");
    expect(SELECTORS.viewContent).toHaveProperty("innerHTML", content);
    expect(SELECTORS.noContentHelper).toHaveCount(1);
});

test(`non empty gantt with sample="1"`, async () => {
    await mountGanttView({
        resModel: "tasks",
        arch: `<gantt date_start="start" date_stop="stop" default_range="year" sample="1"/>`,
        searchViewArch: `
            <search>
                <filter name="filter" string="False Domain" domain="[(0, '=', 1)]"/>
            </search>
        `,
    });
    expect(SELECTORS.viewContent).not.toHaveClass("o_view_sample_data");
    expect(SELECTORS.cell).toHaveCount(18);
    expect(SELECTORS.pill).toHaveCount(7);
    expect(SELECTORS.noContentHelper).toHaveCount(0);

    await toggleSearchBarMenu();
    await toggleMenuItem("False Domain");
    expect(SELECTORS.viewContent).not.toHaveClass("o_view_sample_data");
    expect(SELECTORS.pill).toHaveCount(0);
    expect(SELECTORS.noContentHelper).toHaveCount(0);
    expect(SELECTORS.cell).toHaveCount(18);
});

test(`non empty grouped gantt with sample="1"`, async () => {
    await mountGanttView({
        resModel: "tasks",
        arch: `<gantt date_start="start" date_stop="stop" default_range="year" sample="1"/>`,
        groupBy: ["project_id"],
        searchViewArch: `
            <search>
                <filter name="filter" string="False Domain" domain="[(0, '=', 1)]"/>
            </search>
        `,
    });
    expect(SELECTORS.viewContent).not.toHaveClass("o_view_sample_data");
    expect(SELECTORS.cell).toHaveCount(36);
    expect(SELECTORS.pill).toHaveCount(7);

    await toggleSearchBarMenu();
    await toggleMenuItem("False Domain");
    expect(SELECTORS.viewContent).not.toHaveClass("o_view_sample_data");
    expect(SELECTORS.pill).toHaveCount(0);
    expect(SELECTORS.noContentHelper).toHaveCount(0);
    expect(SELECTORS.cell).toHaveCount(18);
});

test("no content helper from action when no data and sample mode", async () => {
    Tasks._records = [];
    await mountGanttView({
        resModel: "tasks",
        arch: `<gantt date_start="start" date_stop="stop" sample="1"/>`,
        noContentHelp: markup`<p class="hello">click to add a partner</p>`,
    });
    expect(SELECTORS.noContentHelper).toHaveCount(1);
    expect(`${SELECTORS.noContentHelper} p.hello:contains(add a partner)`).toHaveCount(
        1,
    );
});
