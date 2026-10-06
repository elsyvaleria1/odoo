// @ts-check

import { after, describe, expect, test } from "@odoo/hoot";
import {
    defineModels,
    getService,
    makeMockEnv,
    models,
    onRpc,
} from "@web/../tests/web_test_helpers";
import {
    disableLogging,
    enableLogging,
    getStats,
    getStatus,
} from "@web/core/debug/debug_logger";
import { viewService } from "@web/views/view_service";

describe.current.tags("headless");

test("failed view loads finish their timing span and preserve the error", async () => {
    const { spec } = getStatus();
    after(() =>
        spec
            ? enableLogging(spec, { persist: false })
            : disableLogging({ persist: false }),
    );
    enableLogging("web.view:perf", { persist: false });
    const failure = new Error("view load failed");
    const orm = {
        cache() {
            return this;
        },
        retry() {
            return this;
        },
        async call() {
            throw failure;
        },
    };
    const service = viewService.start(await makeMockEnv(), { orm });
    after(() => service.destroy());
    const count = () =>
        getStats()
            .filter(
                (row) => row.ns === "web.view" && row.label === "get_views timing_test",
            )
            .reduce((sum, row) => sum + row.count, 0);
    const before = count();
    let caught;
    try {
        await service.loadViews({ resModel: "timing_test", views: [] });
    } catch (error) {
        caught = error;
    }
    expect(caught).toBe(failure);
    expect(count()).toBe(before + 1);
});

class TakeFive extends models.Model {
    _name = "take.five";
    _views = {
        "list,99": `<list><field name="display_name" /></list>`,
    };
}

class IrUiView extends models.Model {
    _name = "ir.ui.view";
}

defineModels([TakeFive, IrUiView]);

test("stores calls in cache in success", async () => {
    expect.assertions(1);
    onRpc("get_views", () => {
        expect.step("get_views");
    });
    await makeMockEnv();
    await getService("view").loadViews(
        {
            resModel: "take.five",
            views: [[99, "list"]],
            context: { default_field_value: 1 },
        },
        {},
    );
    await getService("view").loadViews(
        {
            resModel: "take.five",
            views: [[99, "list"]],
            context: { default_field_value: 2 },
        },
        {},
    );
    expect.verifySteps(["get_views"]);
});

test("stores calls in cache when failed", async () => {
    expect.assertions(3);
    onRpc("get_views", () => {
        expect.step("get_views");
        throw new Error("my little error");
    });
    await makeMockEnv();
    await expect(
        getService("view").loadViews(
            {
                resModel: "take.five",
                views: [[99, "list"]],
            },
            {},
        ),
    ).rejects.toThrow(/my little error/);
    await expect(
        getService("view").loadViews(
            {
                resModel: "take.five",
                views: [[99, "list"]],
            },
            {},
        ),
    ).rejects.toThrow(/my little error/);
    expect.verifySteps(["get_views", "get_views"]);
});

test("clear cache when updating ir.ui.view", async () => {
    expect.assertions(4);
    onRpc("get_views", () => {
        expect.step("get_views");
    });
    await makeMockEnv();
    const loadView = () =>
        getService("view").loadViews(
            {
                resModel: "take.five",
                views: [[99, "list"]],
                context: { default_field_value: 1 },
            },
            {},
        );
    await loadView();
    expect.verifySteps(["get_views"]);
    await loadView();
    expect.verifySteps([]);
    await getService("orm").unlink("ir.ui.view", [3]);
    await loadView();
    expect.verifySteps(["get_views"]);
    await getService("orm").unlink("take.five", [3]);
    await loadView();
    expect.verifySteps([]);
});

test("clear cache when creating an ir.filters favorite (create_filter)", async () => {
    onRpc("get_views", () => {
        expect.step("get_views");
    });
    onRpc("create_filter", () => [7]);
    await makeMockEnv();
    const loadView = () =>
        getService("view").loadViews(
            { resModel: "take.five", views: [[99, "list"]], context: {} },
            {},
        );
    await loadView();
    expect.verifySteps(["get_views"]);
    await loadView();
    expect.verifySteps([]);
    await getService("orm").call("ir.filters", "create_filter", [{ name: "F" }]);
    await loadView();
    expect.verifySteps(["get_views"]);
});

const OFFERED_REQUEST = {
    model: "take.five",
    views: [[99, "list"]],
    context: {},
    options: {
        action_id: false,
        embedded_action_id: false,
        embedded_parent_res_id: false,
        load_filters: false,
        toolbar: false,
        arch: false,
    },
};

/** @returns {Promise<any>} a get_views answer, as the server sends it */
async function getViewsAnswer() {
    const { model, views, context, options } = OFFERED_REQUEST;
    return getService("orm").call(model, "get_views", [], { context, views, options });
}

test("an answer offered for the exact request is taken instead of the network, and kept", async () => {
    onRpc("get_views", () => {
        expect.step("get_views");
    });
    await makeMockEnv();
    const answer = await getViewsAnswer();
    expect.verifySteps(["get_views"]);

    getService("view").offerViews(OFFERED_REQUEST, answer);
    const loaded = await getService("view").loadViews(
        { resModel: "take.five", views: [[99, "list"]], context: {} },
        {},
    );
    expect(Object.keys(loaded.views)).toEqual(["list"]);
    await getService("view").loadViews(
        { resModel: "take.five", views: [[99, "list"]], context: {} },
        {},
    );
    expect.verifySteps([]);
});

test("an answer offered for another request is not taken", async () => {
    onRpc("get_views", () => {
        expect.step("get_views");
    });
    await makeMockEnv();
    const answer = await getViewsAnswer();
    expect.verifySteps(["get_views"]);

    getService("view").offerViews(
        { ...OFFERED_REQUEST, options: { ...OFFERED_REQUEST.options, toolbar: true } },
        answer,
    );
    await getService("view").loadViews(
        { resModel: "take.five", views: [[99, "list"]], context: {} },
        {},
    );
    expect.verifySteps(["get_views"]);
});

test("a change to the views drops what was offered", async () => {
    onRpc("get_views", () => {
        expect.step("get_views");
    });
    await makeMockEnv();
    const answer = await getViewsAnswer();
    expect.verifySteps(["get_views"]);

    getService("view").offerViews(OFFERED_REQUEST, answer);
    await getService("orm").unlink("ir.ui.view", [3]);
    await getService("view").loadViews(
        { resModel: "take.five", views: [[99, "list"]], context: {} },
        {},
    );
    expect.verifySteps(["get_views"]);
});

test("a server action's remembered request is known while its views are cached", async () => {
    await makeMockEnv();
    const view = getService("view");
    view.rememberRunViews(7, OFFERED_REQUEST);
    expect(view.knownRunViews(7)).toBe(undefined);

    await view.loadViews(
        { resModel: "take.five", views: [[99, "list"]], context: {} },
        {},
    );
    expect(view.knownRunViews(7)).toEqual(OFFERED_REQUEST);
    expect(view.knownRunViews(8)).toBe(undefined);

    await getService("orm").unlink("ir.ui.view", [3]);
    expect(view.knownRunViews(7)).toBe(undefined);
});
