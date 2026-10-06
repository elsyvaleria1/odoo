// @ts-check

import { expect, test } from "@odoo/hoot";
import { animationFrame } from "@odoo/hoot-mock";
import {
    contains,
    defineModels,
    fields,
    models,
    mountView,
    onRpc,
    toggleMenuItem,
    toggleSearchBarMenu,
} from "@web/../tests/web_test_helpers";

class Note extends models.Model {
    name = fields.Char();

    _records = [
        { id: 1, name: "first" },
        { id: 2, name: "second" },
    ];
}

defineModels([Note]);

const searchViewArch = `
    <search>
        <filter name="none" string="Nothing" domain="[('id', '=', 0)]"/>
    </search>
`;

async function mountNotes() {
    await mountView({
        resModel: "note",
        type: "list",
        arch: `<list><field name="name"/></list>`,
        noContentHelp: "Write your first note",
        searchViewArch,
    });
}

test("a search hiding every record says how many it hides, and clears", async () => {
    onRpc("search_count", ({ args }) => {
        expect.step(`search_count ${JSON.stringify(args[0])}`);
    });
    await mountNotes();
    await toggleSearchBarMenu();
    await toggleMenuItem("Nothing");
    await animationFrame();

    expect(".o_view_nocontent_no_results").toHaveText("No results");
    expect(".o_nocontent_help p:eq(1)").toHaveText(
        "2 records are hidden by your search.",
    );
    expect.verifySteps(["search_count []"]);

    await contains(".o_empty_state_clear_search").click();
    expect(".o_view_nocontent").toHaveCount(0);
    expect(".o_data_row").toHaveCount(2);
});

test("with nothing to hide, a search shows the action's help", async () => {
    Note._records = [];
    await mountNotes();
    await toggleSearchBarMenu();
    await toggleMenuItem("Nothing");
    await animationFrame();

    expect(".o_view_nocontent_no_results").toHaveCount(0);
    expect(".o_nocontent_help").toHaveText("Write your first note");
});

test("without a search, an empty view asks for no count", async () => {
    onRpc("search_count", () => expect.step("search_count"));
    Note._records = [];
    await mountNotes();

    expect(".o_nocontent_help").toHaveText("Write your first note");
    expect.verifySteps([]);
});
