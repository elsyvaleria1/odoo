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

    test.tags("mobile");
    test("on a small screen the search bar can be revealed", async () => {
        await mountGeo();
        expect("button[aria-label='Toggle the search bar']").toHaveCount(1);
    });
});
