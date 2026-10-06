/** @odoo-module native */

import {
    editCommandOf,
    EditHistory,
    partCount,
} from "@geoengine/geoengine/renderer/geoengine_edit_session";
import { GeoengineRendererInteractions } from "@geoengine/geoengine/renderer/geoengine_renderer_interactions";
import { geoLibs, loadGeoLibs } from "@geoengine/lib/geo_libs";
import { before, describe, expect, test, withFetch } from "@odoo/hoot";
import { Deferred } from "@odoo/hoot-mock";
import { globalCachedFetch } from "@web/../tests/_framework/module_set.hoot";

const key = (name, modifiers = {}, target = document.body) => ({
    key: name,
    ctrlKey: false,
    metaKey: false,
    shiftKey: false,
    target,
    ...modifiers,
});

describe("edit history (production)", () => {
    test("steps are undone last first and redone in their order", () => {
        const history = new EditHistory();
        history.record({ resId: 1, geoField: "area", before: "a0", after: "a1" });
        history.record({ resId: 2, geoField: "area", before: "b0", after: "b1" });
        expect(history.undo().resId).toBe(2);
        expect(history.undo().resId).toBe(1);
        expect(history.undo()).toBe(undefined);
        expect(history.redo().resId).toBe(1);
        expect(history.canUndo).toBe(true);
        expect(history.canRedo).toBe(true);
    });

    test("a new reshape after an undo drops what could be redone", () => {
        const history = new EditHistory();
        history.record({ resId: 1, geoField: "area", before: "a0", after: "a1" });
        history.undo();
        history.record({ resId: 1, geoField: "area", before: "a0", after: "a2" });
        expect(history.canRedo).toBe(false);
        expect(history.redo()).toBe(undefined);
    });
});

describe("edit keys (production)", () => {
    test("while reshaping, Ctrl+Z undoes and Ctrl+Y or Ctrl+Shift+Z redoes", () => {
        expect(editCommandOf(key("z", { ctrlKey: true }), "modify")).toBe("undo");
        expect(editCommandOf(key("Z", { metaKey: true }), "modify")).toBe("undo");
        expect(editCommandOf(key("y", { ctrlKey: true }), "modify")).toBe("redo");
        expect(
            editCommandOf(key("Z", { ctrlKey: true, shiftKey: true }), "modify"),
        ).toBe("redo");
        expect(editCommandOf(key("z"), "modify")).toBe(null);
        expect(editCommandOf(key("Backspace"), "modify")).toBe(null);
    });

    test("while drawing, Ctrl+Z or Backspace takes back the last point and Escape drops the shape", () => {
        expect(editCommandOf(key("z", { ctrlKey: true }), "draw")).toBe(
            "remove-last-point",
        );
        expect(editCommandOf(key("Backspace"), "draw")).toBe("remove-last-point");
        expect(editCommandOf(key("Escape"), "draw")).toBe("abort");
    });

    test("selecting, or typing in a field, is left alone", () => {
        expect(editCommandOf(key("z", { ctrlKey: true }), "select")).toBe(null);
        const input = document.createElement("input");
        expect(editCommandOf(key("z", { ctrlKey: true }, input), "modify")).toBe(null);
        expect(editCommandOf(key("Backspace", {}, input), "draw")).toBe(null);
    });
});

