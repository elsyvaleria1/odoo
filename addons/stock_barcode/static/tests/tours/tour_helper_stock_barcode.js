import { assert, fail } from "@stock/../tests/tours/tour_helper";
export { assert, fail };

/**
 * @param {(HTMLElement|integer)} lineOrIndex
 * @param {string} errorClue
 * @returns {HTMLElement}
 */
export function _getLineOrFail(lineOrIndex, errorClue = "No line found") {
    const line =
        typeof lineOrIndex === "number"
            ? document.querySelectorAll(".o_barcode_line")[lineOrIndex]
            : lineOrIndex;
    if (line instanceof HTMLElement) {
        return line;
    }
    const errorMessage =
        typeof lineOrIndex === "number"
            ? `${errorClue}: the given index (${lineOrIndex}) doesn't match an existing line`
            : `${errorClue}: the given object isn't a line`;
    fail(errorMessage);
}
/**
 * @param {string} selector
 * @param {Object} description
 * @param {string} [description.barcode]
 * @param {Boolean} [description.completed]
 * @param {Boolean} [description.selected]
 * @param {string} [description.selector]
 * @returns {string}
 */
export function _prepareSelector(selector, description) {
    const { barcode, selected, completed } = description;
    if (selected !== undefined) {
        selector += selected ? ".o_selected" : ":not(.o_selected)";
    }
    if (completed !== undefined) {
        selector += completed ? ".o_line_completed" : ":not(.o_line_completed)";
    }
    selector += barcode ? `[data-barcode="${barcode}"]` : "";
    description.selector = selector;
    return selector;
}

/**
 * @param {Object} description
 * @returns {HTMLElement}
 */
export function getLine(description = {}) {
    const line = getLines(description);
    if (line.length > 1) {
        fail(
            `getLine: Multiple lines were found for the selector "${description.selector}" (use 'getLines' instead if its wanted)`,
        );
    } else if (line.length === 0) {
        fail(`getLine: No line was found for the selector "${description.selector}"`);
    }
    return line[0];
}

/**
 * @param {Object} [description]
 * @returns {Element[]}
 */
export function getLines(description = {}) {
    const selector = _prepareSelector(
        ":not(.o_sublines) > .o_barcode_line",
        description,
    );
    const lines = document.querySelectorAll(selector);
    const { index } = description;
    if (index === undefined) {
        return Array.from(lines);
    }
    const indexes = typeof index === "number" ? [index] : index;
    const missing = indexes.filter((i) => !lines[i]);
    if (missing.length) {
        fail(
            `getLines: no line at index ${missing.join(", ")} for the selector "${selector}" (${lines.length} found)`,
        );
    }
    return indexes.map((i) => lines[i]);
}

export function getSubline(description = {}) {
    const subline = getSublines(description);
    if (subline.length > 1) {
        fail(`Multiple sublines were found for the selector "${description.selector}"`);
    }
    return subline[0];
}

export function getSublines(description = {}) {
    const selector = _prepareSelector(".o_sublines .o_barcode_line", description);
    const sublines = document.querySelectorAll(selector);
    if (!sublines.length) {
        fail(`No subline was found for the selector "${selector}"`);
    }
    return sublines;
}

/**
 * @param {HTMLElement|Integer} lineOrIndex
 * @param {string} buttonName
 * @param {boolean} [shouldBeVisible=true]
 */
export function assertButtonIsVisible(lineOrIndex, buttonName, shouldBeVisible = true) {
    const line = _getLineOrFail(lineOrIndex);
    const button = line.querySelector(`.o_line_button.o_${buttonName}`);
    const label = line.querySelector(".o_product_label,.package")?.innerText;
    assert(
        !!button,
        shouldBeVisible,
        `${label ? label + " line" : "Line"}'s button "${buttonName}" ${
            shouldBeVisible ? "should" : "should not"
        } be visible`,
    );
}

export function assertValidateVisible(expected) {
    const validateButton = document.querySelector(".o_validate_page,.o_apply_page");
    assert(!!validateButton, expected, "Validate visible");
}

export function assertValidateEnabled(expected) {
    const validateButton =
        document.querySelector(".o_validate_page,.o_apply_page") || false;
    assert(
        validateButton && !validateButton.hasAttribute("disabled"),
        expected,
        "Validate enabled",
    );
}

