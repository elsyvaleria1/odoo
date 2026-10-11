// @ts-check

import { after, beforeEach, expect, test } from "@odoo/hoot";
import { queryAll, queryOne, queryRect, resize } from "@odoo/hoot-dom";
import { animationFrame } from "@odoo/hoot-mock";
import { onWillDestroy } from "@odoo/owl";
import {
    contains,
    defineModels,
    fields,
    models,
    mountView,
    patchWithCleanup,
    webModels,
} from "@web/../tests/web_test_helpers";
import { ListRecordRow } from "@web/views/list/list_record_row";

const ROW = 36;
const SCREENFUL = 10;

class Line extends models.Model {
    name = fields.Char();
    partner_id = fields.Many2one({ relation: "partner" });

    _records = Array.from({ length: 12 }, (_, i) => ({
        id: i + 1,
        name: `line ${i + 1}`,
        partner_id: 1,
    }));
}

class Partner extends models.Model {
    name = fields.Char();
    kind = fields.Char();
    company_id = fields.Many2one({ relation: "res.company" });
    line_ids = fields.One2many({ relation: "line", relation_field: "partner_id" });

    _records = Array.from({ length: 64 }, (_, i) => ({
        id: i + 1,
        name: `partner ${String(i + 1).padStart(2, "0")}`,
        kind: i < 40 ? "a" : "b",
        company_id: 1,
        line_ids: i === 0 ? Array.from({ length: 12 }, (_, line) => line + 1) : [],
    }));
}

const { ResCompany } = webModels;

defineModels([...Object.values(webModels), Partner, Line]);

const ARCH = `<list><field name="name"/></list>`;

function trackRows() {
    const rows = { built: 0, destroyed: 0 };
    patchWithCleanup(ListRecordRow.prototype, {
        setup() {
            super.setup();
            rows.built++;
            onWillDestroy(() => {
                rows.destroyed++;
            });
        },
    });
    return rows;
}

async function untilBuilt() {
    for (let frame = 0; frame < 20; frame++) {
        await animationFrame();
    }
}

beforeEach(() => resize({ height: SCREENFUL * ROW }));

test.tags("desktop");
test("a list builds the rows of one screen first, then the rest of its page", async () => {
    const rows = trackRows();
    await mountView({ resModel: "partner", type: "list", arch: ARCH });
    expect(".o_data_row").toHaveCount(SCREENFUL);
    expect(".o_data_row:first").toHaveText("partner 01");

    await untilBuilt();
    expect(".o_data_row").toHaveCount(64);
    expect(queryAll(".o_data_row").at(-1)).toHaveText("partner 64");
    expect(rows).toEqual({ built: 64, destroyed: 0 });
});

test.tags("desktop");
test("the rows built later take nothing from the page: selection and count cover it at once", async () => {
    await mountView({ resModel: "partner", type: "list", arch: ARCH });
    expect(".o_data_row").toHaveCount(SCREENFUL);
    expect(".o_pager_value").toHaveText("1-64");

    await contains("thead .o_list_record_selector input").click();
    expect(".o_selection_box").toHaveText(/64\s+selected/);
});

test.tags("desktop");
test("a new page starts at one screen again", async () => {
    await mountView({
        resModel: "partner",
        type: "list",
        arch: `<list limit="30"><field name="name"/></list>`,
    });
    await untilBuilt();
    expect(".o_data_row").toHaveCount(30);

    const rows = trackRows();
    await contains(".o_pager_next").click();
    expect(".o_data_row").toHaveCount(SCREENFUL);
    expect(".o_data_row:first").toHaveText("partner 31");

    await untilBuilt();
    expect(".o_data_row").toHaveCount(30);
    expect(rows.built).toBe(30);
});

test.tags("desktop");
test("a list scrolled back to an offset builds what that offset shows", async () => {
    await mountView({
        resModel: "partner",
        type: "list",
        arch: ARCH,
        state: { rendererScrollPositions: { left: 0, top: 20 * ROW } },
    });
    expect(".o_data_row").toHaveCount(SCREENFUL + 20);
});

test.tags("desktop");
test("a column sized from the text of its rows keeps its width while the rest is built", async () => {
    ResCompany._records = [{ id: 1, name: "AGM" }];
    await mountView({
        resModel: "partner",
        type: "list",
        arch: `<list><field name="name"/><field name="company_id"/></list>`,
    });
    expect(".o_data_row").toHaveCount(SCREENFUL);
    const widths = queryAll("th").map((th) => queryRect(th).width);
    let computations = 0;
    const observer = new MutationObserver((mutations) => {
        computations += mutations.filter((mutation) =>
            mutation.oldValue?.includes("o_list_computing_widths"),
        ).length;
    });
    observer.observe(queryOne(".o_list_table"), {
        attributeFilter: ["class"],
        attributeOldValue: true,
    });
    after(() => observer.disconnect());

    await untilBuilt();
    expect(".o_data_row").toHaveCount(64);
    expect(queryAll("th").map((th) => queryRect(th).width)).toEqual(widths);
    expect(computations).toBe(0);
});

test.tags("desktop");
test("a label only a later row shows widens its column once that row is built", async () => {
    ResCompany._records = [
        { id: 1, name: "AGM" },
        { id: 2, name: "Agro Marin Agricultural Operations" },
    ];
    Partner._records[59].company_id = 2;
    await mountView({
        resModel: "partner",
        type: "list",
        arch: `<list><field name="name"/><field name="company_id"/></list>`,
    });
    const width = queryRect('th[data-name="company_id"]').width;

    await untilBuilt();
    expect(queryRect('th[data-name="company_id"]').width).toBeGreaterThan(width + 100);
    const cell = queryOne('.o_data_row:eq(59) .o_data_cell[name="company_id"]');
    const text = cell.querySelector(".text-truncate") || cell;
    expect(text.scrollWidth).toBeLessThan(text.clientWidth + 2);
});

test.tags("desktop");
test("an opened group builds one screen of its rows first", async () => {
    await mountView({
        resModel: "partner",
        type: "list",
        arch: ARCH,
        groupBy: ["kind"],
    });
    await contains(".o_group_header:first").click();
    expect(".o_data_row").toHaveCount(SCREENFUL);

    await untilBuilt();
    expect(".o_data_row").toHaveCount(40);
});

test.tags("desktop");
test("a list embedded in a form builds all its rows at once", async () => {
    await mountView({
        resModel: "partner",
        type: "form",
        resId: 1,
        arch: `
            <form>
                <field name="line_ids">
                    <list><field name="name"/></list>
                </field>
            </form>`,
    });
    expect(".o_data_row").toHaveCount(12);
});
