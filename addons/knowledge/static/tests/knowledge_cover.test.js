import { defineMailModels } from "@mail/../tests/mail_test_helpers";
import { describe, expect, test } from "@odoo/hoot";
import { click, manuallyDispatchProgrammaticEvent, queryOne } from "@odoo/hoot-dom";
import { animationFrame, mockTouch } from "@odoo/hoot-mock";
import {
    defineModels,
    fields,
    models,
    mountView,
    onRpc,
} from "@web/../tests/web_test_helpers";

describe.current.tags("desktop");

class Article extends models.Model {
    cover_image_url = fields.Char();
    cover_image_position = fields.Float();
    is_locked = fields.Boolean();
    user_can_write = fields.Boolean();
    active = fields.Boolean({ default: true });

    _records = [
        {
            id: 1,
            cover_image_url: "/web/static/img/placeholder.png",
            cover_image_position: 50,
            is_locked: false,
            user_can_write: true,
            active: true,
        },
    ];
}

defineMailModels();
defineModels([Article]);

onRpc("has_group", () => true);

async function mountCover() {
    await mountView({
        type: "form",
        resModel: "article",
        resId: 1,
        arch: `
            <form>
                <field name="cover_image_url" invisible="1"/>
                <field name="cover_image_position" invisible="1"/>
                <field name="is_locked" invisible="1"/>
                <field name="user_can_write" invisible="1"/>
                <field name="active" invisible="1"/>
                <widget name="knowledge_cover"/>
            </form>
        `,
    });
}

/** @param {number} clientY */
async function moveFingerTo(clientY) {
    await manuallyDispatchProgrammaticEvent(document, "pointermove", {
        clientY,
        pointerType: "touch",
    });
    await animationFrame();
}

test("a cover is repositioned with a finger", async () => {
    mockTouch(true);
    await mountCover();
    expect(".o_knowledge_reposition_cover").toHaveCount(1);

    await click(".o_knowledge_reposition_cover");
    await animationFrame();
    await manuallyDispatchProgrammaticEvent(
        queryOne(".o_knowledge_cover img"),
        "pointerdown",
        { clientY: 100, pointerType: "touch" },
    );
    await animationFrame();
    expect(".o_knowledge_cover").toHaveClass("o_cursor_grabbing");

    await moveFingerTo(50);
    expect(queryOne(".o_knowledge_cover img").style.objectPosition).toBe("50% 60%");
});

test("a cancelled touch ends the grab", async () => {
    mockTouch(true);
    await mountCover();
    await click(".o_knowledge_reposition_cover");
    await animationFrame();
    await manuallyDispatchProgrammaticEvent(
        queryOne(".o_knowledge_cover img"),
        "pointerdown",
        { clientY: 100, pointerType: "touch" },
    );
    await moveFingerTo(50);

    await manuallyDispatchProgrammaticEvent(document, "pointercancel", {
        pointerType: "touch",
    });
    await animationFrame();
    expect(".o_knowledge_cover").not.toHaveClass("o_cursor_grabbing");

    await moveFingerTo(0);
    expect(queryOne(".o_knowledge_cover img").style.objectPosition).toBe("50% 60%");
});