describe("reshaping a record (production)", () => {
    let ol;

    before(async () => {
        await withFetch(globalCachedFetch, () => loadGeoLibs());
        ({ ol } = geoLibs());
    });

    const SQUARE = [
        [
            [0, 0],
            [10, 0],
            [10, 10],
            [0, 10],
            [0, 0],
        ],
    ];
    const MOVED = [
        [
            [0, 0],
            [20, 0],
            [20, 10],
            [0, 10],
            [0, 0],
        ],
    ];

    const session = (answer = async () => null) => {
        const written = [];
        const checks = [];
        const notified = [];
        const layers = [];
        const source = new ol.source.Vector();
        const feature = new ol.Feature({
            geometry: new ol.geom.Polygon(MOVED),
            geoField: "area",
        });
        feature.setId(7);
        source.addFeature(feature);
        const renderer = {
            props: {
                model: {
                    root: {
                        resModel: "agro.plot",
                        records: [{ resId: 7, switchMode: async () => {} }],
                    },
                    orm: {
                        silent: {
                            call: async (...args) => {
                                checks.push(args);
                                return answer(args);
                            },
                        },
                    },
                },
                updateRecord: async (value, geoField) =>
                    written.push([geoField, JSON.parse(value).coordinates]),
            },
            map: {
                addLayer: (layer) => layers.push(layer),
                removeLayer: (layer) => layers.splice(layers.indexOf(layer), 1),
                getView: () => ({ getProjection: () => ol.proj.get("EPSG:3857") }),
            },
            notification: {
                add: (message, options) => notified.push([message, options]),
            },
            vectorLayersResult: [{ getSource: () => source }],
        };
        const interactions = new GeoengineRendererInteractions(renderer);
        interactions.tool = "modify";
        interactions.history.record({
            resId: 7,
            geoField: "area",
            before: new ol.geom.Polygon(SQUARE),
            after: new ol.geom.Polygon(MOVED),
        });
        return { interactions, feature, written, checks, notified, layers };
    };

    test("undo writes the shape before the reshape back to its record, redo the one after", async () => {
        const { interactions, feature, written } = session();
        await interactions.undo();
        expect(written).toEqual([["area", SQUARE]]);
        expect(feature.getGeometry().getCoordinates()).toEqual(SQUARE);
        await interactions.redo();
        expect(written.at(-1)).toEqual(["area", MOVED]);
        expect(feature.getGeometry().getCoordinates()).toEqual(MOVED);
    });

    test("each written shape is checked, and a problem is marked where it is", async () => {
        const { interactions, checks, notified, layers } = session(async () => ({
            message: "The outline crosses itself here.",
            location: [5, 5],
        }));
        await interactions.undo();
        expect(
            checks.map(([model, method, [field]]) => [model, method, field]),
        ).toEqual([["agro.plot", "get_geometry_problem", "area"]]);
        expect(notified.map(([message]) => message)).toEqual([
            "The outline crosses itself here.",
        ]);
        expect(interactions._problemMarker.location).toEqual([5, 5]);
        expect(layers).toHaveLength(1);
        interactions.teardown();
        expect(layers).toHaveLength(0);
    });

    test("a check overtaken by a later edit is not shown", async () => {
        const first = new Deferred();
        let calls = 0;
        const { interactions, notified } = session(() =>
            calls++ === 0 ? first : Promise.resolve(null),
        );
        const square = new ol.geom.Polygon(SQUARE);
        const stale = interactions._checkGeometry("agro.plot", "area", square);
        await interactions._checkGeometry("agro.plot", "area", square);
        first.resolve({ message: "stale", location: [1, 1] });
        await stale;
        expect(notified).toEqual([]);
        expect(interactions._problemMarker).toBe(null);
    });

    test("a drawn shape the server would refuse is not offered for saving", async () => {
        const refused = session(async () => ({ message: "crosses", location: [5, 5] }));
        const square = new ol.geom.Polygon(SQUARE);
        expect(
            await refused.interactions._isStorable("agro.plot", "area", "{}", square),
        ).toBe(false);
        const accepted = session();
        expect(
            await accepted.interactions._isStorable("agro.plot", "area", "{}", square),
        ).toBe(true);
    });

    test("another tool starts a new session: no history, no marker", async () => {
        const { interactions } = session(async () => ({
            message: "m",
            location: [5, 5],
        }));
        await interactions.undo();
        interactions._enterTool("select");
        expect(interactions.history.canUndo).toBe(false);
        expect(interactions.history.canRedo).toBe(false);
        expect(interactions._problemMarker.location).toBe(null);
    });
});

