/** @odoo-module native */
export class BarcodeObject {
    constructor(rawValue) {
        this.rawValue = rawValue; // Untouched barcode.

        this.parsedBarcode = undefined; // Barcode's value(s) once it has been parsed.
        this.isParsed = false; // Flag to know if barcode was already parsed.
        this.missingRecords = []; // Keep track of missing records (try to fetch them later.)
        this.isURN = Boolean(this.rawValue.match(/^urn:.*$/));

        if (this.parser) {
            try {
                this.parsedBarcode = this.parser.parseBarcode(this.rawValue);
            } catch (err) {
                // The barcode can't be parsed but the error is caught to fallback
                // on the classic way to handle barcodes.
                console.warn(
                    `Barcode ${this.rawValue} could not be parsed:`,
                    err.message,
                );
            }
            if (this.parsedBarcode && !Array.isArray(this.parsedBarcode)) {
                // Depending of the nomenclature, the parsed data is either an object,
                // either an array of objects. Convert it into an array in all case.
                this.parsedBarcode = [this.parsedBarcode];
            }
            this.isParsed = Boolean(this.parsedBarcode?.length);
        } else {
            console.warn("No parser set !");
        }

        // Adds this instance into the raw barcode/barcode object mapping.
        BarcodeObject.mappingRawBarcodeToObject[rawValue] = this;
    }

    /**
     * Attach to the barcode record(s) already in the cache.
     * For missing record(s), they need to be fetched afterward.
     */
    async setRecords(options = false) {
        if (!this.isParsed) {
            return;
        }
        options = options || {
            fetchLater: true,
            onlyInCache: true,
        };
        this.missingRecords = [];
        for (const barcodeData of this.parsedBarcode) {
            const { type, code } = barcodeData;
            if (type === "product") {
                await this.fetchProduct(code, options);
            } else if (type === "lot") {
                await this.fetchTrackingNumber(code, options);
            }
        }
    }

    // Getters
    get cache() {
        return BarcodeObject.__cache;
    }

    get hasMissingRecords() {
        return this.isParsed && Boolean(this.missingRecords.length);
    }

    get parser() {
        return BarcodeObject.__parser;
    }

    // Fetching methods
    async fetchTrackingNumber(lotBarcode, options) {
        const lot = await this.cache.getRecordByBarcode(
            lotBarcode,
            "product.trace",
            options,
        );
        if (!lot) {
            this.missingRecords.push({ type: "lot", lotBarcode });
        }
    }

    async fetchProduct(productBarcode, options) {
        let product = await this.cache.getRecordByBarcode(
            productBarcode,
            "product.product",
            options,
        );
        if (!product) {
            const packaging = await this.cache.getRecordByBarcode(
                productBarcode,
                "product.uom",
                {
                    onlyInCache: true,
                },
            );
            if (packaging) {
                product = this.cache.getRecord(
                    "product.product",
                    packaging.product_id,
                    false,
                );
            }
        }
        if (!product) {
            this.missingRecords.push({ type: "product", productBarcode });
        }
    }
}

// Static properties and methods.
BarcodeObject.mappingRawBarcodeToObject = {};

BarcodeObject.setEnv = (cache, parser) => {
    BarcodeObject.__cache = cache;
    BarcodeObject.__parser = parser;
};

BarcodeObject.forBarcode = (barcode) => {
    if (BarcodeObject.mappingRawBarcodeToObject[barcode]) {
        return BarcodeObject.mappingRawBarcodeToObject[barcode];
    }
    return new BarcodeObject(barcode);
};
