import { getCurrentViewInfo } from "@ai/discuss/core/common/view_details";
import { defineMailModels } from "@mail/../tests/mail_test_helpers";
import { expect, test } from "@odoo/hoot";
import { waitFor } from "@odoo/hoot-dom";
import { animationFrame } from "@odoo/hoot-mock";
import {
    defineActions,
    defineMenus,
    defineModels,
    fields,
    getMockEnv,
    getService,
    models,
    mountWebClient,
} from "@web/../tests/web_test_helpers";
import { FormViewDialog } from "@web/views/view_dialogs/form_view_dialog";

class Partner extends models.Model {
    name = fields.Char();
    _records = [{ id: 1, name: "dummy record" }];
    _views = {
        list: `<list><field name="name"/></list>`,
        form: `<form><field name="name"/></form>`,
        search: `<search><filter name="named" string="Named" domain="[('name', '!=', False)]"/></search>`,
    };
}
defineModels([Partner]);
defineMailModels();
defineActions([
    {
        id: 667,
        xml_id: "partners",
        name: "Partners",
        res_model: "partner",
        views: [
            [false, "list"],
            [false, "form"],
        ],
    },
]);
defineMenus([{ id: 1, name: "App1", appID: 1, actionID: 667 }]);

test.tags("desktop");
test("the agent is told about the view the user is looking at", async () => {
    await mountWebClient();
    const env = getMockEnv();
    expect(getCurrentViewInfo(env)).toBe(null);
    await getService("menu").selectMenu(1);
    await waitFor(".o_list_view");
    await getService("active_view").current.searchModel.applySearchSpec({
        filters: ["named"],
    });
    await animationFrame();
    const info = getCurrentViewInfo(env);
    expect(info).toMatchObject({
        action_id: 667,
        model: "partner",
        view_type: "list",
        available_view_types: ["list"],
    });
    expect(info.facets.map((facet) => facet.values)).toEqual([["Named"]]);
});

test.tags("desktop");
test("a form in a dialog has nothing for the agent to adjust", async () => {
    await mountWebClient();
    const env = getMockEnv();
    await getService("menu").selectMenu(1);
    await waitFor(".o_list_view");
    getService("dialog").add(FormViewDialog, { resModel: "partner", resId: 1 });
    await waitFor(".modal .o_form_view");
    expect(getCurrentViewInfo(env)).toBe(null);
});
