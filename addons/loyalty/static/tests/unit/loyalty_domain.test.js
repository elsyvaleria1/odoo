import { expect, test } from "@odoo/hoot";
import { Domain } from "@web/core/domain";
import { evaluateExpr } from "@web/core/py_js/py";

test("the loyalty card search filters resolve a real date client-side", () => {
    const active = evaluateExpr(`[
        '&', ('active', '=', True),
        '&', ('program_id.active', '=', True),
        '|', ('expiration_date', '>=', context_today().strftime('%Y-%m-%d')),
             ('expiration_date', '=', False)
    ]`);
    const inactive = evaluateExpr(`[
        '|', ('active', '=', False),
        '|', ('program_id.active', '=', False),
             ('expiration_date', '<', context_today().strftime('%Y-%m-%d'))
    ]`);

    const today = active[5][2];
    expect(today).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(inactive[4][2]).toBe(today);
    expect(new Domain(active).toString()).toInclude(today);
    expect(new Domain(inactive).toString()).toInclude(today);
});

test("child_of matches every record client-side; the expanded id list does not", () => {
    expect(new Domain([["categ_id", "child_of", 1]]).contains({ categ_id: 999 })).toBe(
        true,
    );
    expect(new Domain([["categ_id", "parent_of", 1]]).contains({ categ_id: 999 })).toBe(
        true,
    );

    expect(new Domain([["categ_id", "in", [1, 2]]]).contains({ categ_id: 999 })).toBe(
        false,
    );
    expect(new Domain([["categ_id", "in", [1, 2]]]).contains({ categ_id: 2 })).toBe(
        true,
    );
});
