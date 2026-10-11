import { beforeEach, describe, expect, test } from "@odoo/hoot";
import { queryAllTexts } from "@odoo/hoot-dom";
import { animationFrame, tick } from "@odoo/hoot-mock";
import { markup } from "@odoo/owl";
import {
    contains,
    defineModels,
    fields,
    findComponent,
    mockService,
    models,
    mountView,
    onRpc,
    patchWithCleanup,
    toggleMenuItem,
    toggleSearchBarMenu,
} from "@web/../tests/web_test_helpers";
import { browser } from "@web/core/browser/browser";
import { session } from "@web/session";
import { MapController } from "@web_map/map_view/map_controller";
import { MapModel } from "@web_map/map_view/map_model";
import { MapRenderer } from "@web_map/map_view/map_renderer";

const MAP_BOX_TOKEN = "token";

class Task extends models.Model {
    _name = "project.task";

    name = fields.Char();
    stage = fields.Selection({
        string: "Stage",
        selection: [
            ["a", "Alpha"],
            ["b", "Beta"],
        ],
    });
    partner_id = fields.Many2one({ string: "Partner", relation: "res.partner" });

    _records = [
        { id: 1, name: "First", partner_id: 1, stage: "a" },
        { id: 2, name: "Second", partner_id: 2, stage: "b" },
    ];

    _views = {
        "list,7": `<list><field name="name"/></list>`,
        "form,9": `<form><field name="name"/></form>`,
        "search,3": `<search/>`,
    };
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
            name: "Foo",
            partner_latitude: 10,
            partner_longitude: 10.5,
            contact_address_complete: "Rue A 1",
        },
        {
            id: 2,
            name: "Bar",
            partner_latitude: 11,
            partner_longitude: 11.5,
            contact_address_complete: "Rue B 2",
        },
    ];

    update_latitude_longitude() {
        return true;
    }
}

defineModels([Task, Partner]);

/**
 * Answer the geocoding/routing calls with real `Response` objects; anything
 * that is not an outbound provider call keeps going to the test server.
 *
 * @param {(url: string) => Response|Promise<Response>} handler
 * @returns {string[]} the provider urls requested, in order
 */
function mockProvider(handler) {
    const requested = [];
    const originalFetch = browser.fetch;
    patchWithCleanup(browser, {
        fetch: async (url, ...rest) => {
            const route = String(url);
            if (!route.startsWith("http")) {
                return originalFetch.call(browser, url, ...rest);
            }
            requested.push(route);
            return handler(route);
        },
    });
    return requested;
}

function jsonResponse(payload, status = 200) {
    return new Response(JSON.stringify(payload), { status });
}

function getModel(view) {
    return findComponent(view, (c) => c instanceof MapController).model;
}

function getRenderer(view) {
    return findComponent(view, (c) => c instanceof MapRenderer);
}

beforeEach(() => {
    patchWithCleanup(MapModel, { COORDINATE_FETCH_DELAY: 0 });
});

