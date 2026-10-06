/** @odoo-module native */
import { SubcontractingPortalWebClient } from "@mrp_subcontracting/subcontracting_portal/subcontracting_portal";
import { startWebClient } from "@web/boot/start";

import { removeServices } from "./remove_services.js";

removeServices();
startWebClient(SubcontractingPortalWebClient);
