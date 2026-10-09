import { describe, expect, test } from "@odoo/hoot";
import { createRelatedModels } from "@point_of_sale/app/models/related_models";
import { makeMockServer } from "@web/../tests/web_test_helpers";
import { effect } from "@web/core/utils/reactive";

import { definePosModels } from "../data/generate_model_definitions.js";
import {
    getModelDefinitions,
    getRelatedModelsInstance,
} from "../data/get_model_definitions.js";

definePosModels();

const LINK = "product.template.pos_categ_ids";

function countIndexBuilds(models) {
    const model = models["product.template"];
    const state = { builds: 0 };
    const original = model.addEventListener.bind(model);
    model.addEventListener = function (...args) {
        state.builds++;
        return original(...args);
    };
    return {
        get value() {
            return state.builds / 3;
        },
        reset() {
            state.builds = 0;
        },
    };
}

describe("backLink index", () => {
    test("is built once and survives reads", async () => {
        await makeMockServer();
        const models = getRelatedModelsInstance(false);
        const category = models["pos.category"].create({});
        for (let i = 0; i < 50; i++) {
            models["product.template"].create({ pos_categ_ids: [category] });
        }
        const builds = countIndexBuilds(models);
        builds.reset();
        for (let i = 0; i < 20; i++) {
            expect(category.backLink(LINK)).toHaveLength(50);
        }
        expect(builds.value).toBe(1);
    });

    test("a write that does not touch the inverse field never rebuilds it", async () => {
        await makeMockServer();
        const models = getRelatedModelsInstance(false);
        const category = models["pos.category"].create({});
        for (let i = 0; i < 50; i++) {
            models["product.template"].create({ pos_categ_ids: [category] });
        }
        const templates = models["product.template"].getAll();
        const builds = countIndexBuilds(models);
        category.backLink(LINK);
        builds.reset();

        for (let i = 0; i < 20; i++) {
            templates[i].name = `renamed-${i}`;
            expect(category.backLink(LINK)).toHaveLength(50);
        }
        expect(builds.value).toBe(0);
    });

    test("tracks creates, deletes and reparenting incrementally", async () => {
        await makeMockServer();
        const models = getRelatedModelsInstance(false);
        const catA = models["pos.category"].create({});
        const catB = models["pos.category"].create({});
        const first = models["product.template"].create({ pos_categ_ids: [catA] });
        const builds = countIndexBuilds(models);
        expect(catA.backLink(LINK)).toEqual([first]);
        builds.reset();

        const second = models["product.template"].create({ pos_categ_ids: [catA] });
        expect(catA.backLink(LINK)).toEqual([first, second]);

        second.pos_categ_ids = [catB];
        expect(catA.backLink(LINK)).toEqual([first]);
        expect(catB.backLink(LINK)).toEqual([second]);

        models["product.template"].delete(first);
        expect(catA.backLink(LINK)).toEqual([]);

        const shared = models["product.template"].create({
            pos_categ_ids: [catA, catB],
        });
        expect(catA.backLink(LINK)).toEqual([shared]);
        expect(catB.backLink(LINK)).toEqual([second, shared]);

        models["product.template"].delete(shared);
        expect(catA.backLink(LINK)).toEqual([]);
        expect(catB.backLink(LINK)).toEqual([second]);

        expect(builds.value).toBe(0);
    });

    test("keeps store insertion order across re-parenting", async () => {
        await makeMockServer();
        const models = getRelatedModelsInstance(false);
        const category = models["pos.category"].create({});
        const first = models["product.template"].create({ pos_categ_ids: [category] });
        const second = models["product.template"].create({ pos_categ_ids: [category] });
        expect(category.backLink(LINK)).toEqual([first, second]);

        first.pos_categ_ids = [];
        expect(category.backLink(LINK)).toEqual([second]);
        first.pos_categ_ids = [category];
        expect(category.backLink(LINK)).toEqual([first, second]);

        const third = models["product.template"].create({ pos_categ_ids: [category] });
        expect(category.backLink(LINK)).toEqual([first, second, third]);
    });

    test("a record that gains a parent later sorts into its store position", async () => {
        await makeMockServer();
        const models = getRelatedModelsInstance(false);
        const category = models["pos.category"].create({});
        const first = models["product.template"].create({ pos_categ_ids: [category] });
        const middle = models["product.template"].create({ pos_categ_ids: [] });
        const last = models["product.template"].create({ pos_categ_ids: [category] });
        expect(category.backLink(LINK)).toEqual([first, last]);

        middle.pos_categ_ids = [category];
        expect(category.backLink(LINK)).toEqual([first, middle, last]);
    });

    test("deleting the parent empties its bucket", async () => {
        await makeMockServer();
        const models = getRelatedModelsInstance(false);
        const category = models["pos.category"].create({});
        const template = models["product.template"].create({
            pos_categ_ids: [category],
        });
        expect(category.backLink(LINK)).toEqual([template]);
        models["pos.category"].delete(category);
        expect(category.backLink(LINK)).toEqual([]);
    });

    test("loading a batch of records keeps the index consistent", async () => {
        await makeMockServer();
        const models = getRelatedModelsInstance(false);
        const category = models["pos.category"].create({});
        models.connectNewData({
            "product.template": [
                { id: 4001, pos_categ_ids: [category.id] },
                { id: 4002, pos_categ_ids: [category.id] },
            ],
        });
        expect(category.backLink(LINK).map((r) => r.id)).toEqual([4001, 4002]);

        models.connectNewData({
            "product.template": [{ id: 4002, pos_categ_ids: [] }],
        });
        expect(category.backLink(LINK).map((r) => r.id)).toEqual([4001]);
    });
});

