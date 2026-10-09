import { describe, expect, test } from "@odoo/hoot";
import { DataServiceOptions } from "@point_of_sale/app/models/data_service_options";

import { definePosModels } from "../data/generate_model_definitions.js";

definePosModels();

const CURRENT_SESSION = 1;

function databaseTable() {
    globalThis.odoo = globalThis.odoo || {};
    odoo.pos_session_id = CURRENT_SESSION;
    return new DataServiceOptions().databaseTable;
}

const pastSessionPaidOrder = (values = {}) => ({
    finalized: true,
    isSynced: true,
    id: 7,
    session_id: { id: CURRENT_SESSION + 1 },
    ...values,
});

describe("an order's rows are purged with the order", () => {
    test("a current-session paid order and its line and payment are kept alike", () => {
        const tables = databaseTable();
        const order = {
            finalized: true,
            isSynced: true,
            session_id: { id: CURRENT_SESSION },
        };

        const orderPurged = tables["pos.order"].condition(order);

        expect(orderPurged).toBe(false);
        expect(tables["pos.order.line"].condition({ order_id: order })).toBe(
            orderPurged,
        );
        expect(tables["pos.payment"].condition({ pos_order_id: order })).toBe(
            orderPurged,
        );
    });

    test("every row's purge condition follows its order", () => {
        const tables = databaseTable();
        const purgeAll = (order) => ({
            order: tables["pos.order"].condition(order),
            line: tables["pos.order.line"].condition({ order_id: order }),
            payment: tables["pos.payment"].condition({ pos_order_id: order }),
            customValue: tables["product.attribute.custom.value"].condition({
                order_id: order,
            }),
        });

        expect(
            purgeAll(pastSessionPaidOrder({ session_id: { id: CURRENT_SESSION } })),
        ).toEqual({ order: false, line: false, payment: false, customValue: false });

        expect(purgeAll(pastSessionPaidOrder())).toEqual({
            order: true,
            line: true,
            payment: true,
            customValue: true,
        });

        expect(
            purgeAll({
                finalized: false,
                isSynced: false,
                session_id: { id: CURRENT_SESSION },
            }),
        ).toEqual({ order: false, line: false, payment: false, customValue: false });

        expect(purgeAll(undefined)).toEqual({
            order: false,
            line: false,
            payment: false,
            customValue: false,
        });
    });
});

describe("a past-session paid order is purged only when nothing still needs it", () => {
    test("an unsynced edit keeps it", () => {
        const tables = databaseTable();
        expect(
            tables["pos.order"].condition(pastSessionPaidOrder({ _dirty: true })),
        ).toBe(false);
    });

    test("a pending refund of one of its lines keeps it, until the refund is settled", () => {
        const tables = databaseTable();
        const refund = { finalized: false, isSynced: false };
        const refunded = pastSessionPaidOrder({
            lines: [{ refund_orderline_ids: [{ order_id: refund }] }],
        });

        expect(tables["pos.order"].condition(refunded)).toBe(false);

        Object.assign(refund, pastSessionPaidOrder({ id: 8 }));
        expect(tables["pos.order"].condition(refunded)).toBe(true);
    });
});
