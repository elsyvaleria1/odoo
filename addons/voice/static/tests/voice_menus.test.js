// @ts-check

import { describe, expect, test } from "@odoo/hoot";
import { interpret } from "@voice/interpreter/interpreter";
import {
    defineMenus,
    getService,
    mountWebClient,
} from "@web/../tests/web_test_helpers";

describe.current.tags("desktop");

defineMenus([
    {
        id: 1,
        name: "Contabilidad",
        appID: 1,
        actionID: 11,
        children: [
            {
                id: 10,
                name: "Clientes",
                appID: 1,
                children: [{ id: 11, name: "Facturas", appID: 1, actionID: 11 }],
            },
            {
                id: 20,
                name: "Proveedores",
                appID: 1,
                children: [{ id: 21, name: "Facturas", appID: 1, actionID: 21 }],
            },
            { id: 30, name: "Pagos", appID: 1, actionID: 30 },
        ],
    },
]);

test("two menus of one name ask which, each named by its section", async () => {
    await mountWebClient();
    const vocabulary = getService("voice").vocabulary();
    const { proposals, candidates } = interpret("abre facturas", vocabulary);
    expect(proposals).toEqual([]);
    expect(candidates.map((c) => c.description)).toEqual([
        "Open Facturas (Contabilidad / Clientes)",
        "Open Facturas (Contabilidad / Proveedores)",
    ]);
    expect(
        interpret("abre facturas de proveedores", vocabulary).proposals.map(
            (p) => p.description,
        ),
    ).toEqual(["Open Facturas (Contabilidad / Proveedores)"]);
    expect(
        interpret("abre pagos", vocabulary).proposals.map((p) => p.description),
    ).toEqual(["Open Pagos (Contabilidad)"]);
});
