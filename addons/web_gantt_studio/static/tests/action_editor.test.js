import { describe, expect, test } from "@odoo/hoot";
import { animationFrame } from "@odoo/hoot-mock";
import { contains, mountWithCleanup, onRpc } from "@web/../tests/web_test_helpers";
import { WebClient } from "@web/webclient/webclient";
import { defineStudioEnvironment } from "@web_studio/../tests/studio_tests_context";

describe.current.tags("desktop");

defineStudioEnvironment();

test("add a gantt view", async () => {
    expect.assertions(5);

    onRpc("/web_studio/add_view_type", async (request) => {
        const { params } = await request.json();
        expect(params.view_type).toBe("gantt");
    });

    onRpc("fields_get", ({ model }) => {
        expect(model).toBe("partner");
    });

    await mountWithCleanup(WebClient);
    await animationFrame();

    await contains(".o_web_studio_navbar_item button").click();
    await contains(".o_app[data-menu-xmlid=app_1]").click();
    await contains(".o_menu_sections button:contains(Views)").click();
    await contains(".o_web_studio_thumbnail_item.o_web_studio_thumbnail_gantt").click();

    expect(".o_web_studio_new_view_dialog").toHaveCount(1);
    expect(".o_web_studio_new_view_dialog select[name='date_start']").toHaveValue(
        "create_date",
    );
    expect(".o_web_studio_new_view_dialog select[name='date_stop']").toHaveValue(
        "create_date",
    );
});
