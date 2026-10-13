/** @odoo-module native */
import { ApplyQuantDialog } from "@stock_barcode/components/apply_quant_dialog";
import { ConfirmQuantDialog } from "@stock_barcode/components/confirm_quant_dialog";
import BarcodeModel from "@stock_barcode/models/barcode_model";
import { now, serializeDate } from "@web/core/l10n/dates";
import { _t } from "@web/core/translation";
import { floatIsZero } from "@web/core/utils/format/numbers";

export default class BarcodeQuantModel extends BarcodeModel {
    constructor(params) {
        super(...arguments);
        this.lineModel = this.resModel;
        this.validateMessage = _t("The inventory count has been updated");
        this.validateMethod = "action_validate";
        this.deleteLineMethod = "action_barcode_remove_count";
    }

    async _validate() {
        return this.apply({ shouldConfirm: true });
    }

    async waitReview() {
        return this.apply({ shouldWaitReview: true });
    }

    /** @returns {Promise} */
    apply(options = {}) {
        if (this.checkBeforeApply()) {
            const { shouldConfirm = false, shouldWaitReview = false } = options;
            const confirm = (context) => this._apply(context);
            const waitReview = async () => {
                await this.save();
                this.trigger("history-back");
                this.trigger("update");
            };
            if (shouldConfirm) {
                return confirm();
            } else if (shouldWaitReview) {
                return waitReview();
            } else {
                this.dialogService.add(ConfirmQuantDialog, {
                    onConfirm: confirm,
                    onWaitReview: waitReview,
                });
            }
        }
    }

    /** @returns {Boolean} */
    checkBeforeApply() {
        if (this.applyOn === 0) {
            const message = _t("There is nothing to apply in this page.");
            this.notification(message, { type: "warning" });
            return false;
        }
        const countedSerialNumbers = this.groupedLines.filter(
            (gl) =>
                gl.lines &&
                gl.inventory_quantity_set &&
                gl.product_id.tracking === "serial",
        );
        const notCountedSiblingSerialNumbers = [];
        for (const groupedLine of countedSerialNumbers) {
            for (const line of groupedLine.lines) {
                if (!line.inventory_quantity_set) {
                    notCountedSiblingSerialNumbers.push(line);
                }
            }
        }
        if (notCountedSiblingSerialNumbers.length) {
            this.dialogService.add(ApplyQuantDialog, {
                onApply: this._apply.bind(this),
                onApplyAll: () => {
                    for (const line of notCountedSiblingSerialNumbers) {
                        this.toggleAsCounted(line);
                    }
                    this._apply();
                },
            });
            return false;
        }
        return true;
    }

    /** @returns {Promise} */
    async _apply(context = {}) {
        await this.save();
        const quantIds = this.pageLines.map((quant) => quant.id);
        const action = await this.orm.call(
            "stock.quant",
            "action_validate",
            [quantIds],
            { context },
        );
        const notifyAndGoAhead = (res) => {
            if (res && res.special) {
                return this.trigger("refresh");
            }
            this.notification(this.validateMessage, { type: "success" });
            this.trigger("history-back");
        };
        if (action && action.res_model) {
            return this.action.doAction(action, { onClose: notifyAndGoAhead });
        }
        notifyAndGoAhead();
    }

    get applyOn() {
        return this.pageLines.filter((line) => line.inventory_quantity_set).length;
    }

