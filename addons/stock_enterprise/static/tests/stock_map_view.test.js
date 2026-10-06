import { describe, expect, test } from "@odoo/hoot";
import { queryAllTexts } from "@odoo/hoot-dom";
import { StockMapRenderer } from "@stock_enterprise/map_view/map_renderer";
import {
    contains,
    defineModels,
    fields,
    findComponent,
    models,
    mountView,
    patchWithCleanup,
} from "@web/../tests/web_test_helpers";
import { browser } from "@web/core/browser/browser";
import { MapRenderer } from "@web_map/map_view/map_renderer";

class Picking extends models.Model {
    _name = "stock.picking";

    name = fields.Char();
    partner_id = fields.Many2one({
        string: "Delivery Address",
        relation: "res.partner",
    });
    warehouse_address_id = fields.Many2one({
        string: "Warehouse",
        relation: "res.partner",
    });

    _records = [
        { id: 1, name: "WH/OUT/001", partner_id: 1, warehouse_address_id: 9 },
        { id: 2, name: "WH/OUT/002", partner_id: 1, warehouse_address_id: 9 },
        { id: 3, name: "WH/OUT/003", partner_id: 1, warehouse_address_id: 9 },
    ];
}

class Partner extends models.Model {
    _name = "res.partner";

    name = fields.Char();
    partner_latitude = fields.Float();
    partner_longitude = fields.Float();
    contact_address_complete = fields.Char();

    _records = [
        {
            id: 1,
            name: "Customer",
            partner_latitude: 10,
            partner_longitude: 10.5,
            contact_address_complete: "Rue du Client 1",
        },
        {
            id: 9,
            name: "Main Warehouse",
            partner_latitude: 50,
            partner_longitude: 4,
            contact_address_complete: "Rue de l'Entrepot 9",
        },
    ];

    update_latitude_longitude() {
        return true;
    }
}

defineModels([Picking, Partner]);

/** Answer the geocoding provider so no test reaches the network. */
function blockProviders() {
    const original = browser.fetch;
    patchWithCleanup(browser, {
        fetch: async (url, ...rest) =>
            String(url).startsWith("http")
                ? new Response("[]", { status: 200 })
                : original.call(browser, url, ...rest),
    });
}

async function mountStockMap() {
    blockProviders();
    return mountView({
        type: "map",
        resModel: "stock.picking",
        arch: `<map res_partner="partner_id" js_class="stock_map" routing="1"/>`,
    });
}

describe.tags("desktop");
describe("stock_map_view", () => {
    test("the popup of a shared address lists every transfer exactly once", async () => {
        // The three transfers share one delivery address, so they cluster onto
        // one marker. The cluster used to keep only its *last* record and push
        // that same record into `relatedRecords`, so this popup showed the last
        // transfer twice and the first one not at all.
        await mountStockMap();

        expect(".o-map-renderer--marker").toHaveCount(1);
        await contains(".leaflet-marker-icon").click();

        expect(
            queryAllTexts(".leaflet-popup .o-map-renderer--popup-table"),
        ).toHaveLength(3, { message: "one table per clustered transfer" });
        const popup = document.querySelector(".leaflet-popup").textContent;
        for (const name of ["WH/OUT/001", "WH/OUT/002", "WH/OUT/003"]) {
            expect(popup.split(name)).toHaveLength(2, {
                message: `${name} appears exactly once`,
            });
        }
    });

    test("the Google Maps link makes a round trip from the warehouse", async () => {
        const view = await mountStockMap();
        const renderer = findComponent(view, (c) => c instanceof StockMapRenderer);

        // Regression: this getter called a helper the base class did not
        // declare, so any stock map with a warehouse threw a TypeError here.
        const params = renderer.googleMapParams;

        expect(params.origin).toBe("Rue de l'Entrepot 9");
        expect(params.destination).toBe("Rue de l'Entrepot 9");
        expect(params.waypoints).toBe("Rue du Client 1");
        expect("a[data-hotkey=m]").toHaveAttribute(
            "href",
            /origin=Rue\+de\+l%27Entrepot\+9.*destination=Rue\+de\+l%27Entrepot\+9/,
        );
    });

    test('an empty stock map under sample="1" degrades instead of throwing', async () => {
        // MapModel.hasData() makes sample mode reachable for this view too, and
        // SampleServer answers a nested many2one specification with
        // `{id, display_name}` only -- so the sample warehouse arrives without
        // the `contact_address_complete` this renderer routes from.
        Picking._records = [];
        Partner._records = [];
        blockProviders();

        const view = await mountView({
            type: "map",
            resModel: "stock.picking",
            arch: `<map res_partner="partner_id" js_class="stock_map" sample="1"/>`,
        });
        const renderer = findComponent(view, (c) => c instanceof StockMapRenderer);

        expect(".o_view_sample_data").toHaveCount(1);
        expect(renderer.googleMapParams).toEqual({});
        expect(renderer.googleMapUrl).toBe("https://www.google.com/maps/dir/?api=1");
    });

    test("transfers from different warehouses fall back to the plain route", async () => {
        Picking._records[2].warehouse_address_id = 1;
        const view = await mountStockMap();
        const renderer = findComponent(view, (c) => c instanceof StockMapRenderer);

        expect(renderer.googleMapParams.origin).toBe(undefined);
        expect(renderer.googleMapParams).toEqual(
            Object.getOwnPropertyDescriptor(
                MapRenderer.prototype,
                "googleMapParams",
            ).get.call(renderer),
        );
    });
});