export function assertValidateIsHighlighted(expected) {
    const validateButton =
        document.querySelector(".o_validate_page,.o_apply_page") || false;
    const isHighlighted =
        validateButton && validateButton.classList.contains("btn-primary");
    assert(isHighlighted, expected, "Validate button is highlighted");
}

export function assertLinesCount(expectedCount, description) {
    const currentCount = getLines(description).length;
    assert(currentCount, expectedCount, `Should have ${expectedCount} line(s)`);
}

export function assertScanMessage(expected) {
    const instruction = document.querySelector(`.o_scan_message`);
    const cssClass = instruction.classList[1];
    assert(cssClass, `o_${expected}`, "Not the right message displayed");
}

export function assertSublinesCount(expected) {
    const current = document.querySelectorAll(".o_sublines > .o_barcode_line").length;
    assert(current, expected, `Should have ${expected} subline(s), found ${current}`);
}

export function assertLineDestinationIsNotVisible(lineOrIndex) {
    const line = _getLineOrFail(lineOrIndex);
    const destinationElement = line.querySelector(".o_line_destination_location");
    if (destinationElement) {
        const product = line.querySelector(".o_product_label").innerText;
        fail(
            `The destination for line of the product ${product} should not be visible, "${destinationElement.innerText}" instead`,
        );
    }
}

/**
 * @param {Element} lineOrIndex
 * @param {string} location
 */
export function assertLineDestinationLocation(lineOrIndex, location) {
    const line = _getLineOrFail(lineOrIndex, "Can't check the line's destination");
    const destinationElement = line.querySelector(".o_line_destination_location");
    const product = line.querySelector(".o_product_label").innerText;
    if (!destinationElement) {
        fail(
            `The destination (${location}) for line of the product ${product} is not visible`,
        );
    }
    assert(
        destinationElement.innerText,
        location,
        `The destination for line of product ${product} isn't in the right location`,
    );
}

export function assertLineIsHighlighted(lineOrIndex, expected = true) {
    const line = _getLineOrFail(lineOrIndex, "Can't check if the line is highlighted");
    const errorMessage = `line ${expected ? "should" : "shouldn't"} be highlighted`;
    assert(line.classList.contains("o_highlight"), expected, errorMessage);
}

export function assertLineLocations(lineOrIndex, source = null, destination = null) {
    const line = _getLineOrFail(lineOrIndex, "Can't check line's locations");
    if (source) {
        assertLineSourceLocation(line, source);
    } else {
        assertLineSourceIsNotVisible(line);
    }
    if (destination) {
        assertLineDestinationLocation(line, destination);
    } else {
        assertLineDestinationIsNotVisible(line);
    }
}

export function assertLineProduct(lineOrIndex, productName) {
    const line = _getLineOrFail(lineOrIndex, "Can't check line's product");
    const lineProduct = line.querySelector(".o_product_label").innerText;
    assert(lineProduct, productName, "Not the expected product");
}

/**
 * @param {(HTMLElement|integer)} lineOrIndex
 * @param {string} expectedQuantityWithUOM
 */
export function assertLineQty(lineOrIndex, expectedQuantityWithUOM) {
    const line = _getLineOrFail(lineOrIndex, "Can't check the line's quantity");
    const elQty = line.querySelector(".o_barcode_scanner_qty");
    const elUOM = line.querySelector(".o_line_uom");
    let qtyText = elQty.innerText;
    let errorMessage = "Something wrong with the quantities";
    if (elUOM) {
        qtyText += " " + elUOM.innerText;
        errorMessage += " or with the Unit of Measure";
    }
    assert(qtyText, expectedQuantityWithUOM, errorMessage);
}

/**
 * @param {(HTMLElement|integer)} lineOrIndex
 * @param {string} [expectedPackageName]
 */
export function assertLinePackage(lineOrIndex, expectedPackageName = false) {
    const line = _getLineOrFail(lineOrIndex, "Can't check the line's result package");
    const packageEl = line.querySelector("div[name='package'] > .package");
    if (!packageEl) {
        if (expectedPackageName) {
            fail(`There is no package: ${expectedPackageName} expected`);
        }
    } else {
        const linePackageName = packageEl.innerText;
        assert(linePackageName, expectedPackageName, "Not the expected line's package");
    }
}

/**
 * @param {(HTMLElement|integer)} lineOrIndex
 * @param {string} [expectedPackageName]
 */