describe("editing a shape's areas (production)", () => {
    let ol;

    before(async () => {
        await withFetch(globalCachedFetch, () => loadGeoLibs());
        ({ ol } = geoLibs());
    });

    const square = (x) => [
        [
            [x, 0],
            [x + 10, 0],
            [x + 10, 10],
            [x, 10],
            [x, 0],
        ],
    ];

    const areas = (answer) => {
        const calls = [];
        const written = [];
        const notified = [];
        const feature = new ol.Feature({
            geometry: new ol.geom.Polygon(square(0)),
            geoField: "zones",
        });
        feature.setId(3);
        const selected = new ol.Collection([feature]);
        const source = new ol.source.Vector({ features: [feature] });
        const renderer = {
            props: {
                model: {
                    root: {
                        resModel: "device.geo.fence",
                        records: [{ resId: 3, switchMode: async () => {} }],
                    },
                    orm: {
                        silent: {
                            call: async (...args) => {
                                calls.push(args);
                                return args[1] === "get_edited_shape" ? answer() : null;
                            },
                        },
                    },
                },
                updateRecord: async (value, geoField) =>
                    written.push([geoField, JSON.parse(value).type]),
            },
            state: {},
            map: {
                getView: () => ({ getProjection: () => ol.proj.get("EPSG:3857") }),
            },
            modifyClick: { getFeatures: () => selected, setActive: () => {} },
            notification: {
                add: (message, options) => notified.push([message, options]),
            },
            vectorLayersResult: [{ getSource: () => source }],
        };
        const interactions = new GeoengineRendererInteractions(renderer);
        interactions.tool = "modify";
        return { interactions, feature, calls, written, notified };
    };

    test("a part count reads a multi geometry's members", () => {
        expect(partCount(undefined)).toBe(0);
        expect(partCount(new ol.geom.Polygon(square(0)))).toBe(1);
        const two = new ol.format.GeoJSON().readGeometry({
            type: "MultiPolygon",
            coordinates: [square(0), square(50)],
        });
        expect(partCount(two)).toBe(2);
    });

    test("an added area comes back from the server and is written as an undoable reshape", async () => {
        const edited = JSON.stringify({
            type: "MultiPolygon",
            coordinates: [square(0), square(50)],
        });
        const { interactions, feature, calls, written } = areas(async () => edited);
        await interactions._applyShapeEdit(
            feature,
            "add_area",
            new ol.geom.Polygon(square(50)),
        );
        const [, method, [field, value, sketch, edit]] = calls[0];
        expect([method, field, edit]).toEqual([
            "get_edited_shape",
            "zones",
            "add_area",
        ]);
        expect(JSON.parse(value).coordinates).toEqual(square(0));
        expect(JSON.parse(sketch).coordinates).toEqual(square(50));
        expect(feature.getGeometry().getType()).toBe("MultiPolygon");
        expect(written).toEqual([["zones", "MultiPolygon"]]);
        await interactions.undo();
        expect(feature.getGeometry().getCoordinates()).toEqual(square(0));
        expect(written.at(-1)).toEqual(["zones", "Polygon"]);
    });

    test("an edit the server refuses leaves the shape and says why", async () => {
        const { interactions, feature, written, notified } = areas(async () => {
            throw Object.assign(new Error("rpc"), {
                data: { message: "Nothing of the shape would remain." },
            });
        });
        await interactions._applyShapeEdit(
            feature,
            "cut_area",
            new ol.geom.Polygon(square(0)),
        );
        expect(feature.getGeometry().getCoordinates()).toEqual(square(0));
        expect(written).toEqual([]);
        expect(interactions.history.canUndo).toBe(false);
        expect(notified.map(([message]) => message)).toEqual([
            "Nothing of the shape would remain.",
        ]);
    });

    test("with no shape selected, an area edit does not start", () => {
        const { interactions } = areas(async () => null);
        interactions.renderer.modifyClick = {
            getFeatures: () => new ol.Collection(),
            setActive: () => {},
        };
        interactions._startShapeEdit("add_area");
        expect(interactions._shapeEdit).toBe(null);
    });
});

