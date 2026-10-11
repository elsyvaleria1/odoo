/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { usePos } from "@point_of_sale/app/hooks/pos_hook";
import { logPosMessage } from "@point_of_sale/app/utils/pretty_console_log";
import { makeLogger } from "@web/core/debug/debug_logger";
import { useLifecycleLog } from "@web/core/debug/logger_hooks";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";
import { AlertDialog, Dialog } from "@web/ui/dialog";
const log = makeLogger("pos.popup.product_info");
export class ProductInfoPopup extends Component {
    static template = "point_of_sale.ProductInfoPopup";
    static components = { Dialog };
    static props = { info: t.any(), productTemplate: t.any(), close: t.any() };
    props = useProps(this.constructor.props);

    setup() {
        this.utils = useService("contextual_utils_service");
        useLifecycleLog(log);
        this.pos = usePos();
        log.lifecycle("opened", () => ({
            template: this.props.productTemplate?.id,
            marginsVisible: this._hasMarginsCostsAccessRights(),
        }));
    }
    searchProduct(productName) {
        this.pos.setSelectedCategory(0);
        this.pos.searchProductWord = productName;
        this.props.close();
    }
    _hasMarginsCostsAccessRights() {
        if (!this.pos.config.is_margins_costs_accessible_to_every_user) {
            return false;
        }
        return ["manager", "cashier"].includes(this.pos.getCashier()._role);
    }
    editProduct() {
        this.pos.editProduct(this.props.productTemplate);
        this.props.close();
    }
    get allowProductEdition() {
        return true;
    }
    async toggleFeatured() {
        const template = this.props.productTemplate;
        const next = !template.is_featured;
        log.pipeline("toggleFeatured", () => ({ template: template.id, next }));
        try {
            const applied = await this.pos.data.call(
                "product.template",
                "set_pos_featured",
                [[template.id], next],
            );
            template.is_featured = applied;
        } catch (error) {
            this.pos.dialog.add(AlertDialog, {
                title: _t("Not saved"),
                body: _t("Whether this product is featured could not be saved."),
            });
            logPosMessage(
                "ProductInfoPopup",
                "toggleFeatured",
                `Could not set is_featured on product.template ${template.id}`,
                undefined,
                [error],
            );
        }
    }
    get vatLabel() {
        return _t("VAT:");
    }
    get totalVatLabel() {
        return _t("Total VAT:");
    }
}