    get barcodeInfo() {
        let line = this._getParentLine(this.selectedLine) || this.selectedLine;
        if (!line && this.lastScanned.packageId) {
            line = this.pageLines.find(
                (l) => l.package_id && l.package_id.id === this.lastScanned.packageId,
            );
        }
        const messages = {
            scanProduct: {
                class: "scan_product",
                message: _t("Scan a product"),
                icon: "tags",
            },
            scanLot: {
                class: "scan_lot",
                message: _t(
                    "Scan lot numbers for product %s to change their quantity",
                    line ? line.product_id.display_name : "",
                ),
                icon: "barcode",
            },
            scanSerial: {
                class: "scan_serial",
                message: _t(
                    "Scan serial numbers for product %s to change their quantity",
                    line ? line.product_id.display_name : "",
                ),
                icon: "barcode",
            },
        };

        if (line) {
            const { tracking } = line.product_id;
            const trackingNumber = this.getLotName(line);
            if (this._lineIsNotComplete(line)) {
                if (tracking !== "none") {
                    return tracking === "lot" ? messages.scanLot : messages.scanSerial;
                }
                return messages.scanProduct;
            } else if (tracking !== "none" && !trackingNumber) {
                return tracking === "lot" ? messages.scanLot : messages.scanSerial;
            } else {
                if (
                    this.groups.group_stock_multi_locations &&
                    line.location_id.id === this.location.id
                ) {
                    return {
                        class: "scan_product_or_src",
                        message: _t(
                            "Scan more products in %s or scan another location",
                            this.location.display_name,
                        ),
                    };
                }
                return messages.scanProduct;
            }
        }
        if (this.groups.group_stock_multi_locations) {
            if (!this.lastScanned.sourceLocation) {
                return {
                    class: "scan_src",
                    message: _t("Scan a location"),
                    icon: "right-from-bracket",
                };
            }
            return {
                class: "scan_product_or_src",
                message: _t(
                    "Scan a product in %s or scan another location",
                    this.location.display_name,
                ),
            };
        }
        return messages.scanProduct;
    }

    displaySetButton(line) {
        const isSelected = this.selectedLineVirtualId === line.virtual_id;
        return (
            isSelected &&
            (this.showQuantityCount ||
                (line.product_id.tracking === "serial" && this.getLotName(line)))
        );
    }

    setData(data) {
        this.userId = data.data.user_id;
        this.showQuantityCount = data.data.show_quantity_count;
        this.countEntireLocation = false;
        super.setData(...arguments);
        const companies = data.data.records["res.company"];
        this.companyIds = companies.map((company) => company.id);
        this.lineFormViewId = data.data.line_view_id;
    }

    get countsQuants() {
        return true;
    }

    get displayApplyButton() {
        return true;
    }

    getQtyDone(line) {
        return line.inventory_quantity_set ? line.inventory_quantity : 0;
    }

    getQtyDemand(line) {
        return this.showQuantityCount ? line.quantity : 0;
    }

    getActionRefresh(newId) {
        const action = super.getActionRefresh(newId);
        action.params.res_id = this.currentState.lines.map((l) => l.id);
        if (newId) {
            action.params.res_id.push(newId);
        }
        return action;
    }

    get highlightValidateButton() {
        return this.applyOn > 0 && this.applyOn === this.pageLines.length;
    }

    lineIsNotSet(line) {
        return !line.inventory_quantity_set;
    }

    lineCanBeDeleted(line) {
        return line.inventory_quantity_set && this.getQtyDone(line) === 0;
    }

    lineIsFaulty(line) {
        if (this.showQuantityCount) {
            return (
                line.inventory_quantity_set &&
                !floatIsZero(line.inventory_quantity - line.quantity, this.precision)
            );
        }
        return false;
    }

    lineIsTracked(line) {
        const lineIsTracked = super.lineIsTracked(...arguments);
        if (lineIsTracked && line.product_id.tracking === "serial") {
            return (
                this.getLotName(line) ||
                (this.getQtyDone(line) <= 1 && this.getQtyDemand(line) <= 1)
            );
        }
        return lineIsTracked;
    }

    get printButtons() {
        return [
            {
                name: _t("Print Inventory"),
                class: "o_print_inventory",
                action: "stock.action_report_inventory",
            },
        ];
    }

    get recordIds() {
        return this.currentState.lines.map((l) => l.id);
    }

    /** @param {Object} line */
    toggleAsCounted(line) {
        line.inventory_quantity = 0;
        line.inventory_quantity_set = !line.inventory_quantity_set;
        this._markLineAsDirty(line);
        this.trigger("update");
    }

