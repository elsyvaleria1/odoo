// @ts-check

import { beforeEach, expect, test } from "@odoo/hoot";
import { queryAll, resize } from "@odoo/hoot-dom";
import { animationFrame } from "@odoo/hoot-mock";
import { onMounted, onWillDestroy } from "@odoo/owl";
import {
    defineModels,
    fields,
    getMockEnv,
    models,
    mountView,
    patchWithCleanup,
    webModels,
} from "@web/../tests/web_test_helpers";
import { scrollSymbol } from "@web/core/action_hook";
import { browser } from "@web/core/browser/browser";
import { KanbanRecord } from "@web/views/kanban/kanban_record";
import {
    getMeasuredCardExtents,
    KanbanRenderer,
} from "@web/views/kanban/kanban_renderer";

// what the renderer counts for a card it has never measured
const PITCH = 48;
const CARD_WIDTH = 200;

class Card extends models.Model {
    name = fields.Char();
    stage = fields.Char();

    _records = Array.from({ length: 60 }, (_, i) => ({
        id: i + 1,
        name: `card ${String(i + 1).padStart(2, "0")}`,
        stage: i < 40 ? "new" : "done",
    }));
}

defineModels([...Object.values(webModels), Card]);

const ARCH = `
    <kanban limit="60">
        <templates>
            <t t-name="card">
                <field name="name"/>
            </t>
        </templates>
    </kanban>
`;
const CARDS = ".o_kanban_record:not(.o_kanban_ghost)";

function trackCards() {
    const cards = { built: 0, destroyed: 0, firstCommit: /** @type {number[]} */ ([]) };
    patchWithCleanup(KanbanRecord.prototype, {
        setup() {
            super.setup();
            cards.built++;
            onWillDestroy(() => {
                cards.destroyed++;
            });
        },
    });
    patchWithCleanup(KanbanRenderer.prototype, {
        setup() {
            super.setup();
            onMounted(() => {
                const el = /** @type {HTMLElement} */ (this.rootRef.el);
                const columns = [...el.querySelectorAll(".o_kanban_group")];
                cards.firstCommit = (columns.length ? columns : [el]).map(
                    (column) => column.querySelectorAll(CARDS).length,
                );
            });
        },
    });
    return cards;
}

const rowsPerScreen = (scrolledBy = 0) =>
    Math.ceil((browser.innerHeight + scrolledBy) / PITCH);
const cardsPerRow = () => Math.ceil(browser.innerWidth / CARD_WIDTH);

async function untilBuilt() {
    for (let frame = 0; frame < 30; frame++) {
        await animationFrame();
    }
}

beforeEach(() =>
    // wide enough for the desktop layout, where the content element scrolls
    resize({ width: 5 * CARD_WIDTH, height: 5 * PITCH }),
);

test.tags("desktop");
test("cards never measured are counted at their smallest: one screen of them is built first", async () => {
    const cards = trackCards();
    await mountView({ resModel: "card", type: "kanban", arch: ARCH });
    expect(cards.firstCommit).toEqual([cardsPerRow() * rowsPerScreen()]);
    expect(cards.firstCommit[0]).toBeLessThan(60);
    expect(`${CARDS}:first`).toHaveText("card 01");

    await untilBuilt();
    expect(CARDS).toHaveCount(60);
    expect(queryAll(CARDS).at(-1)).toHaveText("card 60");
    expect(cards.built).toBe(60);
    expect(cards.destroyed).toBe(0);
});

test.tags("desktop");
test("each column builds one screen of its cards first", async () => {
    const cards = trackCards();
    await mountView({
        resModel: "card",
        type: "kanban",
        arch: ARCH,
        groupBy: ["stage"],
    });
    expect(cards.firstCommit).toEqual([rowsPerScreen(), rowsPerScreen()]);
    expect(rowsPerScreen()).toBeLessThan(20);

    await untilBuilt();
    expect(`.o_kanban_group:eq(0) ${CARDS}`).toHaveCount(20);
    expect(`.o_kanban_group:eq(1) ${CARDS}`).toHaveCount(40);
    expect(cards.built).toBe(60);
});

test.tags("desktop");
test("what the cards measured on screen sizes the next first build of that model", async () => {
    await mountView({ resModel: "card", type: "kanban", arch: ARCH });
    await untilBuilt();
    const extents = getMeasuredCardExtents(getMockEnv().services);
    const measured = extents.get("card,ungrouped");
    expect(measured.pitch).toBeGreaterThan(0);
    expect(measured.perRow).toBeGreaterThan(0);

    extents.set("card,ungrouped", { pitch: browser.innerHeight, perRow: 3 });
    const cards = trackCards();
    await mountView({ resModel: "card", type: "kanban", arch: ARCH });
    expect(cards.firstCommit).toEqual([3]);
});

test.tags("desktop");
test("a kanban scrolled back to an offset builds what that offset shows", async () => {
    const cards = trackCards();
    await mountView({
        resModel: "card",
        type: "kanban",
        arch: ARCH,
        state: { [scrollSymbol]: { content: { left: 0, top: 3 * PITCH } } },
    });
    expect(cards.firstCommit).toEqual([cardsPerRow() * rowsPerScreen(3 * PITCH)]);
});
