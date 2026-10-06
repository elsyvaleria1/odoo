/** @odoo-module native */
import { provideFsmContext, useFsmContext } from "@industry_fsm_sale/fsm_context";
import { ProductCatalogKanbanRecord } from "@product/product_catalog/kanban_record";
import { useProductCatalogContext } from "@product/product_catalog/product_catalog_context";
import { rpc } from "@web/core/network";
import { useService } from "@web/core/utils/hooks";
import { useSearchModel } from "@web/search/search_model";

export class FSMProductCatalogKanbanRecord extends ProductCatalogKanbanRecord {
    setup() {
        super.setup();
        this.searchModel = useSearchModel();
        this.orm = useService("orm");
        provideFsmContext({
            fsm_task_id: this.props.record.context.fsm_task_id,
            resetQuantity: this.debouncedUpdateQuantity.bind(this),
        });
        this.fsmContext = useFsmContext();
        this.catalogContext = useProductCatalogContext();
    }

    async _updateQuantity() {
        const { action, price, min_quantity } = await rpc(
            "/product/catalog/update_order_line_info",
            {
                order_id: this.catalogContext.orderId,
                product_id: this.catalogContext.productId,
                quantity: this.productCatalogData.quantity,
                res_model: this.catalogContext.orderResModel,
                task_id: this.fsmContext.fsm_task_id,
                child_field: this.catalogContext.childField,
                section_id: this.sectionIdOfPendingUpdate,
            },
        );
        if (price) {
            this.productCatalogData.price = parseFloat(price);
        }
        if (min_quantity) {
            this.productCatalogData.minimumQuantityOnProduct = min_quantity;
        }
        if (action && action !== true) {
            const actionContext = {
                default_product_id: this.props.record.data.id,
            };
            const options = {
                additionalContext: actionContext,
                onClose: async () => {
                    const domain = [
                        ["task_id", "=", this.fsmContext.fsm_task_id],
                        ["product_id", "=", this.catalogContext.productId],
                        ["product_uom_qty", ">", 0],
                    ];
                    let lines = await this.orm.searchRead("sale.order.line", domain, [
                        "product_uom_qty",
                        "parent_id",
                    ]);
                    if (this.catalogContext.orderId) {
                        lines = lines.filter((line) =>
                            this.searchModel.selectedSection.sectionId
                                ? line.parent_id?.[0] ===
                                  this.searchModel.selectedSection.sectionId
                                : line.parent_id === false,
                        );
                    }
                    const quantity = lines.reduce(
                        (total, line) => total + line.product_uom_qty,
                        0,
                    );
                    this.notifyLineCountChange(
                        quantity - this.productCatalogData.quantity,
                    );
                    this.productCatalogData.quantity = quantity;
                    this.productCatalogData.tracking = true;
                },
            };
            await this.action.doAction(action, options);
        }
    }
}
