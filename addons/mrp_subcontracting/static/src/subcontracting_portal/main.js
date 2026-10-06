/** @odoo-module native */
import { startWebClient } from "@web/boot/start";
import { registry } from "@web/core/registry";

import { SubcontractingPortalWebClient } from "./subcontracting_portal.js";

const servicesToRemove = ["menu"];

const servicesRegistry = registry.category("services");

export function removeServices() {
    for (const service of servicesToRemove) {
        if (servicesRegistry.contains(service)) {
            servicesRegistry.remove(service);
        }
    }
}

removeServices();
startWebClient(SubcontractingPortalWebClient);
