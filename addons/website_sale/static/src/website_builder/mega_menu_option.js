/** @odoo-module native */
import { useCachedModel } from "@html_builder/core/cached_model_utils";
import { onWillStart } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";
import { MegaMenuOption } from "@website/builder/plugins/options/mega_menu_option";

patch(MegaMenuOption.prototype, {
    setup() {
        this.website = useService("website");
        this.cachedModel = useCachedModel();
        super.setup();
        this.productCategories = [];

        onWillStart(async () => {
            this.productCategories = await this.cachedModel.ormSearchRead(
                "product.public.category",
                [
                    "|",
                    ["website_id", "=", false],
                    ["website_id", "=", this.website.currentWebsiteId],
                ],
                ["id"],
            );
        });
    },
});
