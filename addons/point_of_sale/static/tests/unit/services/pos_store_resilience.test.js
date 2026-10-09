import { describe, expect, test } from "@odoo/hoot";
import { Deferred } from "@odoo/hoot-mock";
import { patchWithCleanup } from "@web/../tests/web_test_helpers";
import { ConnectionLostError } from "@web/core/network";

import { definePosModels } from "../data/generate_model_definitions.js";
import { getFilledOrder, setupPosEnv } from "../utils.js";

definePosModels();

test("canceling the customer editor settles without reading an unsaved customer", async () => {
    const store = await setupPosEnv();
    let options;
    store.action = {
        doAction: async (request, args) => {
            options = args;
        },
    };
    store.data.read = () => expect.step("read customer");
    const result = store.editPartner();
    await options.onClose();
    expect(await result).toBe(undefined);
    expect.verifySteps([]);
});

describe("pos_store.js resilience", () => {
    describe("removeOrders", () => {
        test("one failing order does not abort the batch nor throw", async () => {
            const store = await setupPosEnv();
            const order1 = await getFilledOrder(store);
            const order2 = await getFilledOrder(store);
            const order3 = await getFilledOrder(store);
            await store.syncAllOrders({ orders: [order1, order2, order3] });
            expect(order2.isSynced).toBe(true);

            const call = store.data.call.bind(store.data);
            store.data.call = async (model, method, args, kwargs) => {
                if (
                    method === "action_pos_order_cancel" &&
                    args[0].includes(order2.id)
                ) {
                    throw new Error("Order already invoiced");
                }
                return call(model, method, args, kwargs);
            };
            const dialogs = [];
            store.dialog = {
                add: (component, props) => {
                    dialogs.push(props);
                    return () => {};
                },
            };

            const result = await store.removeOrders([order1, order2, order3]);

            expect(result).toBe(false);
            expect(store.models["pos.order"].getBy("uuid", order1.uuid)).toBeEmpty();
            expect(store.models["pos.order"].getBy("uuid", order3.uuid)).toBeEmpty();
            expect(
                store.models["pos.order"].getBy("uuid", order2.uuid),
            ).not.toBeEmpty();
            expect(dialogs).toHaveLength(1);
            expect(dialogs[0].body).toInclude(order2.getName());
        });

        test("a fully successful batch still reports true", async () => {
            const store = await setupPosEnv();
            const order1 = await getFilledOrder(store);
            const order2 = await getFilledOrder(store);
            await store.syncAllOrders({ orders: [order1, order2] });

            expect(await store.removeOrders([order1, order2])).toBe(true);
            expect(store.getOpenOrders()).toHaveLength(0);
        });
    });

    describe("printReceipt", () => {
        test("printing a clean synced order leaves no dirty residue", async () => {
            const store = await setupPosEnv();
            const order = await getFilledOrder(store);
            await store.syncAllOrders({ orders: [order] });
            order._markClean();
            expect(order.isDirty()).toBe(false);

            store.printer = { print: async () => true };
            await store.printReceipt({ order });

            expect(order.isDirty()).toBe(false);
            expect([...order._dirtyFields]).toEqual([]);
        });

        test("concurrent prints do not lose an increment", async () => {
            const store = await setupPosEnv();
            const order = await getFilledOrder(store);
            await store.syncAllOrders({ orders: [order] });
            expect(order.nb_print || 0).toBe(0);

            store.printer = { print: async () => true };
            const gate = new Deferred();
            store.data.write = async (model, ids, vals) => {
                await gate;
                const record = store.models[model].get(ids[0]);
                record.update(vals, { omitUnknownField: true });
                return [record];
            };

            const printed = Promise.all([
                store.printReceipt({ order }),
                store.printReceipt({ order }),
            ]);
            gate.resolve();
            await printed;

            expect(order.nb_print).toBe(2);
        });
    });

    describe("handleUrlParams", () => {
        test("a paramless route keeps the selected order", async () => {
            const store = await setupPosEnv();
            const order = await getFilledOrder(store);
            store.setOrder(order);
            expect(store.getOrder().uuid).toBe(order.uuid);

            delete store.router.state.params.orderUuid;
            await store.handleUrlParams();

            expect(store.getOrder()?.uuid).toBe(order.uuid);
        });

        test("a route carrying an orderUuid still selects that order", async () => {
            const store = await setupPosEnv();
            const order1 = await getFilledOrder(store);
            const order2 = await getFilledOrder(store);
            store.setOrder(order1);

            store.router.state.params.orderUuid = order2.uuid;
            await store.handleUrlParams();

            expect(store.getOrder().uuid).toBe(order2.uuid);
        });

        test("an order the device does not hold opens the default screen when the server cannot be reached", async () => {
            const store = await setupPosEnv();
            const unknown = "00000000-0000-4000-8000-000000000000";
            const notifications = [];
            patchWithCleanup(store.notification, {
                add: (message, options) => notifications.push({ message, options }),
            });
            patchWithCleanup(store.data, {
                loadServerOrders: async () => {
                    throw new ConnectionLostError();
                },
            });

            const navigations = [];
            patchWithCleanup(store.router, {
                navigate: (...args) => navigations.push(args),
            });

            store.router.state.params.orderUuid = unknown;
            await store.handleUrlParams();

            expect(navigations).toHaveLength(1);
            const [page, params, options] = navigations[0];
            expect(page).toBe("ProductScreen");
            expect(params.orderUuid).not.toBe(unknown);
            expect(store.models["pos.order"].getBy("uuid", params.orderUuid)).not.toBe(
                undefined,
            );
            expect(options).toEqual({ replace: true });
            expect(notifications).toHaveLength(1);
            expect(notifications[0].options.type).toBe("warning");
        });
    });

    describe("closeSession", () => {
        test("closing sends the queued operations first and refuses while any is pending", async () => {
            const store = await setupPosEnv();
            const data = store.data;
            const shown = [];
            patchWithCleanup(store.dialog, {
                add: (_component, props) => shown.push(props),
            });
            patchWithCleanup(store, {
                pushOrdersWithClosingPopup: async () => true,
                getClosePosInfo: async () => {
                    expect.step("closing info");
                },
            });
            data.network.offline = true;
            data.network.unsyncData = [
                {
                    args: [
                        {
                            type: "call",
                            model: "pos.session",
                            method: "try_cash_in_out",
                            args: [
                                [1],
                                "in",
                                9,
                                "float",
                                1,
                                { translatedType: "in", formattedAmount: "$ 9.00" },
                            ],
                            kwargs: {},
                        },
                    ],
                    date: "2025-01-01 00:00:00",
                    try: 1,
                    uuid: "pending-cash-move",
                },
            ];

            await store.closeSession();

            expect.verifySteps([]);
            expect(shown).toHaveLength(1);
            expect(shown[0].body).toInclude("Cash in of $ 9.00 (float)");

            data.network.offline = false;
            patchWithCleanup(data.orm, {
                call: async (_model, method) => {
                    expect.step(method);
                    return true;
                },
            });

            await store.closeSession();

            expect.verifySteps(["try_cash_in_out", "closing info"]);
            expect(data.network.unsyncData).toHaveLength(0);
        });
    });

    describe("lastPrints", () => {
        const addPreparedLine = async (store, order) => {
            await store.addLineToOrder(
                { product_tmpl_id: store.models["product.template"].get(5), qty: 1 },
                order,
            );
        };

        test("a failed print is not recorded as reprintable", async () => {
            const store = await setupPosEnv();
            const order = store.addNewOrder();
            await addPreparedLine(store, order);
            expect(order.uiState.lastPrints).toHaveLength(0);

            store.printChanges = async () => {
                throw new Error("printer unreachable");
            };
            await store.sendOrderInPreparation(order);

            expect(order.uiState.lastPrints).toHaveLength(0);
        });

        test("the history is bounded", async () => {
            const store = await setupPosEnv();
            const order = store.addNewOrder();
            store.printChanges = async () => true;

            for (let i = 0; i < 14; i++) {
                await addPreparedLine(store, order);
                await store.sendOrderInPreparation(order);
            }

            expect(order.uiState.lastPrints.length).toBeLessThan(14);
            expect(order.uiState.lastPrints).toHaveLength(10);
        });
    });
});
