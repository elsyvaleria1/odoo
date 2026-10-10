/** @odoo-module native */
import { registry } from "@web/core/registry";

import { SpreadsheetCollaborativeChannel } from "./spreadsheet_collaborative_channel.js";

/**
 * Creates a channel to handle collaborative edition of a spreadsheet.
 * This service can be mocked to mock the channel in tests.
 */
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
