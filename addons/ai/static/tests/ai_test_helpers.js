import { mailModels } from "@mail/../tests/mail_test_helpers";
import { registerMailMockRoutes } from "@mail/../tests/mock_server/mail_mock_server";
import { defineModels } from "@web/../tests/web_test_helpers";

import { AIAgent } from "./mock_server/mock_models/ai_agent.js";
import { AIComposer } from "./mock_server/mock_models/ai_composer.js";
import { DiscussChannel } from "./mock_server/mock_models/discuss_channel.js";

/**
 * Define the ai models AND bind mail's mock routes to the calling file.
 *
 * `mail_mock_server.js` registers `/mail/data` & co. at module level, which
 * binds them to whichever test file's suite happened to import it first; every
 * other file loses them unless `registerMailMockRoutes()` replays them (see
 * that function's docstring). `defineMailModels()` does this for mail's own
 * tests -- ai spreads `mailModels` into `defineModels()` instead, which
 * registers the *models* but never the *routes*, leaving `/mail/data` unmocked
 * (the store then silently receives no channel data).
 */
export function defineAIModels() {
    registerMailMockRoutes();
    return defineModels(aiModels);
}

export const aiModels = { ...mailModels, DiscussChannel, AIAgent, AIComposer };
