import { geoengineView } from "@geoengine/geoengine/geoengine_view";
import { describe, expect, test } from "@odoo/hoot";
import { Component, useProps, xml } from "@odoo/owl";
import {
    defineModels,
    fields,
    models,
    mountView,
    onRpc,
    patchWithCleanup,
    webModels,
} from "@web/../tests/web_test_helpers";

/**
 * The controller's chassis, isolated from OpenLayers.
 *
 * geoengine ships no test that mounts its controller, so the control panel it
 * renders was never asserted: before the ViewLayout conversion it drew a search
 * bar it could not reveal on a small screen (`SearchBar` was guarded by
 * `searchBarToggler.state.showSearchBar` and the toggler button was never
 * rendered at all), no cog menu despite declaring one, and no no-content
 * helper. Stubbing the renderer is what makes that assertable without a WebGL
 * context.
 */
class StubRenderer extends Component {
    static template = xml`<div class="o_geo_stub_renderer"/>`;
    static props = null;
    props = useProps(this.constructor.props);
}

class GeoRecord extends models.Model {
    _name = "geo.record";
    name = fields.Char();
    lat = fields.Float();
    lon = fields.Float();
    _records = [{ id: 1, name: "one", lat: 1.5, lon: 2.5 }];
}
defineModels({ ...webModels, GeoRecord });

const ARCH = `<geoengine><field name="name"/></geoengine>`;

async function mountGeo(props = {}) {
    patchWithCleanup(geoengineView, { Renderer: StubRenderer });
    onRpc("get_layers", () => ({ actives: [], backgrounds: [] }));
    await mountView({
        type: "geoengine",
        resModel: "geo.record",
        arch: ARCH,
        ...props,
    });
}

describe("GeoengineController chassis", () => {
    test("mounts and takes the view root class it is given", async () => {
        await mountGeo();
        expect(".o_geo_stub_renderer").toHaveCount(1);
        expect(".o_geoengine_view").toHaveCount(1);
        expect(".o_geoengine_view").toHaveClass("o_view_controller");
    });

    test.tags("desktop");
    test("renders the search bar", async () => {
        await mountGeo();
        expect(".o_cp_searchview").toHaveCount(1);
    });

    // The loaded-root cases (first paint, reload, panel toggle) live in
    // geoengine_view_e2e.test.js, which mounts the real renderer against a
    // mocked get_layers.

    test.tags("mobile");
    test("on a small screen the search bar can be revealed", async () => {
        await mountGeo();
        // The toggler button is the whole point: without it the search bar is
        // hidden on a small screen with no way to bring it back.
        expect("button[aria-label='Toggle the search bar']").toHaveCount(1);
    });
});
