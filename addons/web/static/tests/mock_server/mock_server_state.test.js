// @ts-check

import { describe, expect, test } from "@odoo/hoot";
import { serverState } from "@web/../tests/web_test_helpers";
import { currencies } from "@web/core/currency";
import { user } from "@web/core/user";
import { session } from "@web/session";

describe.current.tags("headless");

test("default state", () => {
    expect(odoo.debug).toBe("");
    const s = /** @type {any} */ ({ ...serverState });
    expect(s).toInclude("view_info");
    delete s.view_info;
    expect(s).toEqual({
        companies: [{ id: 1, name: "Hermit", currency_id: 1 }],
        currencies: [
            { id: 1, name: "USD", position: "before", symbol: "$" },
            { id: 2, name: "EUR", position: "after", symbol: "€" },
        ],
        db: "test",
        debug: "",
        disallowedAncestorCompanies: /** @type {any[]} */ ([]),
        groupId: 11,
        lang: "en",
        multiLang: false,
        odoobotId: 418,
        odoobotUid: 518,
        partnerId: 17,
        partnerName: "Mitchell Admin",
        publicPartnerId: 18,
        publicPartnerName: "Public user",
        publicUserId: 8,
        serverVersion: [1, 0, 0, "final", 0, ""],
        timezone: "taht",
        userContext: {},
        userId: 7,
    });
});

test("state changes should be reflected on user and session", () => {
    expect(serverState.userId).toBe(7);
    expect(user.userId).toBe(7);
    expect(session.uid).toBe(7);

    serverState.userId = 42;

    expect(serverState.userId).toBe(42);
    expect(user.userId).toBe(42);
    expect(session.uid).toBe(42);
});

test("sanity check: server state is unaffected by previous tests", () => {
    expect(serverState.userId).toBe(7);
    expect(user.userId).toBe(7);
    expect(session.uid).toBe(7);
});

test("a currency set through the server state is exposed", () => {
    serverState.currencies = [
        { id: 1, name: "USD", position: "before", symbol: "$" },
        { id: 5, name: "MXN", position: "before", symbol: "$" },
    ];

    expect(Object.keys(currencies)).toEqual(["1", "5"]);
});

test("sanity check: currencies of a previous test are gone", () => {
    expect(Object.keys(currencies)).toEqual(["1", "2"]);
});

describe("a nested suite ending before the file's last tests", () => {
    test("reflects state changes on user and session", () => {
        serverState.userId = 43;

        expect(user.userId).toBe(43);
        expect(session.uid).toBe(43);
    });
});

test("state changes are still reflected on user, session and currencies after a nested suite", () => {
    serverState.userId = 42;
    serverState.companies = [
        { id: 3, name: "Hermit", currency_id: 1 },
        { id: 2, name: "Herman's", currency_id: 1 },
    ];
    serverState.currencies = [{ id: 5, name: "MXN", position: "before", symbol: "$" }];

    expect(user.userId).toBe(42);
    expect(session.uid).toBe(42);
    expect(user.allowedCompanies.map((company) => company.id)).toEqual([2, 3]);
    expect(Object.keys(currencies)).toEqual(["5"]);
});
