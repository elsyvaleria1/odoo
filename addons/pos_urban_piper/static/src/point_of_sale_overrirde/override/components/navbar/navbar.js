/** @odoo-module native */
import { Navbar } from "@point_of_sale/app/components/navbar/navbar";
import { DeliveryButton } from "@pos_urban_piper/point_of_sale_overrirde/app/delivery_button/delivery_button";
import { patch } from "@web/core/utils/patch";

patch(Navbar, {
    components: { ...Navbar.components, DeliveryButton },
});