    updateLineQty(virtualId, qty = 1) {
        return this.actionMutex.exec(async () => {
            const line = this.pageLines.find((l) => l.virtual_id === virtualId);
            await this.updateLine(line, { inventory_quantity: qty });
            this.trigger("update");
        });
    }

    _getCommands() {
        return Object.assign(super._getCommands(), {
            OBTAPPLY: this.apply.bind(this),
            OBTWREV: this.waitReview.bind(this),
        });
    }

    _getNewLineDefaultContext() {
        return {
            default_company_id: this.companyIds[0],
            default_location_id: this._defaultLocation().id,
            default_inventory_quantity: 1,
            default_user_id: this.userId,
            inventory_mode: true,
            display_default_code: false,
            hide_qty_to_count: !this.showQuantityCount,
        };
    }

    _createCommandVals(line) {
        const values = {
            dummy_id: line.virtual_id,
            inventory_date: line.inventory_date,
            inventory_quantity: line.inventory_quantity,
            inventory_quantity_set: line.inventory_quantity_set,
            location_id: line.location_id,
            trace_id: line.trace_id,
            lot_name: line.lot_name,
            package_id: line.package_id,
            product_id: line.product_id,
            owner_id: line.owner_id,
            user_id: this.userId,
        };
        for (const [key, value] of Object.entries(values)) {
            values[key] = this._fieldToValue(value);
        }
        return values;
    }

    async _createNewLine(params) {
        const product = params.fieldsParams.product_id;
        if (!product.is_storable) {
            const productName =
                (product.default_code ? `[${product.default_code}] ` : "") +
                product.display_name;
            const message = _t(
                "%s can't be inventoried. Only storable products can be inventoried.",
                productName,
            );
            this.notification(message, { type: "warning" });
            return false;
        }
        const location_id = this.location.id;
        const { trace_id, lot_name, owner_id, package_id } = params.fieldsParams;
        let quants = [];
        if (!params.fieldsParams.packaging || product.tracking === "none") {
            if (!trace_id && !lot_name && !package_id && !owner_id) {
                quants = await this.cache.getQuants(product, location_id);
            } else {
                const quantParams = { trace_id, lot_name, owner_id, package_id };
                quants = await this.cache.getQuants(product, location_id, quantParams);
            }
        }
        if (
            quants.length === 1 &&
            (product.tracking === "none" ||
                params.fieldsParams.lot_name ||
                params.fieldsParams.trace_id)
        ) {
            const inventory_quantity =
                product.tracking === "lot"
                    ? quants[0].quantity
                    : params.fieldsParams.inventory_quantity || 1;
            params.fieldsParams = Object.assign({}, params.fieldsParams, {
                inventory_quantity,
            });
        }
        let newLine = false;
        if (quants.length) {
            const lineIds = this.currentState.lines.map((l) => l.id);
            for (const quant of quants) {
                if (lineIds.includes(quant.id)) {
                    continue;
                }
                const lineParams = {
                    fieldsParams: Object.assign({}, quant, params.fieldsParams),
                };
                const newlyCreatedLine = await super._createNewLine(lineParams);
                this.selectedLineVirtualId = newlyCreatedLine.virtual_id;
                newLine = newLine || newlyCreatedLine;
                const lineWithOriginalQuantValues = Object.assign(
                    {},
                    newlyCreatedLine,
                    {
                        inventory_date: quant.inventory_date,
                        inventory_quantity: quant.inventory_quantity,
                        inventory_quantity_set: quant.inventory_quantity_set,
                        quantity: quant.quantity,
                        user_id: quant.user_id,
                    },
                );
                this.initialState.lines.push(lineWithOriginalQuantValues);
            }
        } else {
            newLine = await super._createNewLine(params);
        }
        return newLine;
    }

