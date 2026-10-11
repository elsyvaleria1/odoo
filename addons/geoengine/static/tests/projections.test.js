/** @odoo-module native */

import { geoLibs, loadGeoLibs, registerProjections } from "@geoengine/lib/geo_libs";
import { before, describe, expect, test, withFetch } from "@odoo/hoot";
import { globalCachedFetch } from "@web/../tests/_framework/module_set.hoot";

const MEXICO_LCC = {
    code: "EPSG:6372",
    proj4:
        "+proj=lcc +lat_1=17.5 +lat_2=29.5 +lat_0=12 +lon_0=-102 +x_0=2500000 +y_0=0 " +
        "+ellps=GRS80 +towgs84=0,0,0,0,0,0,0 +units=m +no_defs",
    extent: [278545.21, 11252.35, 4411724.3, 2428997.54],
};

describe("projections OpenLayers cannot resolve (production)", () => {
    let ol;

    before(async () => {
        await withFetch(globalCachedFetch, () => loadGeoLibs());
        ({ ol } = geoLibs());
    });

    test("a PostGIS definition makes the CRS drawable, with its area of use", async () => {
        await withFetch(globalCachedFetch, () => registerProjections([MEXICO_LCC]));
        const projection = ol.proj.get("EPSG:6372");
        expect(Boolean(projection)).toBe(true);
        expect(projection.getExtent()).toEqual(MEXICO_LCC.extent);
        const [x, y] = ol.proj.fromLonLat([-107.39, 24.8], "EPSG:6372");
        expect(Math.round(x * 1000) / 1000).toBe(1957969.293);
        expect(Math.round(y * 1000) / 1000).toBe(1427746.328);
    });

    test("built-in projections and no definitions need no proj4", async () => {
        await registerProjections([]);
        await registerProjections(undefined);
        await registerProjections([{ code: "EPSG:3857", proj4: "x", extent: null }]);
        expect(ol.proj.get("EPSG:3857").getCode()).toBe("EPSG:3857");
    });
});