export function assertLineResultPackage(lineOrIndex, expectedPackageName = false) {
    const line = _getLineOrFail(lineOrIndex, "Can't check the line's result package");
    const resultPackageEl = line.querySelector(".result-package");
    if (!resultPackageEl) {
        if (expectedPackageName) {
            fail(`There is no result package: ${expectedPackageName} expected`);
        }
    } else {
        const linePackageName = resultPackageEl.innerText;
        assert(linePackageName, expectedPackageName, "Not the expected result package");
    }
}

export function assertLinePackages(
    lineOrIndex,
    expectedSrcPackageName,
    expectedResultPackageName,
) {
    assertLinePackage(lineOrIndex, expectedSrcPackageName);
    assertLineResultPackage(lineOrIndex, expectedResultPackageName);
}

export function assertLineSourceIsNotVisible(lineOrIndex) {
    const line = _getLineOrFail(lineOrIndex);
    const sourceElement = line.parentNode.querySelector(".o_barcode_location_line");
    if (sourceElement) {
        const product = line.querySelector(".o_product_label").innerText;
        fail(
            `The location for line of the product ${product} should not be visible, "${sourceElement.innerText}" instead`,
        );
    }
}

/**
 * @param {(HTMLElement|integer)} lineOrIndex
 * @param {string|Boolean} expectedTrackingNumber
 */
export function assertLineTrackingNumber(lineOrIndex, expectedTrackingNumber) {
    const line = _getLineOrFail(lineOrIndex);
    const elTrackingNumber = line.querySelector(".o_line_lot_name");
    const product = line.querySelector(".o_product_label")?.innerText || "";
    if (expectedTrackingNumber === false) {
        assert(
            !!elTrackingNumber,
            false,
            `No tracking number should be visible on the ${product} line`,
        );
    } else {
        assert(
            !!elTrackingNumber,
            true,
            `${expectedTrackingNumber} should be visible but there is no tracking number on the ${product} line`,
        );
        assert(
            elTrackingNumber.innerText,
            expectedTrackingNumber,
            `Not the expected tracking number for the ${product} line`,
        );
    }
}

/**
 * @param {HTMLElement[]} lines
 * @param {string[]} trackingNumbers
 */
export function assertLinesTrackingNumbers(lines, trackingNumbers) {
    assert(
        lines.length,
        trackingNumbers.length,
        "Not the same amount of lines and tracking numbers",
    );
    for (const [index, line] of lines.entries()) {
        assertLineTrackingNumber(line, trackingNumbers[index]);
    }
}

/**
 * @param {Element} lineOrIndex
 * @param {string} location
 */
export function assertLineSourceLocation(lineOrIndex, location) {
    const line = _getLineOrFail(lineOrIndex, "Can't check the line's source");
    const sourceElement = line.parentNode.querySelector(".o_barcode_location_line");
    const product = line.querySelector(".o_product_label").innerText;
    if (!sourceElement) {
        fail(
            `The source (${location}) for line of the product ${product} is not visible`,
        );
    }
    assert(
        sourceElement.innerText,
        location,
        `The source for line of product ${product} isn't in the right location`,
    );
}

export function assertLineDescription(lineOrIndex, description) {
    const line = _getLineOrFail(lineOrIndex, "Can't check the line's description");
    const descriptionElement = line.querySelector("div[name='description']");
    assert(descriptionElement.innerText, description, "Wrong description");
}

export function assertFormLocationSrc(expected) {
    const location = document.querySelector(
        '.o_field_widget[name="location_id"] input',
    );
    assert(location.value, expected, "Wrong source location");
}

export function assertFormLocationDest(expected) {
    const location = document.querySelector(
        '.o_field_widget[name="location_dest_id"] input',
    );
    assert(location.value, expected, "Wrong destination location");
}

export function assertFormQuantity(expected) {
    const quantityField = document.querySelector(
        '.o_field_widget[name="inventory_quantity"] input, .o_field_widget[name="qty_done"] input',
    );
    assert(quantityField.value, expected, "Wrong quantity");
}

export function assertKanbanRecordsCount(expected) {
    const kanbanRecords = document.querySelectorAll(
        ".o_kanban_view .o_kanban_record:not(.o_kanban_ghost)",
    );
    assert(kanbanRecords.length, expected, "Wrong number of cards");
}

export function assertLineIsFaulty(lineOrIndex, expected = true) {
    const line = _getLineOrFail(lineOrIndex, "Can't check if the line is faulty");
    const errorMessage = `line ${expected ? "should" : "shouldn't"} be faulty`;
    assert(line.classList.contains("o_faulty"), expected, errorMessage);
}
