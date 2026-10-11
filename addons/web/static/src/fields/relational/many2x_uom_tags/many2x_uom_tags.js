// @ts-check
/** @odoo-module native */
import { onWillUpdateProps, t } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { roundPrecision } from "@web/core/utils/format/numbers";
import {
    Many2ManyTagsFieldColorEditable,
    many2ManyTagsFieldColorEditable,
} from "@web/fields/relational/many2many_tags";
import { Many2XAutocomplete } from "@web/fields/relational/many2x_autocomplete";

export function getProductRelatedModel() {
    const field = this.props.record.fields[this.props.productField];
    const resModel = field?.relation || this.props.record.resModel;
    if (!["product.product", "product.template"].includes(resModel)) {
        throw new Error(
            `The widget '${this.constructor.name}' (field '${this.props.name}') needs a 'product.product' or 'product.template' field. '${this.props.productField}' is used but is related to '${field?.relation}' model.`,
        );
    }
    return resModel;
}

export function getProductId() {
    const { record } = this.props;
    if (["product.product", "product.template"].includes(record.resModel)) {
        return record.resId || 0;
    }
    return record.data[this.props.productField]?.id || 0;
}

export function getProductQuantity() {
    return this.props.record.data[this.props.quantityField];
}

export class Many2XUomTagsAutocomplete extends Many2XAutocomplete {
    static props = {
        ...Many2XAutocomplete.props,
        productModel: t.string().optional(),
        productId: t.number().optional(),
        productQuantity: t.number().optional(),
    };

    setup() {
        super.setup();
        this.referenceUnitSeq = 0;
        this.updateReferenceUnit();
        onWillUpdateProps((nextProps) => {
            if (
                nextProps.productModel !== this.props.productModel ||
                nextProps.productId !== this.props.productId
            ) {
                this.updateReferenceUnit(nextProps);
            }
        });
    }

    updateReferenceUnit(props = this.props) {
        this.referenceUnitReady = this._loadReferenceUnit(
            props,
            ++this.referenceUnitSeq,
        );
        return this.referenceUnitReady;
    }

    async _loadReferenceUnit(props, seq) {
        let referenceUnit;
        if (props.productModel && props.productId) {
            try {
                const products = await this.orm.webRead(
                    props.productModel,
                    [props.productId],
                    {
                        specification: {
                            uom_id: {
                                fields: {
                                    name: {},
                                    factor: {},
                                    reference_uom_id: {},
                                    rounding: {},
                                },
                            },
                        },
                        context: { active_test: false },
                    },
                );
                referenceUnit = products[0]?.uom_id || undefined;
            } catch {
                referenceUnit = undefined;
            }
        }
        if (seq === this.referenceUnitSeq) {
            this.referenceUnit = referenceUnit;
        }
    }

    async search(name) {
        await this.referenceUnitReady;
        const fields = ["id", "display_name", "factor", "reference_uom_id"];
        const domain = [...this.props.getDomain(), ["name", "ilike", name]];
        const limit = this.props.searchLimit + 1;
        const reference = this.referenceUnit;
        const referenceRoot = reference?.reference_uom_id?.id;
        let records;
        if (referenceRoot) {
            const sameDimension = ["reference_uom_id", "=", referenceRoot];
            const [common, others] = await Promise.all([
                this.orm.searchRead(
                    this.props.resModel,
                    [...domain, sameDimension],
                    fields,
                    { limit },
                ),
                this.orm.searchRead(
                    this.props.resModel,
                    [...domain, "!", sameDimension],
                    fields,
                    { limit },
                ),
            ]);
            records = [...common, ...others].slice(0, limit);
        } else {
            records = await this.orm.searchRead(this.props.resModel, domain, fields, {
                limit,
            });
        }
        const quantity = this.props.productQuantity || 1;
        return records.map((record) => {
            let relativeInfo = "";
            if (
                reference &&
                record.id !== reference.id &&
                record.reference_uom_id?.[0] === referenceRoot
            ) {
                const converted = (quantity * record.factor) / reference.factor;
                relativeInfo = `${roundPrecision(converted, reference.rounding)} ${reference.name}`;
            }
            return { ...record, relative_info: relativeInfo };
        });
    }
}

export class Many2ManyUomTagsField extends Many2ManyTagsFieldColorEditable {
    static template = "web.Many2ManyUomTagsField";
    static components = {
        ...Many2ManyTagsFieldColorEditable.components,
        Many2XAutocomplete: Many2XUomTagsAutocomplete,
    };
    static props = {
        ...Many2ManyTagsFieldColorEditable.props,
        productField: t.string().optional("product_id"),
        quantityField: t.string().optional("product_uom_qty"),
    };

    setup() {
        super.setup();
        this.productModel = getProductRelatedModel.call(this);
    }

    get productId() {
        return getProductId.call(this);
    }

    get productQuantity() {
        return getProductQuantity.call(this);
    }
}

export const many2ManyUomTagsField = {
    ...many2ManyTagsFieldColorEditable,
    component: Many2ManyUomTagsField,
    additionalClasses: ["o_field_many2many_tags"],
    supportedOptions: [
        ...(many2ManyTagsFieldColorEditable.supportedOptions || []),
        {
            label: _t("Product Field Name"),
            name: "product_field",
            type: "field",
            availableTypes: ["many2one"],
        },
        {
            label: _t("Quantity Field Name"),
            name: "quantity_field",
            type: "field",
            availableTypes: ["float", "integer"],
        },
    ],
    extractProps(staticInfo, dynamicInfo) {
        return {
            ...many2ManyTagsFieldColorEditable.extractProps(staticInfo, dynamicInfo),
            productField: staticInfo.options.product_field,
            quantityField: staticInfo.options.quantity_field,
        };
    },
};

registry.category("fields").add("many2many_uom_tags", many2ManyUomTagsField);
