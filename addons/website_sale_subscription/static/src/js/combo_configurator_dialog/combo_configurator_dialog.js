/** @odoo-module native */
import { t } from "@odoo/owl";
import { comboConfiguratorDialogProps } from "@sale/js/combo_configurator_dialog/combo_configurator_dialog";

Object.assign(comboConfiguratorDialogProps, {
    allow_one_time_sale: t.boolean().optional(),
});