    _convertDataToFieldsParams(args) {
        const params = {};
        if (args.packaging && args.product.tracking === "serial") {
            params.inventory_quantity = 1;
        } else if (args.quantity) {
            params.inventory_quantity = args.quantity;
        }
        args.lot && (params.trace_id = args.lot);
        args.lotName && (params.lot_name = args.lotName);
        args.owner && (params.owner_id = args.owner);
        args.package && (params.package_id = args.package);
        args.product && (params.product_id = args.product);
        args.product &&
            args.product.uom_id &&
            (params.product_uom_id = args.product.uom_id);
        args.packaging && (params.packaging = args.packaging);
        return params;
    }

    _getNewLineDefaultValues(fieldsParams) {
        const defaultValues = super._getNewLineDefaultValues(...arguments);
        Object.assign(defaultValues, {
            inventory_date: serializeDate(now()),
            inventory_quantity: 0,
            quantity: (fieldsParams && fieldsParams.quantity) || 0,
            user_id: this.userId,
        });
        if (fieldsParams.quantity === undefined || fieldsParams.inventory_quantity) {
            defaultValues.inventory_quantity_set = true;
        }
        return defaultValues;
    }

    _getFieldToWrite() {
        return [
            "inventory_date",
            "inventory_quantity",
            "inventory_quantity_set",
            "user_id",
            "location_id",
            "lot_name",
            "trace_id",
            "package_id",
            "owner_id",
        ];
    }

    _getSaveCommand() {
        const commands = this._getSaveLineCommand();
        if (commands.length) {
            return {
                route: "/stock_barcode/save_barcode_data",
                params: {
                    model: this.resModel,
                    res_id: false,
                    write_field: false,
                    write_vals: commands,
                },
            };
        }
        return {};
    }

    _groupSublines() {
        const groupedLine = super._groupSublines(...arguments);
        const hasAtLeastOneSetSubline = groupedLine.lines.find(
            (l) => l.inventory_quantity_set,
        );
        groupedLine.inventory_quantity = groupedLine.totalQtyDone;
        groupedLine.quantity = groupedLine.totalQtyDemand;
        groupedLine.inventory_quantity_set = hasAtLeastOneSetSubline;
        return groupedLine;
    }

    _lineIsNotComplete(line) {
        return line.inventory_quantity === 0;
    }

