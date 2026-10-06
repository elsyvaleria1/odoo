import { describe, expect, test } from "@odoo/hoot";
import { animationFrame, click, queryAll, queryOne } from "@odoo/hoot-dom";
import {
    setupInteractionWhiteList,
    startInteractions,
} from "@web/../tests/public/helpers";

setupInteractionWhiteList("asset_ledger_website_sale.vehicle_catalog");

describe.current.tags("interaction_dev");

const CATALOG = `
    <div class="m-vehicles-catalog">
        <button class="m-vehicle-filter m-vehicle-filter--active" data-m-filter="all">All</button>
        <button class="m-vehicle-filter" data-m-filter="1">Trucks</button>
        <button class="m-vehicle-filter" data-m-filter="2">Tractors</button>
        <div class="m-vehicle-card" data-m-tags="1">truck</div>
        <div class="m-vehicle-card" data-m-tags="1 2">both</div>
        <div class="m-vehicle-card" data-m-tags="2">tractor</div>
    </div>
`;

function shownCards() {
    return queryAll(".m-vehicle-card")
        .filter((card) => card.style.display !== "none")
        .map((card) => card.textContent);
}

test("starts on a page rendered after DOMContentLoaded", async () => {
    // the website editor iframe receives the bundle after the event
    const { core } = await startInteractions(CATALOG);
    expect(core.interactions).toHaveLength(1);
    expect(shownCards()).toEqual(["truck", "both", "tractor"]);
});

test("a filter shows only the cards carrying its tag", async () => {
    await startInteractions(CATALOG);
    await click("[data-m-filter='2']");
    await animationFrame();
    expect(shownCards()).toEqual(["both", "tractor"]);
    expect(queryOne("[data-m-filter='2']")).toHaveClass("m-vehicle-filter--active");
    expect(queryOne("[data-m-filter='all']")).not.toHaveClass(
        "m-vehicle-filter--active",
    );

    await click("[data-m-filter='all']");
    await animationFrame();
    expect(shownCards()).toEqual(["truck", "both", "tractor"]);
});
