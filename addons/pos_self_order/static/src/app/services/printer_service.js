/** @odoo-module native */
import { printerService } from "@point_of_sale/app/services/printer_service";
import { registry } from "@web/core/registry";
registry.category("services").add("printer", printerService);