describe("splitting and merging records (production)", () => {
    let ol;

    before(async () => {
        await withFetch(globalCachedFetch, () => loadGeoLibs());
        ({ ol } = geoLibs());
    });

    const records = ({
        answer = async () => ({ tag: "display_notification" }),
        saves = true,
    } = {}) => {
        const calls = [];
        const done = [];
        const notified = [];
        let loads = 0;
        const feature = (id, geoField = "zones") => {
            const f = new ol.Feature({
                geometry: new ol.geom.Point([id, id]),
                geoField,
            });
            f.setId(id);
            return f;
        };
        const selected = new ol.Collection();
        const renderer = {
            props: {
                model: {
                    root: {
                        resModel: "device.geo.fence",
                        editedRecord: { save: async () => saves },
                        load: async () => loads++,
                    },
                    orm: {
                        silent: {
                            call: async (...args) => {
                                calls.push(args);
                                return answer();
                            },
                        },
                    },
                },
            },
            action: { doAction: async (action) => done.push(action) },
            map: { getView: () => ({ getProjection: () => ol.proj.get("EPSG:3857") }) },
            modifyClick: { getFeatures: () => selected, setActive: () => {} },
            notification: { add: (message) => notified.push(message) },
        };
        const interactions = new GeoengineRendererInteractions(renderer);
        interactions.tool = "modify";
        return {
            interactions,
            feature,
            selected,
            calls,
            done,
            notified,
            loads: () => loads,
        };
    };

    test("shapes of one field merge, in the order they were selected", async () => {
        const { interactions, feature, selected, calls, done, loads } = records();
        selected.extend([feature(9), feature(4)]);
        interactions.history.record({
            resId: 9,
            geoField: "zones",
            before: 1,
            after: 2,
        });
        await interactions._mergeSelectedShapes();
        expect(calls).toEqual([
            ["device.geo.fence", "action_merge_shapes", [[9, 4], "zones"]],
        ]);
        expect(done).toEqual([{ tag: "display_notification" }]);
        expect(loads()).toBe(1);
        expect(interactions.history.canUndo).toBe(false);
        expect(selected.getLength()).toBe(0);
    });

    test("shapes of two fields, or a single shape, do not merge", async () => {
        const { interactions, feature, selected, calls } = records();
        selected.extend([feature(9), feature(4, "route")]);
        expect(interactions._mergeableFeatures()).toEqual([]);
        await interactions._mergeSelectedShapes();
        selected.clear();
        selected.push(feature(9));
        await interactions._mergeSelectedShapes();
        expect(calls).toEqual([]);
    });

    test("a split sends the drawn line for the selected record", async () => {
        const { interactions, feature, calls } = records();
        await interactions._splitShape(
            feature(9),
            new ol.geom.LineString([
                [0, 0],
                [5, 5],
            ]),
        );
        const [[model, method, [ids, field, line]]] = calls;
        expect([model, method, ids, field]).toEqual([
            "device.geo.fence",
            "action_split_shape",
            [9],
            "zones",
        ]);
        expect(JSON.parse(line).coordinates).toEqual([
            [0, 0],
            [5, 5],
        ]);
    });

    test("an edit that cannot be saved stops the split; a refused one says why", async () => {
        const unsaved = records({ saves: false });
        await unsaved.interactions._splitShape(
            unsaved.feature(9),
            new ol.geom.LineString([
                [0, 0],
                [1, 1],
            ]),
        );
        expect(unsaved.calls).toEqual([]);
        const refused = records({
            answer: async () => {
                throw Object.assign(new Error("rpc"), {
                    data: {
                        message:
                            "The line does not cut the shape: draw it across the shape.",
                    },
                });
            },
        });
        await refused.interactions._splitShape(
            refused.feature(9),
            new ol.geom.LineString([
                [0, 0],
                [1, 1],
            ]),
        );
        expect(refused.notified).toEqual([
            "The line does not cut the shape: draw it across the shape.",
        ]);
        expect(refused.loads()).toBe(0);
    });
});
