// @ts-check

import { expect, test } from "@odoo/hoot";
import { animationFrame } from "@odoo/hoot-mock";
import {
    contains,
    defineModels,
    fields,
    models,
    mountView,
    patchWithCleanup,
} from "@web/../tests/web_test_helpers";
import { makeLogger } from "@web/core/debug/debug_logger";
import { Field } from "@web/fields/field";

class Partner extends models.Model {
    name = fields.Char({ help: "the name" });
    other = fields.Char({ help: "readonly with flag" });
    txt = fields.Char({ help: "required with flag" });
    flag = fields.Boolean();
    _records = [
        { id: 1, name: "p1", other: "o1", txt: "t1", flag: false },
        { id: 2, name: "p2", other: "o2", txt: "t2", flag: true },
    ];
}

defineModels([Partner]);

const ARCH = `
    <form>
        <field name="name"/>
        <field name="other" readonly="flag"/>
        <field name="txt" required="flag"/>
        <field name="flag"/>
    </form>`;

function countDerivations() {
    /**
     * @type {{
     * computed: Record<string, number>,
     * feedback: Record<string, number>,
     * tooltip: Record<string, number>,
     * }}
     */
    let counts = { computed: {}, feedback: {}, tooltip: {} };
    /**
     * @param {Record<string, number>} bucket
     * @param {string} name
     */
    const bump = (bucket, name) => {
        bucket[name] = (bucket[name] || 0) + 1;
    };
    patchWithCleanup(makeLogger("web.field"), {
        /**
         * @param {string} label
         * @param {...any} data
         */
        logic(label, ...data) {
            if (label === "visualFeedback") {
                bump(counts.computed, data[0]().name);
            }
            return super.logic(label, ...data);
        },
    });
    patchWithCleanup(Field.prototype, {
        setup() {
            super.setup();
            const read = this.visualFeedback;
            const seen = new WeakSet();
            this.visualFeedback = () => {
                const value = read();
                if (!seen.has(value)) {
                    seen.add(value);
                    bump(counts.feedback, this.props.name);
                }
                return value;
            };
        },
        computeTooltip() {
            bump(counts.tooltip, this.props.name);
            return super.computeTooltip();
        },
    });
    return () => {
        const taken = counts;
        counts = { computed: {}, feedback: {}, tooltip: {} };
        return taken;
    };
}

test("the wrapper derives its feedback and tooltip once, however often a render reads them", async () => {
    const take = countDerivations();
    await mountView({ type: "form", resModel: "partner", resId: 1, arch: ARCH });
    await animationFrame();

    expect(".o_field_widget[name=other]").not.toHaveClass("o_readonly_modifier");
    expect(".o_field_widget[name=txt]").not.toHaveClass("o_required_modifier");
    expect(take()).toEqual({
        computed: { name: 1, other: 1, txt: 1, flag: 1 },
        feedback: { name: 1, other: 1, txt: 1, flag: 1 },
        tooltip: { name: 1, other: 1, txt: 1, flag: 1 },
    });
});

test("readonly and required follow the field their expression reads, deriving once", async () => {
    const take = countDerivations();
    await mountView({ type: "form", resModel: "partner", resId: 1, arch: ARCH });
    await animationFrame();
    take();

    await contains(".o_field_widget[name=flag] input").click();
    await animationFrame();

    expect(".o_field_widget[name=other]").toHaveClass("o_readonly_modifier");
    expect(".o_field_widget[name=txt]").toHaveClass("o_required_modifier");
    expect(take()).toEqual({
        computed: { other: 1, txt: 1 },
        feedback: { other: 1, txt: 1 },
        tooltip: {},
    });

    await contains(".o_field_widget[name=flag] input").click();
    await animationFrame();

    expect(".o_field_widget[name=other]").not.toHaveClass("o_readonly_modifier");
    expect(".o_field_widget[name=txt]").not.toHaveClass("o_required_modifier");
    expect(take()).toEqual({
        computed: { other: 1, txt: 1 },
        feedback: { other: 1, txt: 1 },
        tooltip: {},
    });
});

test("an edit evaluates only the edited field's feedback, and renders none that did not change", async () => {
    const take = countDerivations();
    await mountView({ type: "form", resModel: "partner", resId: 1, arch: ARCH });
    await animationFrame();
    take();

    for (const value of ["x", "xy", "xyz", "xyza", "xyzab"]) {
        await contains(".o_field_widget[name=name] input").edit(value);
        await animationFrame();
    }

    expect(".o_field_widget[name=name] input").toHaveValue("xyzab");
    expect(take()).toEqual({ computed: { name: 5 }, feedback: {}, tooltip: {} });
});

test("an emptied field is flagged empty once it is readonly", async () => {
    const take = countDerivations();
    await mountView({ type: "form", resModel: "partner", resId: 1, arch: ARCH });
    await animationFrame();
    await contains(".o_field_widget[name=other] input").clear();
    await animationFrame();
    expect(".o_field_widget[name=other]").not.toHaveClass("o_field_empty");
    take();

    await contains(".o_field_widget[name=flag] input").click();
    await animationFrame();

    expect(".o_field_widget[name=other]").toHaveClass("o_field_empty");
    expect(take().feedback.other).toBe(1);
});

test("another record evaluates each field's feedback once, and renders the ones that changed", async () => {
    const take = countDerivations();
    await mountView({
        type: "form",
        resModel: "partner",
        resId: 1,
        resIds: [1, 2],
        arch: ARCH,
    });
    await animationFrame();
    take();

    await contains(".o_pager_next").click();
    await animationFrame();

    expect(".o_field_widget[name=name] input").toHaveValue("p2");
    expect(".o_field_widget[name=other]").toHaveClass("o_readonly_modifier");
    expect(".o_field_widget[name=txt]").toHaveClass("o_required_modifier");
    expect(take()).toEqual({
        computed: { name: 1, other: 1, txt: 1, flag: 1 },
        feedback: { other: 1, txt: 1 },
        tooltip: {},
    });
});
