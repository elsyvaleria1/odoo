/** @odoo-module native */
import { BaseOptionComponent } from "@html_builder/core/utils";
import { after } from "@html_builder/utils/option_sequence";
import { Plugin } from "@html_editor/plugin";
import { withSequence } from "@html_editor/utils/resource";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { FORUMS_INDEX } from "@website_forum/website_builder/forum_page_option_plugin";

export class SlidesForumOption extends BaseOptionComponent {
    static template = "website_slides_forum.slidesForumOption";
    static selector = "main:has(#o_wforum_forums_index_list)";
    static title = _t("Slides Forum Snippet Options");
    static groups = ["website.group_website_designer"];
    static editableOnly = false;
}

class SlidesForumOptionPlugin extends Plugin {
    static id = "slidesForumOption";
    resources = {
        builder_options: [withSequence(after(FORUMS_INDEX), SlidesForumOption)],
    };
}

registry
    .category("website-plugins")
    .add(SlidesForumOptionPlugin.id, SlidesForumOptionPlugin);
