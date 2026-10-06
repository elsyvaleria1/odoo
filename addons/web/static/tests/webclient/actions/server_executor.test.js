// @ts-check

import { expect, test } from "@odoo/hoot";
import { Deferred } from "@odoo/hoot-mock";
import { makeMockServer, onRpc } from "@web/../tests/web_test_helpers";
import { SupersededError } from "@web/core/utils/concurrency";
import { MAX_ACTION_DEPTH } from "@web/webclient/actions/action_constants";
import { executeServerAction } from "@web/webclient/actions/action_executors/server";
import { NavigationTracker } from "@web/webclient/actions/navigation_token";

/** @param {Object} [overrides] */
function makeFakeAm(overrides = {}) {
    /** @type {Record<string, any[]>} */
    const calls = { doAction: [] };
    const am = {
        navigation: new NavigationTracker(),
        doAction: async (action, options) => {
            calls.doAction.push({ action, options });
            return "doAction-result";
        },
        ...overrides,
    };
    am.__calls = calls;
    return am;
}

test("a null response is normalised to act_window_close", async () => {
    await makeMockServer();
    onRpc("/web/action/run", async () => null);
    const am = makeFakeAm();
    await executeServerAction(/** @type {any} */ ({ id: 1 }), {}, am);
    expect(am.__calls.doAction).toHaveLength(1);
    expect(am.__calls.doAction[0].action.type).toBe("ir.actions.act_window_close");
});

test("a false response is normalised to act_window_close", async () => {
    await makeMockServer();
    onRpc("/web/action/run", async () => false);
    const am = makeFakeAm();
    await executeServerAction(/** @type {any} */ ({ id: 1 }), {}, am);
    expect(am.__calls.doAction[0].action.type).toBe("ir.actions.act_window_close");
});

test("the source action's path is forwarded when the response has none", async () => {
    await makeMockServer();
    onRpc("/web/action/run", async () => ({
        type: "ir.actions.act_window",
        res_model: "x",
    }));
    const am = makeFakeAm();
    await executeServerAction(/** @type {any} */ ({ id: 1, path: "my-path" }), {}, am);
    expect(am.__calls.doAction[0].action.path).toBe("my-path");
});

test("a path already on the response wins over the source action's", async () => {
    await makeMockServer();
    onRpc("/web/action/run", async () => ({
        type: "ir.actions.act_window",
        path: "kept",
    }));
    const am = makeFakeAm();
    await executeServerAction(/** @type {any} */ ({ id: 1, path: "ignored" }), {}, am);
    expect(am.__calls.doAction[0].action.path).toBe("kept");
});

test("the chaining depth is stamped and incremented on the follow-up", async () => {
    await makeMockServer();
    onRpc("/web/action/run", async () => ({ type: "ir.actions.act_window" }));
    const am = makeFakeAm();
    await executeServerAction(/** @type {any} */ ({ id: 1 }), { _actionDepth: 3 }, am);
    expect(am.__calls.doAction[0].options._actionDepth).toBe(4);
});

test("an absent depth starts the chain at 1", async () => {
    await makeMockServer();
    onRpc("/web/action/run", async () => ({ type: "ir.actions.act_window" }));
    const am = makeFakeAm();
    await executeServerAction(/** @type {any} */ ({ id: 1 }), {}, am);
    expect(am.__calls.doAction[0].options._actionDepth).toBe(1);
});

test("a runaway server-action chain is stopped at MAX_ACTION_DEPTH", async () => {
    await makeMockServer();
    onRpc("/web/action/run", async () => ({ type: "ir.actions.act_window" }));
    const am = makeFakeAm();
    await expect(
        executeServerAction(
            /** @type {any} */ ({ id: 1 }),
            { _actionDepth: MAX_ACTION_DEPTH },
            am,
        ),
    ).rejects.toThrow(/recursion limit exceeded/);
    expect(am.__calls.doAction).toEqual([]);
});

