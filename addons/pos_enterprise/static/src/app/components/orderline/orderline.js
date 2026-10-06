/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { parseNoteEntries } from "@point_of_sale/app/models/utils/note_entries";
import { usePrepDisplay } from "@pos_enterprise/app/services/preparation_display_service";
import { useDelayedValueChange } from "@pos_enterprise/app/utils/utils";
import { TagsList } from "@web/components/tags_list";
import { useService } from "@web/core/utils/hooks";

export class Orderline extends Component {
    static components = { TagsList };
    static template = "pos_enterprise.Orderline";
    static props = { orderline: t.object() };
    props = useProps(this.constructor.props);

    setup() {
        this.prepDisplay = usePrepDisplay();
        this.orm = useService("orm");
        this.noteState = useDelayedValueChange(
            () => this.preparation_line.internal_note,
        );
    }

    get preparation_line() {
        return this.props.orderline.prep_line_id;
    }

    get attributeData() {
        return Object.values(
            this.preparation_line.attribute_value_ids.reduce((acc, attr) => {
                const customValue = this.prepDisplay.data.models[
                    "product.attribute.custom.value"
                ].find(
                    (customValue) =>
                        customValue.pos_order_line_id ===
                            this.preparation_line.pos_order_line_id &&
                        customValue.custom_product_template_attribute_value_id.id ===
                            attr.id,
                );

                let value = attr.name;
                if (customValue) {
                    value += `: ${customValue.custom_value}`;
                }

                if (acc[attr.attribute_id.id]) {
                    acc[attr.attribute_id.id].value += `, ${value}`;
                } else {
                    acc[attr.attribute_id.id] = {
                        id: attr,
                        name: attr.attribute_id.name,
                        value,
                    };
                }

                return acc;
            }, {}),
        );
    }
    get internalNotes() {
        return parseNoteEntries(this.preparation_line.internal_note);
    }
    get customerNotes() {
        return (this.preparation_line.customer_note || "")
            .split("\n")
            .filter((note) => note);
    }
}
