/** @odoo-module native */
import { rpc } from "@web/core/network";
import { _t } from "@web/core/translation";
import { RelationalModel, RelationalRecord } from "@web/model/relational_model";

class ProductCatalogRecord extends RelationalRecord {
    setup(config, data, options = {}) {
        this.productCatalogData = data.productCatalogData;
        data = { ...data };
        delete data.productCatalogData;
        super.setup(config, data, options);
    }
}

export class ProductCatalogKanbanModel extends RelationalModel {
    static Record = ProductCatalogRecord;
    static withCache = false;

    async _loadData(params, ...rest) {
        const isSample = Boolean(this.orm.isSample);
        const selectedSection = this.viewContext.searchModel.selectedSection;
        if (selectedSection.filtered) {
            params = {
                ...params,
                domain: [
                    ...(params.domain || []),
                    ["is_in_selected_section_of_order", "=", true],
                ],
                context: {
                    ...params.context,
                    section_id: selectedSection.sectionId,
                },
            };
        }
        const result = await super._loadData(params, ...rest);
        if (params.isMonoRecord) {
            return result;
        }

        const records = params.groupBy?.length
            ? this._collectGroupedRecords(result.groups)
            : result.records;
        if (!records.length) {
            return result;
        }

        const productIds = records.map((record) => record.id);
        const orderLinesInfo = isSample
            ? this._getSampleOrderLineInfo(productIds)
            : await rpc(
                  "/product/catalog/order_lines_info",
                  this._getOrderLinesInfoParams(params, productIds),
              );
        for (const record of records) {
            record.productCatalogData = orderLinesInfo[record.id];
        }
        return result;
    }

    /**
     * @param {Object[]} [groups]
     * @returns {Object[]}
     */
    _collectGroupedRecords(groups = []) {
        const records = [];
        const stack = [...groups];
        while (stack.length) {
            const group = stack.pop();
            if (group.groups?.length) {
                stack.push(...group.groups);
            }
            if (group.records?.length) {
                records.push(...group.records);
            }
        }
        return records;
    }

    _getOrderLinesInfoParams(params, productIds) {
        return {
            order_id: params.context.order_id,
            product_ids: productIds,
            res_model: params.context.product_catalog_order_model,
            child_field: params.context.child_field,
            section_id: this.viewContext.searchModel.selectedSection.sectionId,
        };
    }

    /**
     * @param {number[]} productIds
     * @returns {Object}
     */
    _getSampleOrderLineInfo(productIds) {
        const sampleOrderLineInfo = {};
        for (const productId of productIds) {
            sampleOrderLineInfo[productId] = {
                isSample: true,
                quantity: (productId * 3) % 10,
                price: 100 + ((productId * 37) % 400),
                productType: "consu",
                readOnly: false,
                uomDisplayName: _t("Units"),
            };
        }
        return sampleOrderLineInfo;
    }
}
