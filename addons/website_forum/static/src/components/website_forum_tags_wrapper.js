/** @odoo-module native */
import { Component, onWillStart, proxy, t, useProps } from "@odoo/owl";
import { DropdownItem } from "@web/components/dropdown";
import { SelectMenu } from "@web/components/select_menu";
import { get } from "@web/core/network";

export class WebsiteForumTagsWrapper extends Component {
    static template = "website_forum.WebsiteForumTagsWrapper";
    static components = { SelectMenu, DropdownItem };
    static props = {
        defaulValue: t.array().optional(),
        isReadOnly: t.boolean().optional(false),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.state = proxy({
            value: this.props.defaulValue || [],
        });
        onWillStart(async () => {
            await this.loadChoices();
        });
    }

    showCreateOption(searchValue) {
        const karma = document.querySelector("#karma").value;
        const editKarma = document.querySelector("#karma_edit_retag").value;
        const hasEnoughKarma = parseInt(karma) >= parseInt(editKarma);

        return (
            hasEnoughKarma &&
            searchValue?.length >= 2 &&
            !this.state.choices.some((c) => c.label === searchValue) &&
            !this.state.value.some((v) => v === `_${searchValue.trim()}`)
        );
    }

    onCreateOption(string) {
        const choices = string
            .split(",")
            .map((c) => ({ label: c.trim(), value: `_${c.trim()}` }));
        this.state.choices.push(...choices);
        this.onSelect([...this.state.value, ...choices.map((c) => c.value)]);
    }

    onSelect(values) {
        this.state.value = values;
    }

    async loadChoices(searchString = "") {
        const forumID = document.querySelector("#wrapwrap").dataset.forum_id;
        const choices = await new Promise((resolve) => {
            get(
                `/forum/get_tags?query=${searchString}&limit=${50}&forum_id=${forumID}`,
            ).then((result) => {
                result.forEach((choiceEl) => {
                    choiceEl.value = choiceEl.id;
                    choiceEl.label = choiceEl.name;
                });
                resolve(result);
            });
        });
        this.state.choices = choices;
    }
}
