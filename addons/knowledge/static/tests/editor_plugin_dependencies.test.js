import { PositionPlugin } from "@html_editor/main/position_plugin";
import { KnowledgeCommentsPlugin } from "@knowledge/editor/plugins/comments_plugin/comments_plugin";
import { describe, expect, test } from "@odoo/hoot";

describe("Implicit plugin dependencies", () => {
    test("position as an implicit dependency", async () => {
        for (const P of [KnowledgeCommentsPlugin]) {
            expect(P.dependencies).toInclude(PositionPlugin.id);
        }
    });
});