test("caller options are forwarded to the follow-up doAction", async () => {
    await makeMockServer();
    onRpc("/web/action/run", async () => ({ type: "ir.actions.act_window" }));
    const am = makeFakeAm();
    const onClose = () => {};
    await executeServerAction(
        /** @type {any} */ ({ id: 1 }),
        { onClose, clearBreadcrumbs: true },
        am,
    );
    const { options } = am.__calls.doAction[0];
    expect(options.onClose).toBe(onClose);
    expect(options.clearBreadcrumbs).toBe(true);
});

test("the navigation guard drops a superseded run: only the latest dispatches", async () => {
    await makeMockServer();
    const first = new Deferred();
    let call = 0;
    onRpc("/web/action/run", async () => {
        call++;
        return call === 1 ? first : { type: "ir.actions.act_window", id: 2 };
    });
    const am = makeFakeAm();

    const p1 = executeServerAction(/** @type {any} */ ({ id: 1 }), {}, am);
    const p2 = executeServerAction(/** @type {any} */ ({ id: 2 }), {}, am);
    await expect(p1).rejects.toThrow(SupersededError);
    await p2;
    first.resolve({ type: "ir.actions.act_window", id: 1 });

    expect(am.__calls.doAction).toHaveLength(1);
    expect(am.__calls.doAction[0].action.id).toBe(2);
});

/** @param {any} [known] */
function makeFakeViewService(known) {
    /** @type {any[]} */
    const offered = [];
    /** @type {Record<number, any>} */
    const remembered = {};
    return {
        offered,
        remembered,
        requestFlags: () => ({ mobile: false, debug: true }),
        knownRunViews: (/** @type {number} */ id) => remembered[id] ?? known,
        rememberRunViews: (/** @type {number} */ id, /** @type {any} */ request) => {
            remembered[id] = request;
        },
        offerViews: (/** @type {any} */ request, /** @type {any} */ views) => {
            offered.push({ request, views });
        },
    };
}

const VIEWS_REQUEST = {
    model: "x",
    views: [[false, "list"]],
    context: {},
    options: {},
};

test("a first run asks for the views of the window action it returns", async () => {
    await makeMockServer();
    onRpc("/web/action/run", async (request) => {
        const { params } = await request.json();
        expect.step(params.views_known ? "known" : "unknown");
        expect(params.view_options).toEqual({ mobile: false, debug: true });
        expect(params.view_context).toEqual({ a: 1 });
        return {
            action: { type: "ir.actions.act_window", res_model: "x" },
            views_request: VIEWS_REQUEST,
            views: { views: {} },
        };
    });
    const viewService = makeFakeViewService();
    const am = makeFakeAm({ viewService });
    await executeServerAction(
        /** @type {any} */ ({ id: 1 }),
        { additionalContext: { a: 1 } },
        am,
    );
    expect.verifySteps(["unknown"]);
    expect(am.__calls.doAction[0].action.res_model).toBe("x");
    expect(viewService.offered).toEqual([
        { request: VIEWS_REQUEST, views: { views: {} } },
    ]);
    expect(viewService.remembered[1]).toEqual(VIEWS_REQUEST);
});

test("a run whose views are held says so, and takes the action alone", async () => {
    await makeMockServer();
    onRpc("/web/action/run", async (request) => {
        const { params } = await request.json();
        expect(params.views_known).toEqual(VIEWS_REQUEST);
        return {
            action: { type: "ir.actions.act_window", res_model: "x" },
            views_request: VIEWS_REQUEST,
        };
    });
    const viewService = makeFakeViewService(VIEWS_REQUEST);
    const am = makeFakeAm({ viewService });
    await executeServerAction(/** @type {any} */ ({ id: 1 }), {}, am);
    expect(am.__calls.doAction[0].action.res_model).toBe("x");
    expect(viewService.offered).toEqual([]);
});

test("an answer without a views request is the next action", async () => {
    await makeMockServer();
    onRpc("/web/action/run", async () => ({ type: "ir.actions.act_window_close" }));
    const viewService = makeFakeViewService();
    const am = makeFakeAm({ viewService });
    await executeServerAction(/** @type {any} */ ({ id: 1 }), {}, am);
    expect(am.__calls.doAction[0].action.type).toBe("ir.actions.act_window_close");
    expect(viewService.remembered).toEqual({});
});
