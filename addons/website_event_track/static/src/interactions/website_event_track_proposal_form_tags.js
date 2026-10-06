/** @odoo-module native */
import { Component, proxy, t, useProps } from "@odoo/owl";
import { SelectMenu } from "@web/components/select_menu";
import { rpc } from "@web/core/network";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { Interaction } from "@web/public/interaction";

class WebsiteEventTrackProposalFormTagsWrapper extends Component {
    static template = "website_event_track.WebsiteEventTrackProposalFormTagsWrapper";
    static components = { SelectMenu };
    static props = {
        placeholder: t.string().optional(),
        defaultChoices: t.array().optional(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.state = proxy({
            ...this.props,
            value: [],
        });
    }
    onSelect(item) {
        this.state.value = item;
    }
}

export class WebsiteEventTrackProposalFormTags extends Interaction {
    static selector = ".o_website_event_track_proposal_form_tags";

    async willStart() {
        const choices = await rpc("/event/track_tag/search_read", {
            fields: ["id", "name", "category_id"],
            domain: [["color", "!=", 0]],
        });
        const choicesMap = choices.map(({ id, category_id, name }) => ({
            value: id,
            label: category_id ? `${category_id[1]} : ${name}` : name,
        }));
        this.mountComponent(this.el, WebsiteEventTrackProposalFormTagsWrapper, {
            defaultChoices: choicesMap || [],
            placeholder: _t("Select Categories"),
        });
    }
}

registry
    .category("public.interactions")
    .add(
        "website_event_track.website_event_track_proposal_form_tags",
        WebsiteEventTrackProposalFormTags,
    );
