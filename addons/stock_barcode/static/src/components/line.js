/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { ProductImageDialog } from "@stock_barcode/components/product_image_dialog";
import { useBarcodeModel } from "@stock_barcode/models/barcode_model_hooks";
import { useService } from "@web/core/utils/hooks";

export const lineComponentProps = {
    displayUOM: t.any(),
    line: t.any(),
    subline: t.any().optional(),
    editLine: t.any(),
};

export default class LineComponent extends Component {
    static props = lineComponentProps;
    static template = "stock_barcode.LineComponent";
    props = useProps(this.constructor.props);

    setup() {
        this.model = useBarcodeModel();
        this.dialog = useService("dialog");
    }

    // A getter: the component outlives a product change on its line (same virtual id).
    get imageSource() {
        const product = this.props.line.product_id;
        return product.has_image
            ? `/web/image/product.product/${product.id}/image_128`
            : null;
    }

    get destinationLocationPath() {
        return this._getLocationPath(
            this.model._defaultDestLocation(),
            this.line.location_dest_id,
        );
    }

    get displayDeleteButton() {
        return this.model.lineCanBeDeleted(this.line);
    }

    get displayDestinationLocation() {
        return !this.props.subline && this.model.displayDestinationLocation;
    }

    get displayFulfillbutton() {
        return (
            this.incrementQty &&
            this.model.getDisplayIncrementBtn(this.line) &&
            !this.isPackage
        );
    }

    get displayCompletePackageButton() {
        return this.isSelected && this.model.getDisplayCompletePackageBtn(this.line);
    }

    get displayIncrementButton() {
        if (this.isSelected && !this.isPackage && this.incrementQty !== 1) {
            return this.isTracked && this.line.product_id.tracking === "serial"
                ? this.model.getDisplayIncrementBtnForSerial(this.line)
                : this.model.getDisplayIncrementBtn(this.line);
        }
        return false;
    }

    get incrementQty() {
        return this.model.getIncrementQuantity(this.line);
    }

    get displayResultPackage() {
        return this.model.displayResultPackage;
    }

    get isComplete() {
        if (!this.qtyDemand || this.qtyDemand !== this.qtyDone) {
            return false;
        } else if (this.isTracked && !this.lotName) {
            return false;
        }
        return true;
    }

    get isPackage() {
        return this.line.isPackageLine;
    }

    get isSelected() {
        return (
            this.model.lineIsSelected(this.line) ||
            (this.line.package_id &&
                this.line.package_id.id === this.model.lastScanned.packageId)
        );
    }

    get isTracked() {
        return this.model.lineIsTracked(this.line);
    }

    get lotName() {
        if (this.model.showReservedSns || this.model.getQtyDone(this.line)) {
            return (
                (this.line.trace_id && this.line.trace_id.name) ||
                this.line.lot_name ||
                ""
            );
        }
        return "";
    }

    get nextExpected() {
        if (this.isSelected) {
            if (this.isTracked && !this.lotName) {
                return "lot";
            } else if (this.qtyDemand && this.qtyDone < this.qtyDemand) {
                return "quantity";
            }
        }
        return false;
    }

    get qtyDemand() {
        return this.model.getQtyDemand(this.line);
    }

    get qtyDone() {
        return this.model.getQtyDone(this.line);
    }

    get quantityIsSet() {
        return this.line.inventory_quantity_set;
    }

    get packageLabel() {
        return this.line.package_id.complete_name;
    }

    get resultPackageLabel() {
        return this.line.result_package_id.dest_complete_name;
    }

    get line() {
        return this.props.line;
    }

    get componentClasses() {
        return [
            this.isComplete ? "o_line_completed" : "o_line_not_completed",
            this.model.lineIsFaulty(this.line) ? "o_faulty" : "",
            this.isSelected ? "o_selected o_highlight" : "",
        ].join(" ");
    }

    get showDescription() {
        // In Barcode we don't get the product's `display_name` with the code, however the description uses it.
        const possibleNames = [
            this.line.product_id.display_name,
            `[${this.line.product_id.default_code}] ${this.line.product_id.display_name}`,
            `[${this.line.product_id.code}] ${this.line.product_id.display_name}`,
        ];
        return (
            this.line.description_picking &&
            !possibleNames.includes(this.line.description_picking)
        );
    }

    _getLocationPath(rootLocation, currentLocation) {
        let locationName = currentLocation.display_name;
        if (
            this.model.shouldShortenLocationName &&
            this.model._isSublocation &&
            this.model._isSublocation(currentLocation, rootLocation) &&
            rootLocation &&
            rootLocation.id !== currentLocation.id
        ) {
            locationName = locationName.replace(rootLocation.display_name, "...");
        }
        // Location names are free text: building a RegExp out of one silently changes the match
        // for `Zone (A)` and throws a SyntaxError for `Zone (`. This only ever strips a suffix.
        return locationName.endsWith(currentLocation.name)
            ? locationName.slice(0, -currentLocation.name.length)
            : locationName;
    }

    addQuantity(quantity) {
        let lineVirtualId = this.line.virtual_id;
        if (this.line.lines?.length > 1 && this.lotName) {
            lineVirtualId = this.line.lines.find((subline) => {
                const sublineLotName = subline.trace_id
                    ? subline.trace_id.name
                    : subline.lot_name;
                return sublineLotName === this.lotName;
            }).virtual_id;
        }
        this.model.updateLineQty(lineVirtualId, quantity);
    }

    completePackage() {
        this.model.completePackage(this.line.virtual_id);
    }

    async delete(ev) {
        // The button sits inside the line: letting the click reach the line's `select`
        // selected the line being deleted.
        ev.stopPropagation();
        await this.model.removeLine(this.line);
        this.model.trigger("update");
    }

    select(ev) {
        ev.stopPropagation();
        this.model.selectLine(this.line);
        this.model.trigger("update");
    }

    toggleAsCounted() {
        this.model.toggleAsCounted(this.line);
    }

    onClickImage() {
        this.dialog.add(ProductImageDialog, { record: this.line.product_id });
    }
}