describe("delete command bookkeeping", () => {
    test("deleting a parent records no command under the child's m2o field", async () => {
        await makeMockServer();
        const models = getRelatedModelsInstance(false);
        models.loadConnectedData({
            "pos.order": [{ id: 1, uuid: "o1", lines: [11, 12, 13] }],
            "pos.order.line": [
                { id: 11, uuid: "l1", order_id: 1 },
                { id: 12, uuid: "l2", order_id: 1 },
                { id: 13, uuid: "l3", order_id: 1 },
            ],
        });
        const order = models["pos.order"].get(1);
        expect(order.lines).toHaveLength(3);

        models["pos.order"].delete(order);

        expect([...models.commands["pos.order.line"].unlink.entries()]).toEqual([]);
        expect(models._pendingDeletionIds().has("pos.order")).toBe(false);
    });

    test("deleting a parent drops the commands its deleted children left", async () => {
        await makeMockServer();
        const models = getRelatedModelsInstance(false);
        models.loadConnectedData({
            "pos.order": [
                { id: 1, uuid: "o1", lines: [11, 12, 13] },
                { id: 2, uuid: "o2", lines: [21] },
            ],
            "pos.order.line": [
                { id: 11, uuid: "l11", order_id: 1 },
                { id: 12, uuid: "l12", order_id: 1 },
                { id: 13, uuid: "l13", order_id: 1 },
                { id: 21, uuid: "l21", order_id: 2 },
            ],
        });
        for (const id of [11, 12, 21]) {
            models["pos.order.line"].delete(models["pos.order.line"].get(id));
        }

        models["pos.order"].delete(models["pos.order"].get(1));

        expect([...models.commands["pos.order"].unlink.entries()]).toEqual([
            ["lines", [{ id: 21, parentId: 2 }]],
        ]);
    });

    test("a reload skips the children pending deletion and only those", async () => {
        await makeMockServer();
        const models = getRelatedModelsInstance(false);
        const rows = {
            "pos.order": [{ id: 3, uuid: "o3", lines: [31, 32] }],
            "pos.order.line": [
                { id: 31, uuid: "l31", order_id: 3 },
                { id: 32, uuid: "l32", order_id: 3 },
            ],
        };
        models.loadConnectedData(rows);
        models["pos.order.line"].delete(models["pos.order.line"].get(31));

        models.loadConnectedData({
            ...rows,
            "pos.order.line": [
                ...rows["pos.order.line"],
                { id: 33, uuid: "l33", order_id: 3 },
            ],
        });

        expect(models["pos.order.line"].get(31)).toBe(undefined);
        expect(models["pos.order.line"].getMany([32, 33]).map((l) => l.id)).toEqual([
            32, 33,
        ]);
    });

    test("deleting a child still records the unlink on its parent", async () => {
        await makeMockServer();
        const models = getRelatedModelsInstance(false);
        models.loadConnectedData({
            "pos.order": [{ id: 2, uuid: "o2", lines: [21] }],
            "pos.order.line": [{ id: 21, uuid: "l21", order_id: 2 }],
        });
        models["pos.order.line"].delete(models["pos.order.line"].get(21));
        expect([...models.commands["pos.order"].unlink.entries()]).toEqual([
            ["lines", [{ id: 21, parentId: 2 }]],
        ]);
    });
});

describe("createRelatedModels options", () => {
    test("works without a databaseTable option", async () => {
        await makeMockServer();
        const { models } = createRelatedModels(getModelDefinitions(), {}, {});
        models.loadConnectedData({
            "pos.order": [{ id: 3, uuid: "o3", lines: [31] }],
            "pos.order.line": [{ id: 31, uuid: "l31", order_id: 3 }],
        });
        expect(() =>
            models.connectNewData({
                "pos.order": [{ id: 3, uuid: "o3", lines: [31] }],
            }),
        ).not.toThrow();
        expect(models["pos.order"].get(3).lines).toHaveLength(1);
    });
});

test("backLink results are reactive on a warm cache", async () => {
    await makeMockServer();
    const models = getRelatedModelsInstance(false);
    const order = models["pos.order"].create({ id: 31 });
    const att = models["product.template.attribute.value"].create({ id: 99 });
    models["pos.order.line"].create({
        id: 310,
        order_id: order,
        attribute_value_ids: [["link", att]],
    });

    expect(att.backLink("<-pos.order.line.attribute_value_ids")).toHaveLength(1);

    let seen = 0;
    effect(
        (a) => {
            seen = a.backLink("<-pos.order.line.attribute_value_ids").length;
        },
        [att],
    );
    expect(seen).toBe(1);
    models["pos.order.line"].create({
        id: 311,
        order_id: order,
        attribute_value_ids: [["link", att]],
    });
    expect(seen).toBe(2);
});
