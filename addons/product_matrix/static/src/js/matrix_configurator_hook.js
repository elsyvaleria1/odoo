/** @odoo-module native */
import { useService } from "@web/core/utils/hooks";

import { ProductMatrixDialog } from "./product_matrix_dialog.js";

export function useMatrixConfigurator() {
    const dialog = useService("dialog");

    const openDialog = (
        rootRecord,
        jsonInfo,
        productTemplateId,
        editedCellAttributes,
    ) => {
        const infos = JSON.parse(jsonInfo);
        dialog.add(ProductMatrixDialog, {
            header: infos.header,
            rows: infos.matrix,
            editedCellAttributes: editedCellAttributes.toString(),
            product_template_id: productTemplateId,
            record: rootRecord,
        });
    };

    const open = async (record, edit) => {
        const rootRecord = record.model.root;

        await rootRecord.update({
            grid_product_tmpl_id: record.data.product_template_id,
        });

        const updatedLineAttributes = [];
        if (edit) {
            for (const ptnvav of record.data.product_no_variant_attribute_value_ids
                .records) {
                updatedLineAttributes.push(ptnvav.resId);
            }
            for (const ptav of record.data.product_template_attribute_value_ids
                .records) {
                updatedLineAttributes.push(ptav.resId);
            }
            updatedLineAttributes.sort((a, b) => a - b);
        }

        openDialog(
            rootRecord,
            rootRecord.data.grid,
            record.data.product_template_id.id,
            updatedLineAttributes,
        );

        if (!edit) {
            rootRecord.data.line_ids.delete(record);
        }
    };

    return { open };
}
