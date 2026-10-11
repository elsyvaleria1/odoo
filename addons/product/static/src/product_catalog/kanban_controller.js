/** @odoo-module native */
import { onWillStart } from "@odoo/owl";
import { provideProductCatalogContext } from "@product/product_catalog/product_catalog_context";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";
import { useDebounced } from "@web/core/utils/timing";
import { useViewConfig } from "@web/core/view_config_hooks";
import { KanbanController } from "@web/views/kanban";

export const productCatalogKanbanControllerProps = { ...KanbanController.props };

export class ProductCatalogKanbanController extends KanbanController {
    static props = productCatalogKanbanControllerProps;
    static template = "ProductCatalogKanbanController";

    setup() {
        super.setup();
        this.config = useViewConfig();
        this.orm = useService("orm");
        this.orderId = this.props.context.order_id;
        this.orderResModel = this.props.context.product_catalog_order_model;
        this.backToQuotationDebounced = useDebounced(
            this.backToQuotation.bind(this),
            500,
            {
                immediate: true,
                trailing: false,
            },
        );
        this.pendingLineUpdates = new Set();
        provideProductCatalogContext({
            productCatalogPendingUpdates: this.pendingLineUpdates,
        });

        onWillStart(() => this.onWillStart());
    }

    async onWillStart() {
        await this.setOrderStateInfo();
        this._defineButtonContent();
    }

    get canCreate() {
        return true;
    }

    get stateFields() {
        return ["state"];
    }

    async setOrderStateInfo() {
        const orderData = await this.orm.searchRead(
            this.orderResModel,
            [["id", "=", this.orderId]],
            this.stateFields,
        );
        this.orderStateInfo = orderData[0] || {};
    }

    _defineButtonContent() {
        const orderIsQuotation = ["draft", "sent"].includes(this.orderStateInfo.state);
        if (orderIsQuotation) {
            this.buttonString = _t("Back to Quotation");
        } else {
            this.buttonString = _t("Back to Order");
        }
    }

    /**
     * Settle every card's debounced quantity write before the action goes away.
     *
     * Hooked here rather than on the "Back to Order" button because the button
     * is not the only way out: a breadcrumb, a menu, or any other action all
     * leave through `confirmLeave`, which awaits this. The order form is
     * reloaded by whatever comes next, so the write has to have landed first.
     *
     * `allSettled`: a card whose write failed has already reported it, and one
     * failure must not strand the user in the catalog. Returning anything but
     * `false` lets the departure proceed.
     *
     * @returns {Promise<void>}
     */
    async beforeLeave() {
        await Promise.allSettled(
            [...this.pendingLineUpdates].map((record) => record.flushPendingUpdate()),
        );
        return super.beforeLeave();
    }

    async backToQuotation() {
        if (this.config.breadcrumbs.length > 1) {
            await this.actionService.restore();
        } else {
            await this.actionService.doAction({
                type: "ir.actions.act_window",
                res_model: this.orderResModel,
                views: [[false, "form"]],
                view_mode: "form",
                res_id: this.orderId,
            });
        }
    }
}
