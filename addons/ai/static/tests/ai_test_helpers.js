import { mailModels } from "@mail/../tests/mail_test_helpers";
import { registerMailMockRoutes } from "@mail/../tests/mock_server/mail_mock_server";
import { defineModels } from "@web/../tests/web_test_helpers";

import { AIAgent } from "./mock_server/mock_models/ai_agent.js";
import { AIComposer } from "./mock_server/mock_models/ai_composer.js";
import { DiscussChannel } from "./mock_server/mock_models/discuss_channel.js";

export function defineAIModels() {
    registerMailMockRoutes();
    return defineModels(aiModels);
}

export const aiModels = { ...mailModels, DiscussChannel, AIAgent, AIComposer };
