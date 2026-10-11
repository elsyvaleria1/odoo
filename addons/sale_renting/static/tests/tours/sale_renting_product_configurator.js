import configuratorTourUtils from "@sale/js/tours/product_configurator_tour_utils";
import tourUtils from "@sale/js/tours/tour_utils";
import { registry } from "@web/core/registry";
import { stepUtils } from "@web_tour/tour_utils";

registry.category("web_tour.tours").add("sale_renting_product_configurator", {
    url: "/odoo",
    steps: () => [
        ...stepUtils.goToAppSteps(
            "sale_renting.rental_menu_root",
            "Open the rental app",
        ),
        {
            content: "Create a new SO",
            trigger: ".o-kanban-button-new",
            run: "click",
        },
        ...tourUtils.selectCustomer("Test Partner"),
        ...tourUtils.addProduct("Main product"),
        configuratorTourUtils.assertProductPrice("Main product", "15.00"),
        configuratorTourUtils.assertProductPriceInfo("Main product", "1 Day"),
        configuratorTourUtils.assertOptionalProductPrice("Optional product", "16.00"),
        configuratorTourUtils.assertOptionalProductPriceInfo(
            "Optional product",
            "1 Day",
        ),
        ...configuratorTourUtils.saveConfigurator(),
        ...stepUtils.saveForm(),
    ],
});
