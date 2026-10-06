import { mailModels } from "@mail/../tests/mail_test_helpers";

import { BarcodeNomenclature } from "./mock_models/barcode_nomenclature.js";
import { BarcodeRule } from "./mock_models/barcode_rule.js";
import { ProductProduct } from "./mock_models/product_product.js";
import { StockLocation } from "./mock_models/stock_location.js";
import { StockMoveLine } from "./mock_models/stock_move_line.js";
import { StockPicking } from "./mock_models/stock_picking.js";
import { StockPickingType } from "./mock_models/stock_picking_type.js";
import { UoM } from "./mock_models/uom.js";
import { UoMCategory } from "./mock_models/uom_category.js";

export const stockBarcodeProductExpiryModels = {
    ...mailModels,
    StockPicking,
    StockPickingType,
    StockMoveLine,
    ProductProduct,
    UoMCategory,
    UoM,
    StockLocation,
    BarcodeRule,
    BarcodeNomenclature,
};
