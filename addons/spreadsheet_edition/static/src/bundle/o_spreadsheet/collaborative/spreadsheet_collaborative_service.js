/** @odoo-module native */
import { registry } from "@web/core/registry";

import { SpreadsheetCollaborativeChannel } from "./spreadsheet_collaborative_channel.js";

const spreadsheetCollaborativeService = {
    dependencies: SpreadsheetCollaborativeChannel.dependencies,
    start(env, dependencies) {
        return {
            makeCollaborativeChannel(resModel, resId, accessToken, revisionSequence) {
                return new SpreadsheetCollaborativeChannel(
                    env,
                    resModel,
                    resId,
                    accessToken,
                    revisionSequence,
                );
            },
        };
    },
};

registry
    .category("services")
    .add("spreadsheet_collaborative", spreadsheetCollaborativeService);
