/** @odoo-module native */

import { registry } from "@web/core/registry";

// Field Service installs as its own scoped PWA rather than as the whole web
// client. `web` used to carry this action path in a hardcoded list, which
// meant the base of the addon graph naming a module downstream of it and
// nothing failing when the path changed. The owner declares it instead.
registry.category("scoped_app_installers").add("field-service", true);
