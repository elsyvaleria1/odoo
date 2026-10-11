/** @odoo-module native */
import { useSearchModel } from "@web/search/search_model";
import { PivotRenderer } from "@web/views/pivot";

export class AnalyticPivotRenderer extends PivotRenderer {
    setup() {
        super.setup();
        this.searchModel = useSearchModel();
    }

    onGroupBySelected({ itemId, optionId }) {
        if (typeof optionId === "number") {
            itemId = optionId;
        }
        let searchItems = this.searchModel.getSearchItems(
            (searchItem) =>
                ["groupBy", "dateGroupBy"].includes(searchItem.type) &&
                !searchItem.custom,
        );

        for (const [
            fieldName,
            customGroupBy,
        ] of this.model.metaData.customGroupBys.entries()) {
            searchItems.push({ ...customGroupBy, fieldName });
        }
        searchItems = [
            ...searchItems,
            ...searchItems
                .flatMap((f) => f.options)
                .filter((f) => typeof f?.id === "number"),
        ];
        const { fieldName } = searchItems.find(({ id }) => id === itemId);
        this.model.addGroupBy({
            ...this.dropdown.cellInfo,
            fieldName,
            interval: optionId,
        });
    }
}