    async _processPackage(barcodeData) {
        const { packageType, packageName } = barcodeData;
        let recPackage = barcodeData.package;
        this.lastScanned.packageId = false;
        if (!recPackage && !packageType && !packageName) {
            return;
        }
        const currentLine = this.selectedLine || this.lastScannedLine;
        if (
            currentLine?.package_id &&
            packageType &&
            !recPackage &&
            !packageName &&
            currentLine.package_id.package_type_id?.id !== packageType.id
        ) {
            await this.orm.write("stock.package", [currentLine.package_id.id], {
                package_type_id: packageType.id,
            });
            const message = _t(
                "Package type %(type)s applied to the package %(package)s",
                {
                    type: packageType.name,
                    package: currentLine.package_id.name,
                },
            );
            barcodeData.stopped = true;
            return this.notification(message, { type: "success" });
        }
        if (!recPackage && currentLine && !currentLine.package_id) {
            const valueList = {};
            if (packageName) {
                valueList.name = packageName;
            }
            if (packageType) {
                valueList.package_type_id = packageType.id;
            }
            const newPackageData = await this.orm.call(
                "stock.package",
                "action_create_from_barcode",
                [valueList],
            );
            this.cache.setCache(newPackageData);
            recPackage = newPackageData["stock.package"][0];
        }
        if (
            !recPackage ||
            (recPackage.location_id && recPackage.location_id !== this.location.id)
        ) {
            return;
        }
        const res = await this.orm.call(
            "stock.quant",
            "get_stock_barcode_counting_data",
            [recPackage.contained_quant_ids],
        );
        this.cache.setBarcodeData(res);
        const quants = res.quant_ids.map((id) =>
            this.cache.getRecord("stock.quant", id),
        );
        if (!quants.length) {
            const currentLine = this.selectedLine || this.lastScannedLine;
            if (currentLine && !currentLine.package_id) {
                const fieldsParams = this._convertDataToFieldsParams({
                    package: recPackage,
                });
                await this.updateLine(currentLine, fieldsParams);
                barcodeData.stopped = true;
                this.selectedLineVirtualId = false;
                this.lastScanned.packageId = recPackage.id;
                this.trigger("update");
            }
            return;
        }
        this.cache.setCache(res.records);

        let alreadyExisting = 0;
        for (const line of this.pageLines) {
            if (
                line.package_id &&
                line.package_id.id === recPackage.id &&
                this.getQtyDone(line) > 0
            ) {
                alreadyExisting++;
            }
        }
        if (alreadyExisting === quants.length) {
            barcodeData.error = _t("This package is already scanned.");
            return;
        }
        for (const quant of quants) {
            const product = this.cache.getRecord("product.product", quant.product_id);
            const searchLineParams = Object.assign({}, barcodeData, { product });
            const currentLine = this._findLine(searchLineParams);
            if (currentLine) {
                const fieldsParams = this._convertDataToFieldsParams({
                    quantity: quant.quantity,
                    lotName: barcodeData.lotName,
                    lot: barcodeData.lot,
                    package: recPackage,
                    owner: barcodeData.owner,
                });
                await this.updateLine(currentLine, fieldsParams);
            } else {
                const fieldsParams = this._convertDataToFieldsParams({
                    product,
                    quantity: quant.quantity,
                    lot: quant.trace_id,
                    package: quant.package_id,
                    owner: quant.owner_id,
                });
                const newLine = await this._createNewLine({ fieldsParams });
                if (newLine) {
                    newLine.inventory_quantity = quant.quantity;
                }
            }
        }
        barcodeData.stopped = true;
        this.selectedLineVirtualId = false;
        this.lastScanned.packageId = recPackage.id;
        this.trigger("update");
    }

    async _processLocation(barcodeData) {
        await super._processLocation(barcodeData);
        if (barcodeData.location && this.countEntireLocation) {
            await this.loadQuantsForLocation(barcodeData);
        }
    }

    async loadQuantsForLocation(barcodeData) {
        const res = await this.orm.call(
            "stock.location",
            "get_counted_quant_data_records",
            [barcodeData.location.id],
        );
        this.cache.setBarcodeData(res);
        const quants = res.quant_ids.map((id) =>
            this.cache.getRecord("stock.quant", id),
        );
        for (const quant of quants) {
            const product = this.cache.getRecord("product.product", quant.product_id);
            const lot =
                quant.trace_id && this.cache.getRecord("product.trace", quant.trace_id);
            const quant_package =
                quant.package_id &&
                this.cache.getRecord("stock.package", quant.package_id);
            const searchLineParams = Object.assign({}, barcodeData, { product, lot });
            searchLineParams["package"] = quant_package;
            const currentLine = this._findLine(searchLineParams);
            if (!currentLine) {
                const fieldsParams = this._convertDataToFieldsParams({
                    product,
                    quantity: quant.quantity,
                    lot: quant.trace_id,
                    package: quant.package_id,
                    owner: quant.owner_id,
                });
                const newLine = await this._createNewLine({ fieldsParams });
                if (newLine) {
                    newLine.inventory_quantity = quant.inventory_quantity;
                    newLine.inventory_quantity_set = false;
                }
            }
        }
        barcodeData.stopped = true;
        this.selectedLineVirtualId = false;
        this.trigger("update");
    }

