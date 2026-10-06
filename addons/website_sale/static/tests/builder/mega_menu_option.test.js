import { expect, test } from "@odoo/hoot";
import { contains, onRpc } from "@web/../tests/web_test_helpers";
import {
    defineWebsiteModels,
    setupWebsiteBuilder,
} from "@website/../tests/builder/website_helpers";

defineWebsiteModels();

const megaMenu = (id) => `
    <div data-name="Mega Menu" class="o_mega_menu" data-oe-model="website.menu" data-oe-id="${id}" data-oe-field="mega_menu_content" data-oe-type="html" data-oe-expression="submenu.mega_menu_content">
        <section class="s_mega_menu_odoo_menu pt16 o_cc o_cc1">
            <div class="container">mega menu ${id} content</div>
        </section>
    </div>`;

test("the eCommerce categories are fetched once per builder session", async () => {
    onRpc("product.public.category", "*", ({ method }) => {
        expect.step("product.public.category RPC");
        return method === "search" ? [1] : [{ id: 1 }];
    });
    await setupWebsiteBuilder("", { headerContent: megaMenu(1) + megaMenu(2) });

    await contains(":iframe [data-oe-id='1']").click();
    expect("[data-label='eCommerce Categories']").toHaveCount(1);
    expect.verifySteps(["product.public.category RPC"]);

    await contains(":iframe [data-oe-id='2']").click();
    expect("[data-label='eCommerce Categories']").toHaveCount(1);
    await contains(":iframe [data-oe-id='1']").click();
    expect("[data-label='eCommerce Categories']").toHaveCount(1);
    expect.verifySteps([]);
});
