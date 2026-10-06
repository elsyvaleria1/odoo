/** @odoo-module native */
import { GeoengineRendererUtils } from "@geoengine/geoengine/renderer/geoengine_renderer_utils";
import { describe, expect, test } from "@odoo/hoot";

const VIEW_MODEL = "device.device";

/**
 * @param {number} layerId
 * @returns {Object}
 */
const layer = (layerId) => ({
    get: (key) => (key === "layerId" ? layerId : undefined),
});

/**
 * @param {Array<Object>} configs
 * @param {Array<Object>} vectorLayersResult
 * @param {string} resModel
 * @returns {GeoengineRendererUtils}
 */
const utilsWith = (configs, vectorLayersResult, resModel = VIEW_MODEL) => {
    const utils = Object.create(GeoengineRendererUtils.prototype);
    utils.renderer = {
        props: { model: { root: { resModel }, layers: { vectors: configs } } },
        vectorLayersResult,
    };
    return utils;
};

describe("Map fit ignores cross-model layers", () => {
    test("a layer on another model is left out of the fit", () => {
        // The live GPS map pairs device.device pins with a res.partner
        // overlay; a search filters the devices only, so the partners must
        // not decide the frame.
        const utils = utilsWith(
            [
                { resId: 7, model: VIEW_MODEL },
                { resId: 10, model: "res.partner" },
            ],
            [layer(7), layer(10)],
        );

        expect(
            utils
                ._viewModelLayers(utils.renderer.vectorLayersResult)
                .map((l) => l.get("layerId")),
        ).toEqual([7]);
    });

    test("a layer naming no model of its own draws the view's records", () => {
        const utils = utilsWith([{ resId: 7, model: false }], [layer(7)]);

        expect(
            utils
                ._viewModelLayers(utils.renderer.vectorLayersResult)
                .map((l) => l.get("layerId")),
        ).toEqual([7]);
    });

    test("an unconfigured layer is not assumed to be the view's", () => {
        const utils = utilsWith(
            [{ resId: 7, model: VIEW_MODEL }],
            [layer(7), layer(99)],
        );

        expect(
            utils
                ._viewModelLayers(utils.renderer.vectorLayersResult)
                .map((l) => l.get("layerId")),
        ).toEqual([7]);
    });

    test("no root model selects nothing rather than everything", () => {
        const utils = utilsWith([{ resId: 7, model: VIEW_MODEL }], [layer(7)], null);

        expect(utils._viewModelLayers(utils.renderer.vectorLayersResult)).toEqual([]);
    });

    test("the fit frames the view's own layers when they drew something", () => {
        const utils = utilsWith(
            [
                { resId: 7, model: VIEW_MODEL },
                { resId: 10, model: "res.partner" },
            ],
            [layer(7), layer(10)],
        );
        const asked = [];
        utils._extentOf = (layers) => {
            asked.push(layers.map((l) => l.get("layerId")));
            return layers.length ? [0, 0, 1, 1] : null;
        };

        expect(utils._featuresExtent()).toEqual([0, 0, 1, 1]);
        expect(asked).toEqual([[7]]);
    });

    test("the fit falls back to every layer when the view's model drew nothing", () => {
        // An overlay-only map (every device off, or none reporting) must
        // still frame itself instead of leaving the view where it was.
        const utils = utilsWith([{ resId: 10, model: "res.partner" }], [layer(10)]);
        const asked = [];
        utils._extentOf = (layers) => {
            asked.push(layers.map((l) => l.get("layerId")));
            return layers.length ? [2, 2, 3, 3] : null;
        };

        expect(utils._featuresExtent()).toEqual([2, 2, 3, 3]);
        expect(asked).toEqual([[], [10]]);
    });
});
