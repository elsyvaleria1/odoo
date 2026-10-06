/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { Dialog } from "@web/ui/dialog";

export class ProductImageDialog extends Component {
    static components = { Dialog };
    static props = { record: t.object(), close: t.function() };
    static template = "stock_barcode.ProductImageDialog";
    props = useProps(this.constructor.props);

    setup() {
        this.source = `/web/image/product.product/${this.props.record.id}/image_1024`;
        this.title = this.props.record.display_name;
    }
}
