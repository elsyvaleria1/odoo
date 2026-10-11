import { expect, test } from "@odoo/hoot";
import { ProductNameAndDescriptionField } from "@product/product_name_and_description/product_name_and_description";

/** @param {string} productName @param {string} description */
function labelOf(productName, description) {
    const self = Object.create(ProductNameAndDescriptionField.prototype);
    Object.assign(self, {
        descriptionColumn: "name",
        props: {
            name: "product_id",
            record: {
                data: { name: description, product_id: { display_name: productName } },
            },
        },
    });
    return self.label;
}

test("the product name written as a prefix is stripped", () => {
    expect(labelOf("Desk", "Desk\nwith drawers")).toBe("with drawers");
    expect(labelOf("[DESK01] Desk", "[DESK01] Desk\nwith drawers")).toBe(
        "with drawers",
    );
});

test("a description that only mentions the product name is left alone", () => {
    expect(labelOf("Desk", "Spare leg for a Desk")).toBe("Spare leg for a Desk");
});

test("a description equal to the product name yields no label", () => {
    expect(labelOf("Desk", "Desk")).toBe("");
});

test("an empty description does not throw", () => {
    expect(labelOf("Desk", "")).toBe("");
});
