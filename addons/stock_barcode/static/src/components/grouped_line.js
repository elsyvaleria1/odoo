/** @odoo-module native */
import LineComponent from "@stock_barcode/components/line";

export default class GroupedLineComponent extends LineComponent {
    static components = { LineComponent };
    static template = "stock_barcode.GroupedLineComponent";

    get isComplete() {
        if (
            this.linesToDisplay.length > 1 &&
            this.isTracked &&
            this.qtyDemand &&
            this.qtyDone === this.qtyDemand
        ) {
            // In case the line is tracked and has multiple sublines, we consider the line complete
            // if it has enough quantity and all sublines with quantity has a lot.
            for (const subline of this.linesToDisplay) {
                const lotName = subline.trace_id?.name || subline.lot_name;
                if (this.model.getQtyDone(subline) && !lotName) {
                    return false;
                }
            }
            return true;
        }
        return super.isComplete;
    }

    get isSelected() {
        return this.line.virtual_ids.indexOf(this.model.selectedLineVirtualId) !== -1;
    }

    get opened() {
        return this.model.groupKey(this.line) === this.model.unfoldLineKey;
    }

    sublineProps(subline) {
        return {
            displayUOM: this.props.displayUOM,
            editLine: this.props.editLine,
            line: subline,
            subline: true,
        };
    }

    get linesToDisplay() {
        if (!this.model.showReservedSns) {
            return this.props.line.lines.filter(
                (line) =>
                    this.model.getQtyDone(line) > 0 ||
                    line.product_id.tracking === "none" ||
                    this.model.getQtyDemand(line) === 0,
            );
        }
        return this.props.line.lines;
    }

    get lotName() {
        if (!this.model.showReservedSns) {
            // In case we don't display unscanned reserved lots, display it only
            // if only one subline with a lot has some quantity done.
            if (this.linesToDisplay.length === 1) {
                for (const line of this.linesToDisplay) {
                    const lotName = line.trace_id?.name || line.lot_name;
                    if (lotName && this.model.getQtyDone(this.line)) {
                        return lotName;
                    }
                }
            } else {
                return "";
            }
        }
        return super.lotName;
    }

    get displayToggleBtn() {
        return this.linesToDisplay.length > 1;
    }

    toggleSublines(ev) {
        ev.stopPropagation();
        this.model.toggleSublines(this.line);
    }
}
