import { defineModels, webModels } from "@web/../tests/web_test_helpers";

import { ResourceResource } from "./_framework/mock_server/mock_models/resource_resource.js";

export const resourceModels = {
    ResourceResource,
};

export function defineResourceModels() {
    return defineModels({ ...resourceModels, ...webModels });
}
