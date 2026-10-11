import * as Dialog from "@point_of_sale/../tests/generic_helpers/dialog_util";
import * as ChromePos from "@point_of_sale/../tests/pos/tours/utils/chrome_util";
import * as ProductScreenPos from "@point_of_sale/../tests/pos/tours/utils/product_screen_util";
import * as ChromeRestaurant from "@pos_restaurant/../tests/tours/utils/chrome";
import * as FloorScreen from "@pos_restaurant/../tests/tours/utils/floor_screen_util";
import * as ProductScreenResto from "@pos_restaurant/../tests/tours/utils/product_screen_util";
import { registry } from "@web/core/registry";

const Chrome = { ...ChromePos, ...ChromeRestaurant };
const ProductScreen = { ...ProductScreenPos, ...ProductScreenResto };

const wait = (ms) => ({
    content: `wait for ${ms} ms`,
    trigger: "body",
    run: async () => {
        await new Promise((resolve) => setTimeout(resolve, ms));
    },
});

const addOrderlines = (productNames, quantity) => {
    const steps = [];
    productNames.forEach((productName) => {
        steps.push(ProductScreen.addOrderline(productName, quantity));
    });
    return steps.flat();
};

const updateOrderlines = (productNames, previousQuantity, newQuantity) => {
    const steps = [];
    productNames.forEach((productName) => {
        steps.push(ProductScreen.clickOrderline(productName, previousQuantity));
        steps.push(ProductScreen.clickNumpad(newQuantity));
        steps.push(ProductScreen.selectedOrderlineHas(productName, newQuantity));
    });
    return steps.flat();
};

registry.category("web_tour.tours").add("table_action_transfer", {
    steps: () =>
        [
            Chrome.startPoS(),
            Dialog.confirm("Open Register"),

            FloorScreen.clickTable("4"),
            addOrderlines(["Coca-Cola", "Water", "Minute Maid", "Fanta"], "3"),
            ProductScreen.clickOrderButton(),
            FloorScreen.clickTable("4"),
            updateOrderlines(["Water", "Minute Maid", "Fanta"], "3", "1"),
            ProductScreen.clickOrderButton(),
            FloorScreen.clickTable("4"),
            updateOrderlines(["Minute Maid", "Fanta"], "1", "6"),
            ProductScreen.clickOrderButton(),
            FloorScreen.clickTable("4"),
            updateOrderlines(["Fanta"], "6", "3"),
            ProductScreen.clickOrderButton(),

            FloorScreen.clickTable("4"),
            ProductScreen.clickControlButton("Transfer"),
            FloorScreen.clickTable("5"),
            wait(100),

            updateOrderlines(["Coca-Cola"], "3", "1"),
            ProductScreen.clickOrderButton(),

            FloorScreen.clickTable("5"),
            updateOrderlines(["Coca-Cola", "Water"], "1", "6"),
            ProductScreen.clickOrderButton(),

            FloorScreen.clickTable("5"),
            updateOrderlines(["Coca-Cola", "Water", "Minute Maid"], "6", "3"),
            ProductScreen.clickOrderButton(),
            wait(100),
        ].flat(),
});

registry.category("web_tour.tours").add("table_action_merge", {
    steps: () =>
        [
            Chrome.startPoS(),
            Dialog.confirm("Open Register"),

            FloorScreen.clickTable("4"),
            addOrderlines(["Coca-Cola", "Water", "Minute Maid", "Fanta"], "3"),
            ProductScreen.clickOrderButton(),
            FloorScreen.clickTable("4"),
            updateOrderlines(["Water", "Minute Maid", "Fanta"], "3", "1"),
            ProductScreen.clickOrderButton(),
            FloorScreen.clickTable("4"),
            updateOrderlines(["Minute Maid", "Fanta"], "1", "6"),
            ProductScreen.clickOrderButton(),
            FloorScreen.clickTable("4"),
            updateOrderlines(["Fanta"], "6", "3"),
            ProductScreen.clickOrderButton(),

            FloorScreen.clickTable("5"),
            addOrderlines(["Espresso", "Cocktail", "Beer", "Champagne"], "3"),
            ProductScreen.clickOrderButton(),
            FloorScreen.clickTable("5"),
            updateOrderlines(["Cocktail", "Beer", "Champagne"], "3", "1"),
            ProductScreen.clickOrderButton(),
            FloorScreen.clickTable("5"),
            updateOrderlines(["Beer", "Champagne"], "1", "6"),
            ProductScreen.clickOrderButton(),
            FloorScreen.clickTable("5"),
            updateOrderlines(["Champagne"], "6", "3"),
            ProductScreen.clickOrderButton(),

            FloorScreen.clickTable("5"),
            ProductScreen.clickControlButton("Merge"),
            FloorScreen.clickTable("4"),
            wait(100),

            updateOrderlines(["Coca-Cola", "Espresso"], "3", "1"),
            ProductScreen.clickOrderButton(),

            FloorScreen.clickTable("4"),
            updateOrderlines(["Coca-Cola", "Water", "Espresso", "Cocktail"], "1", "6"),
            ProductScreen.clickOrderButton(),

            FloorScreen.clickTable("4"),
            updateOrderlines(
                ["Coca-Cola", "Water", "Minute Maid", "Espresso", "Cocktail", "Beer"],
                "6",
                "3",
            ),
            ProductScreen.clickOrderButton(),
            wait(100),
        ].flat(),
});