describe.tags("desktop");
describe("map_view_providers", () => {
    test("a MapBox 401 tells the user why the map lost its features", async () => {
        patchWithCleanup(session, { map_box_token: MAP_BOX_TOKEN });
        Partner._records[0].partner_latitude = 0;
        Partner._records[0].partner_longitude = 0;
        const notifications = [];
        mockService("notification", {
            add: (message, options) => notifications.push(options?.title),
        });
        mockProvider(async (url) =>
            url.includes("geocoding")
                ? jsonResponse({ message: "Not Authorized - Invalid Token" }, 401)
                : jsonResponse([]),
        );

        const view = await mountView({
            type: "map",
            resModel: "project.task",
            arch: `<map res_partner="partner_id" routing="1"/>`,
        });

        expect(notifications).toEqual(["Token invalid"], {
            message: "a real 401 has to reach the user, not just flip the provider",
        });
        expect(getModel(view).data.useMapBoxAPI).toBe(false);
    });

    test("a MapBox 5xx is reported even though no case names it", async () => {
        patchWithCleanup(session, { map_box_token: MAP_BOX_TOKEN });
        Partner._records[0].partner_latitude = 0;
        Partner._records[0].partner_longitude = 0;
        const notifications = [];
        mockService("notification", {
            add: (message, options) => notifications.push(options?.title),
        });
        mockProvider(async (url) =>
            url.includes("geocoding")
                ? jsonResponse({ message: "boom" }, 503)
                : jsonResponse([]),
        );

        await mountView({
            type: "map",
            resModel: "project.task",
            arch: `<map res_partner="partner_id" routing="1"/>`,
        });

        expect(notifications).toEqual(["MapBox servers unreachable"]);
    });

    test("a 422 routing reply shows the routing error, not the token banner", async () => {
        patchWithCleanup(session, { map_box_token: MAP_BOX_TOKEN });
        mockProvider(async () =>
            jsonResponse(
                {
                    message:
                        "Too many coordinates; maximum number of coordinates is 25",
                },
                422,
            ),
        );

        const view = await mountView({
            type: "map",
            resModel: "project.task",
            arch: `<map res_partner="partner_id" routing="1"/>`,
        });

        expect(getModel(view).data.routingError).toBe(
            "Too many routing points (maximum 25)",
        );
        expect(".o-map-renderer--alert").toHaveText(
            "Unsuccessful routing request: Too many routing points (maximum 25)",
        );
    });

    test("an unmapped routing message is shown instead of swallowed", async () => {
        patchWithCleanup(session, { map_box_token: MAP_BOX_TOKEN });
        mockProvider(async () => jsonResponse({ message: "Profile not found" }, 422));

        const view = await mountView({
            type: "map",
            resModel: "project.task",
            arch: `<map res_partner="partner_id" routing="1"/>`,
        });

        expect(getModel(view).data.routingError).toBe("Profile not found");
    });

    test("failing to store fetched coordinates is not a MapBox failure", async () => {
        patchWithCleanup(session, { map_box_token: MAP_BOX_TOKEN });
        Partner._records[0].partner_latitude = 0;
        Partner._records[0].partner_longitude = 0;
        const notifications = [];
        mockService("notification", {
            add: (message, options) => notifications.push(options?.title),
        });
        mockProvider(async (url) =>
            url.includes("geocoding")
                ? jsonResponse({ features: [{ geometry: { coordinates: [1, 2] } }] })
                : jsonResponse({ routes: [{ legs: [] }] }),
        );
        onRpc("res.partner", "update_latitude_longitude", () => {
            throw new Error("the write failed");
        });

        const view = await mountView({
            type: "map",
            resModel: "project.task",
            arch: `<map res_partner="partner_id" routing="1"/>`,
        });

        expect(notifications).toEqual([undefined], {
            message: "the failure is reported as itself, not as a provider failure",
        });
        expect(getModel(view).data.useMapBoxAPI).toBe(true, {
            message: "the view must stay on MapBox",
        });
        expect(".o-map-renderer--marker").toHaveCount(2, {
            message: "the map still opens when the coordinates cannot be cached",
        });
    });

    test("a route with more points than MapBox allows is refused, not sent", async () => {
        patchWithCleanup(session, { map_box_token: MAP_BOX_TOKEN });
        Partner._records = [];
        Task._records = [];
        for (let id = 1; id <= 30; id++) {
            Partner._records.push({
                id,
                name: `P${id}`,
                partner_latitude: 10 + id / 100,
                partner_longitude: 10 + id / 100,
                contact_address_complete: `Rue ${id}`,
            });
            Task._records.push({ id, name: `T${id}`, partner_id: id });
        }
        const requested = mockProvider(async () => jsonResponse({ routes: [] }));

        const view = await mountView({
            type: "map",
            resModel: "project.task",
            arch: `<map res_partner="partner_id" routing="1"/>`,
        });

        expect(getModel(view).data.routingError).toBe(
            "Too many routing points (maximum 25)",
        );
        expect(requested.filter((url) => url.includes("directions"))).toEqual([], {
            message: "and no call is made to learn it",
        });
        expect(".o-map-renderer--alert").toHaveText(
            "Unsuccessful routing request: Too many routing points (maximum 25)",
        );
    });

    test("a partner on the prime meridian is located, not geocoded again", async () => {
        Partner._records = [
            {
                id: 1,
                name: "Greenwich",
                partner_latitude: 51.4779,
                partner_longitude: 0,
                contact_address_complete: "Greenwich, London",
            },
            {
                id: 2,
                name: "Null Island",
                partner_latitude: 0,
                partner_longitude: 0,
                contact_address_complete: "",
            },
        ];
        const requested = mockProvider(async () => jsonResponse([]));

        const view = await mountView({
            type: "map",
            resModel: "project.task",
            arch: `<map res_partner="partner_id"/>`,
        });
        await animationFrame();

        expect(".o-map-renderer--marker").toHaveCount(1);
        expect(".o-map-renderer--pin-located").toHaveCount(1);
        expect(requested).toEqual([], {
            message: "a located partner must not be geocoded on every load",
        });
        expect(getModel(view).locatedRecordCount).toBe(1);
    });

    test("a cluster is named and numbered after its first record", async () => {
        Task._records = [
            { id: 1, name: "First", partner_id: 1 },
            { id: 2, name: "Second", partner_id: 1 },
            { id: 3, name: "Third", partner_id: 1 },
        ];
        mockProvider(async () => jsonResponse([]));

        const view = await mountView({
            type: "map",
            resModel: "project.task",
            arch: `<map res_partner="partner_id"/>`,
        });
        const renderer = getRenderer(view);
        const [markerInfo] = renderer.getMarkersInfo();

        expect(markerInfo.ids).toEqual([1, 2, 3]);
        expect(markerInfo.records.map((record) => record.id)).toEqual([1, 2, 3], {
            message: "every clustered record is kept, exactly once",
        });
        expect(renderer.getMarkerRecord(markerInfo).id).toBe(1, {
            message: "the cluster stands for its first record, not its last",
        });
    });

    test("an unrelated re-render keeps the viewport and the open popup", async () => {
        mockProvider(async () => jsonResponse([]));
        const view = await mountView({
            type: "map",
            resModel: "project.task",
            arch: `<map res_partner="partner_id"/>`,
            searchViewId: false,
            searchViewArch: `
                <search>
                    <filter string="Stage" name="stage" context="{'group_by': 'stage'}"/>
                </search>`,
        });
        const renderer = getRenderer(view);
        let addMarkers = 0;
        patchWithCleanup(renderer, {
            addMarkers() {
                addMarkers++;
                return super.addMarkers();
            },
        });

        await contains(".leaflet-marker-icon").click();
        expect(".leaflet-popup").toHaveCount(1);
        renderer.leafletMap.setView([48.8, 2.3], 12);

        renderer.__owl__.render();
        await animationFrame();

        expect(".leaflet-popup").toHaveCount(1, {
            message: "the popup must survive a render that moved nothing",
        });
        expect(renderer.leafletMap.getZoom()).toBe(12, {
            message: "the user's zoom must survive a render that moved nothing",
        });
        expect(addMarkers).toBe(0, {
            message: "unchanged markers must not be torn down and rebuilt",
        });
    });

    test("a reload with the same records still refreshes what the markers show", async () => {
        Task._records = [{ id: 1, name: "First", stage: "a", partner_id: 1 }];
        mockProvider(async () => jsonResponse([]));
        const view = await mountView({
            type: "map",
            resModel: "project.task",
            arch: `<map res_partner="partner_id"/>`,
        });
        const model = getModel(view);

        await contains(".leaflet-marker-icon").click();
        expect(".leaflet-popup:last").toHaveText(/First/);
        await contains(".leaflet-popup-close-button").click();

        await model.orm.write("project.task", [1], { name: "Renamed" });
        await model.load({});
        await animationFrame();

        await contains(".leaflet-marker-icon").click();
        expect(".leaflet-popup:last").toHaveText(/Renamed/, {
            message: "the popup must show the reloaded record, not the old one",
        });
    });

    test("closing a group and then regrouping starts from every group open", async () => {
        mockProvider(async () => jsonResponse([]));
        const view = await mountView({
            type: "map",
            resModel: "project.task",
            arch: `<map res_partner="partner_id"/>`,
            searchViewId: false,
            searchViewArch: `
                <search>
                    <filter string="Stage" name="stage" context="{'group_by': 'stage'}"/>
                    <filter string="Name" name="name" context="{'group_by': 'name'}"/>
                </search>`,
        });
        const renderer = getRenderer(view);

        await toggleSearchBarMenu();
        await toggleMenuItem("Stage");
        await contains(".o-map-renderer--pin-list-group-header:eq(0)").click();
        expect(renderer.state.closedGroupIds).toHaveLength(1);

        await toggleSearchBarMenu();
        await toggleMenuItem("Name");
        await toggleMenuItem("Stage");
        await animationFrame();

        expect(renderer.state.closedGroupIds).toEqual([], {
            message: "a group closed under the old groupBy must not stay closed",
        });
    });

    test('a map on res.partner with sample="1" shows sample pins', async () => {
        Task._records = [];
        Partner._records = [];
        const requested = mockProvider(async () => jsonResponse([]));

        const view = await mountView({
            type: "map",
            resModel: "res.partner",
            arch: `<map res_partner="id" sample="1"/>`,
        });

        expect(getModel(view).useSampleModel).toBe(true);
        expect(".o_view_sample_data").toHaveCount(1);
        expect(
            document.querySelectorAll(".o-map-renderer--marker").length,
        ).toBeGreaterThan(0, {
            message: "the sample partners carry coordinates and must be drawn",
        });
        expect(requested).toEqual([], {
            message: "sample data must never reach a geocoding provider",
        });
    });

    test("a map reaching its partner through a many2one samples pins too", async () => {
        Task._records = [];
        Partner._records = [];
        const requested = mockProvider(async () => jsonResponse([]));

        const view = await mountView({
            type: "map",
            resModel: "project.task",
            arch: `<map res_partner="partner_id" sample="1"/>`,
        });
        const model = getModel(view);

        expect(model.useSampleModel).toBe(true);
        expect(".o_view_sample_data").toHaveCount(1);
        expect(model.locatedRecordCount).toBeGreaterThan(0, {
            message: "the sample partners must carry coordinates",
        });
        expect(
            document.querySelectorAll(".o-map-renderer--marker").length,
        ).toBeGreaterThan(0);
        expect(requested).toEqual([], {
            message: "sample data must never reach a geocoding provider",
        });
    });

    test("sample data stays out of the way when the map has records", async () => {
        mockProvider(async () => jsonResponse([]));

        const view = await mountView({
            type: "map",
            resModel: "project.task",
            arch: `<map res_partner="partner_id" sample="1"/>`,
        });

        expect(getModel(view).useSampleModel).toBe(false);
        expect(".o_view_sample_data").toHaveCount(0);
        expect(".o-map-renderer--pin-located").toHaveCount(2);
    });

    test("a pin's number counts the located records, not every record", async () => {
        Partner._records.push({
            id: 3,
            name: "Nowhere",
            contact_address_complete: "",
        });
        Task._records = [
            { id: 3, name: "Unlocated", partner_id: 3 },
            { id: 1, name: "First", partner_id: 1 },
            { id: 2, name: "Second", partner_id: 2 },
        ];
        mockProvider(async () => jsonResponse([]));

        await mountView({
            type: "map",
            resModel: "project.task",
            arch: `<map res_partner="partner_id" routing="1"/>`,
        });

        expect(queryAllTexts(".o-map-renderer--pin-located")).toEqual([
            "1. First",
            "2. Second",
        ]);
        expect(queryAllTexts(".o-map-renderer--marker-number")).toEqual(["1", "2"]);
    });

    test("a clustered marker drills down through the action's own views", async () => {
        Task._records = [
            { id: 1, name: "First", partner_id: 1 },
            { id: 2, name: "Second", partner_id: 1 },
        ];
        let action = null;
        let options = null;
        mockService("action", {
            doAction(actionRequest, actionOptions) {
                action = actionRequest;
                options = actionOptions;
            },
        });
        mockProvider(async () => jsonResponse([]));

        await mountView({
            type: "map",
            resModel: "project.task",
            arch: `<map res_partner="partner_id"/>`,
            context: { group_by: "stage", search_default_mine: 1, default_kind: "x" },
            config: {
                views: [
                    [7, "list"],
                    [9, "form"],
                    [3, "search"],
                ],
            },
        });
        await contains(".leaflet-marker-icon").click();
        await contains(".o-map-renderer--popup-buttons-open").click();

        expect(action.views).toEqual([
            [7, "list"],
            [9, "form"],
        ]);
        expect(action.search_view_id?.[1]).toBe("search");
        expect(action.domain).toEqual([["id", "in", [1, 2]]]);
        expect(action.res_model).toBe("project.task");
        expect(action.target).toBe("current");
        expect(action.context.default_kind).toBe("x", {
            message: "a default the action carried survives the drill down",
        });
        expect(action.context.group_by).toBe(undefined, {
            message: "this view's grouping must not re-apply to the list",
        });
        expect(action.context.search_default_mine).toBe(undefined);
        expect(options.viewType).toBe("list");
    });

    test("an empty map offers the action's no-content help", async () => {
        Task._records = [];
        Partner._records = [];
        mockProvider(async () => jsonResponse([]));

        await mountView({
            type: "map",
            resModel: "project.task",
            arch: `<map res_partner="partner_id"/>`,
            noContentHelp: markup("<p>Add a task with a customer to see it here</p>"),
        });

        expect(".o_view_nocontent").toBeVisible();
        expect(".o_nocontent_help").toHaveText(
            "Add a task with a customer to see it here",
        );
        expect(".o-map-renderer--pin-list-details").toHaveCount(0);
    });

    test("an empty map with no help still explains itself", async () => {
        Task._records = [];
        Partner._records = [];
        mockProvider(async () => jsonResponse([]));

        await mountView({
            type: "map",
            resModel: "project.task",
            arch: `<map res_partner="partner_id"/>`,
        });

        expect(".o_view_nocontent_empty_folder").toBeVisible();
    });

    test("a record the map cannot place is listed, greyed and inert", async () => {
        Partner._records.push({
            id: 3,
            name: "Nowhere",
            contact_address_complete: "",
        });
        Task._records = [
            { id: 1, name: "First", partner_id: 1 },
            { id: 3, name: "Unplaceable", partner_id: 3 },
        ];
        mockProvider(async () => jsonResponse([]));

        const view = await mountView({
            type: "map",
            resModel: "project.task",
            arch: `<map res_partner="partner_id"/>`,
        });
        const renderer = getRenderer(view);

        expect(queryAllTexts(".o-map-renderer--pin-list-details li")).toEqual([
            "First",
            "Unplaceable",
        ]);
        expect(queryAllTexts(".o-map-renderer--pin-located")).toEqual(["First"]);
        expect(".o-map-renderer--marker").toHaveCount(1);

        const unplaceable =
            ".o-map-renderer--pin-list-details li:not(.o-map-renderer--pin-located)";
        expect(unplaceable).toHaveClass("text-muted");
        const before = renderer.leafletMap.getCenter();
        await contains(unplaceable).click();
        expect(".leaflet-popup").toHaveCount(0);
        expect(renderer.leafletMap.getCenter()).toEqual(before, {
            message: "and the map does not move",
        });
    });

    test("the Google Maps link always carries a destination", async () => {
        mockProvider(async () => jsonResponse([]));
        const view = await mountView({
            type: "map",
            resModel: "project.task",
            arch: `<map res_partner="partner_id"/>`,
        });

        expect(getRenderer(view).googleMapParams.destination).toBe("Rue B 2");
        expect("a[data-hotkey=m]").toHaveAttribute(
            "href",
            "https://www.google.com/maps/dir/?api=1&destination=Rue+B+2&waypoints=Rue+A+1",
        );
    });

    test("OpenStreetMap geocodes the first address without waiting a full delay", async () => {
        patchWithCleanup(MapModel, { COORDINATE_FETCH_DELAY: 100000 });
        Partner._records = [
            {
                id: 1,
                name: "Foo",
                partner_latitude: 0,
                partner_longitude: 0,
                contact_address_complete: "Rue A 1",
            },
        ];
        Task._records = [{ id: 1, name: "First", partner_id: 1 }];
        const requested = mockProvider(async () =>
            jsonResponse([{ lat: "10", lon: "10.5" }]),
        );

        await mountView({
            type: "map",
            resModel: "project.task",
            arch: `<map res_partner="partner_id"/>`,
        });
        await tick();
        await animationFrame();

        expect(requested).toHaveLength(1, {
            message: "the rate limit only applies between requests",
        });
        expect(requested[0]).toMatch(/nominatim/);
    });
});
