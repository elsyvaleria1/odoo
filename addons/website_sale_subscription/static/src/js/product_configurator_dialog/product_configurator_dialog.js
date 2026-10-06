/** @odoo-module native */
import { t } from "@odoo/owl";
import { productConfiguratorDialogProps } from "@sale/js/product_configurator_dialog/product_configurator_dialog";

Object.assign(productConfiguratorDialogProps, {
    allow_one_time_sale: t.boolean().optional(),
});