registry.category("web_tour.tours").add("table_action_link", {
    steps: () =>
        [
            Chrome.startPoS(),
            Dialog.confirm("Open Register"),

            FloorScreen.clickTable("4"),
            addOrderlines(["Coca-Cola", "Water", "Minute Maid", "Fanta"], "3"),
            ProductScreen.clickOrderButton(),
            FloorScreen.clickTable("4"),
            updateOrderlines(["Water", "Minute Maid", "Fanta"], "3", "1"),
            ProductScreen.clickOrderButton(),
            FloorScreen.clickTable("4"),
            updateOrderlines(["Minute Maid", "Fanta"], "1", "6"),
            ProductScreen.clickOrderButton(),
            FloorScreen.clickTable("4"),
            updateOrderlines(["Fanta"], "6", "3"),
            ProductScreen.clickOrderButton(),

            FloorScreen.clickTable("5"),
            addOrderlines(["Espresso", "Cocktail", "Beer", "Champagne"], "3"),
            ProductScreen.clickOrderButton(),
            FloorScreen.clickTable("5"),
            updateOrderlines(["Cocktail", "Beer", "Champagne"], "3", "1"),
            ProductScreen.clickOrderButton(),
            FloorScreen.clickTable("5"),
            updateOrderlines(["Beer", "Champagne"], "1", "6"),
            ProductScreen.clickOrderButton(),
            FloorScreen.clickTable("5"),
            updateOrderlines(["Champagne"], "6", "3"),
            ProductScreen.clickOrderButton(),

            FloorScreen.linkTables("5", "4"),
            wait(100),

            FloorScreen.clickTable("4"),
            updateOrderlines(["Coca-Cola", "Espresso"], "3", "1"),
            ProductScreen.clickOrderButton(),

            FloorScreen.clickTable("4"),
            updateOrderlines(["Coca-Cola", "Water", "Espresso", "Cocktail"], "1", "6"),
            ProductScreen.clickOrderButton(),

            FloorScreen.clickTable("4"),
            updateOrderlines(
                ["Coca-Cola", "Water", "Minute Maid", "Espresso", "Cocktail", "Beer"],
                "6",
                "3",
            ),
            ProductScreen.clickOrderButton(),
            wait(100),
        ].flat(),
});

registry.category("web_tour.tours").add("table_action_unlink", {
    steps: () =>
        [
            Chrome.startPoS(),
            Dialog.confirm("Open Register"),

            FloorScreen.clickTable("4"),
            addOrderlines(["Coca-Cola", "Water", "Minute Maid", "Fanta"], "3"),
            ProductScreen.clickOrderButton(),
            FloorScreen.clickTable("4"),
            updateOrderlines(["Water", "Minute Maid", "Fanta"], "3", "1"),
            ProductScreen.clickOrderButton(),
            FloorScreen.clickTable("4"),
            updateOrderlines(["Minute Maid", "Fanta"], "1", "6"),
            ProductScreen.clickOrderButton(),
            FloorScreen.clickTable("4"),
            updateOrderlines(["Fanta"], "6", "3"),
            ProductScreen.clickOrderButton(),

            FloorScreen.clickTable("5"),
            addOrderlines(["Espresso", "Cocktail", "Beer", "Champagne"], "3"),
            ProductScreen.clickOrderButton(),
            FloorScreen.clickTable("5"),
            updateOrderlines(["Cocktail", "Beer", "Champagne"], "3", "1"),
            ProductScreen.clickOrderButton(),
            FloorScreen.clickTable("5"),
            updateOrderlines(["Beer", "Champagne"], "1", "6"),
            ProductScreen.clickOrderButton(),
            FloorScreen.clickTable("5"),
            updateOrderlines(["Champagne"], "6", "3"),
            ProductScreen.clickOrderButton(),

            FloorScreen.linkTables("5", "4"),
            wait(100),

            FloorScreen.clickTable("4"),
            updateOrderlines(["Coca-Cola", "Espresso"], "3", "1"),
            ProductScreen.clickOrderButton(),

            FloorScreen.clickTable("4"),
            updateOrderlines(["Coca-Cola", "Water", "Espresso", "Cocktail"], "1", "6"),
            ProductScreen.clickOrderButton(),

            FloorScreen.clickTable("4"),
            updateOrderlines(
                ["Coca-Cola", "Water", "Minute Maid", "Espresso", "Cocktail", "Beer"],
                "6",
                "3",
            ),
            ProductScreen.clickOrderButton(),

            FloorScreen.unlinkTables("5", "4"),
            wait(100),

            FloorScreen.clickTable("4"),
            updateOrderlines(["Beer"], "-3", "0"),
            updateOrderlines(["Coca-Cola", "Water"], "3", "5"),
            ProductScreen.clickOrderButton(),
            FloorScreen.clickTable("4"),
            updateOrderlines(["Water"], "5", "1"),
            ProductScreen.clickOrderButton(),

            FloorScreen.clickTable("5"),
            updateOrderlines(["Beer"], "6", "3"),
            updateOrderlines(["Espresso", "Champagne"], "3", "5"),
            ProductScreen.clickOrderButton(),
            FloorScreen.clickTable("5"),
            updateOrderlines(["Champagne"], "5", "1"),
            ProductScreen.clickOrderButton(),
            wait(100),
        ].flat(),
});