    _updateLineQty(line, args) {
        if (args.quantity) {
            line.quantity = args.quantity;
        }
        if (args.inventory_quantity) {
            if (args.uom) {
                const lineUOM = line.product_uom_id;
                if (args.uom.factor !== lineUOM.factor) {
                    const factor = args.uom.factor / lineUOM.factor;
                    args.inventory_quantity = args.inventory_quantity * factor;
                    args.uom = lineUOM;
                }
            }
            line.inventory_quantity += args.inventory_quantity;
            if (line.inventory_quantity > 0) {
                args.inventory_quantity_set = true;
            }
            line.inventory_quantity_set = this.countEntireLocation
                ? args.inventory_quantity_set
                : true;
            if (
                line.product_id.tracking === "serial" &&
                (line.lot_name || line.trace_id)
            ) {
                line.inventory_quantity = Math.max(
                    0,
                    Math.min(1, line.inventory_quantity),
                );
            }
        }
    }

    async _updateLotName(line, lotName) {
        if (line.lot_name === lotName) {
            return;
        }
        line.lot_name = lotName;
        const owner_id = line.owner_id || false;
        const package_id = line.package_id || false;
        const existingQuant = await this.cache.getQuants(
            line.product_id,
            line.location_id.id,
            {
                trace_id: line.trace_id,
                lot_name: lotName,
                owner_id,
                package_id,
            },
        );
        if (existingQuant && existingQuant.length) {
            const quantLine = this._quantToLine(
                this.cache.getRecord("stock.quant", existingQuant[0].id),
            );
            Object.assign(line, quantLine, { virtual_id: line.virtual_id });
        }
    }

    _canOverrideTrackingNumber(line, newLotName) {
        return (
            super._canOverrideTrackingNumber(...arguments) &&
            (!line.id || line.trace_id)
        );
    }

    _createLinesState() {
        const today = serializeDate(now());
        const lines = [];
        const previousLines = new Map(
            (this.currentState?.lines || []).map((line) => [line.id, line]),
        );
        for (const id of Object.keys(this.cache.dbIdCache["stock.quant"]).map((id) =>
            Number(id),
        )) {
            const quant = this.cache.getRecord("stock.quant", id);
            if (
                (quant.user_id && quant.user_id !== this.userId) ||
                quant.inventory_date > today
            ) {
                continue;
            }
            const prevLine = previousLines.get(id);
            lines.push(this._quantToLine(quant, prevLine && prevLine.virtual_id));
        }
        return lines;
    }

    /**
     * @param {Object} quant
     * @param {number} [previousVirtualId]
     */
    _quantToLine(quant, previousVirtualId = false) {
        quant.dummy_id = quant.dummy_id && Number(quant.dummy_id);
        quant.virtual_id = quant.dummy_id || previousVirtualId || this._nextVirtualId();
        quant.product_id = this.cache.getRecord("product.product", quant.product_id);
        quant.product_uom_id = this.cache.getRecord("uom.uom", quant.product_uom_id);
        quant.location_id = this.cache.getRecord("stock.location", quant.location_id);
        quant.trace_id =
            quant.trace_id && this.cache.getRecord("product.trace", quant.trace_id);
        quant.package_id =
            quant.package_id && this.cache.getRecord("stock.package", quant.package_id);
        quant.owner_id =
            quant.owner_id && this.cache.getRecord("res.partner", quant.owner_id);
        return quant;
    }

    _getName() {
        return _t("Physical Inventory");
    }

    _getPrintOptions() {
        const options = super._getPrintOptions();
        const quantsToPrint = this.pageLines.filter(
            (quant) => quant.inventory_quantity_set,
        );
        if (quantsToPrint.length === 0) {
            return { warning: _t("There is nothing to print in this page.") };
        }
        options.additionalContext = {
            active_ids: quantsToPrint.map((quant) => quant.id),
        };
        return options;
    }

    _selectLine(line) {
        if (this.selectedLineVirtualId !== line.virtual_id) {
            this.unfoldLineKey = this.groupKey(line);
        }
        super._selectLine(...arguments);
    }

    zeroQtyClass(line) {
        return this.lineIsNotSet(line)
            ? super.zeroQtyClass(...arguments)
            : "text-danger";
    }

    _getCompanyId() {
        return this.companyIds[0];
    }

    _shouldBeExpressedInPackagingUom() {
        return false;
    }
}
