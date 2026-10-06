/** @odoo-module native */
import { BackButton } from "@point_of_sale/app/screens/product_screen/action_pad/back_button/back_button";
import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";
import { _t } from "@web/core/translation";
import { patch } from "@web/core/utils/patch";

patch(ProductScreen, {
    components: {
        ...ProductScreen.components,
        BackButton,
    },
    back: _t("Back"),
});
