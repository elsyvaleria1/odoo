/** @odoo-module native */
import { Component, onWillStart, proxy, t, useProps } from "@odoo/owl";
import { DropdownItem } from "@web/components/dropdown";
import { SelectMenu } from "@web/components/select_menu";
import { KeepLast } from "@web/core/utils/concurrency";
import { useService } from "@web/core/utils/hooks";

export class WebsiteLinksTagsWrapper extends Component {
    static template = "website_links.WebsiteLinksTagsWrapper";
    static components = { SelectMenu, DropdownItem };
    static props = { placeholder: t.string().optional(), model: t.string().optional() };
    props = useProps(this.constructor.props);

    setup() {
        this.orm = useService("orm");
        this.keepLast = new KeepLast();
        this.state = proxy({
            placeholder: this.props.placeholder,
            choices: [],
            value: undefined,
        });
        onWillStart(async () => {
            this.canCreateLinkTracker = await this.orm.call(
                this.props.model,
                "has_access",
                [[], "create"],
            );
            await this.loadChoice();
        });
    }

    showCreateOption(searchValue) {
        return (
            searchValue &&
            !this.state.choices.some((c) => c.label === searchValue) &&
            this.canCreateLinkTracker
        );
    }

    onSelect(value) {
        this.state.value = value;
    }

    async onCreateOption(string) {
        const record = await this.orm.call("mixin.utm", "get_or_create_record", [
            this.props.model,
            string,
        ]);
        const choice = {
            label: record.name,
            value: record.id,
        };
        this.state.choices.push(choice);
        this.onSelect(choice.value);
    }

    loadChoice(searchString = "") {
        return new Promise((resolve, reject) => {
            const limit = 100;
            const searchReadParams = [
                ["id", "name"],
                {
                    limit: limit,
                    order: "name, id desc",
                },
            ];
            const proms = [];
            proms.push(
                this.orm.searchRead(
                    this.props.model,
                    [["name", "=ilike", `${searchString}%`]],
                    ...searchReadParams,
                ),
            );
            proms.push(
                this.orm.searchRead(
                    this.props.model,
                    [["name", "=ilike", `%_${searchString}%`]],
                    ...searchReadParams,
                ),
            );
            this.keepLast
                .add(Promise.all(proms))
                .then(([startingMatches, endingMatches]) => {
                    const formatChoice = (choice) => {
                        choice.value = choice.id;
                        choice.label = choice.name;
                        return choice;
                    };
                    startingMatches.map(formatChoice);

                    if (startingMatches.length < limit) {
                        const startingMatchesId = startingMatches.map(
                            (value) => value.id,
                        );
                        const extraEndingMatches = endingMatches.filter(
                            (value) => !startingMatchesId.includes(value.id),
                        );
                        extraEndingMatches.map(formatChoice);
                        return startingMatches.concat(extraEndingMatches);
                    }
                    return startingMatches;
                })
                .then((result) => {
                    this.state.choices = result;
                    resolve();
                })
                .catch(reject);
        });
    }
}
