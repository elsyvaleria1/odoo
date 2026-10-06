/** @odoo-module native */
import { Component, onWillUpdateProps, proxy, t, useProps } from "@odoo/owl";
import { deserializeDate, formatDate } from "@web/core/l10n/dates";
import { useService } from "@web/core/utils/hooks";

export class ProjectMilestone extends Component {
    static props = { context: t.object(), milestone: t.object() };
    static template = "project.ProjectMilestone";
    props = useProps(this.constructor.props);

    setup() {
        this.orm = useService("orm");
        this.dialog = useService("dialog");
        this.milestone = proxy({ ...this.props.milestone });
        onWillUpdateProps(this.onWillUpdateProps);
    }

    get resModel() {
        return "project.milestone";
    }

    get deadline() {
        if (!this.milestone.date_deadline) {
            return "";
        }
        return formatDate(deserializeDate(this.milestone.date_deadline));
    }

    get colorClass() {
        return this.milestone.is_deadline_exceeded &&
            !this.milestone.can_be_marked_as_done
            ? "text-danger"
            : this.milestone.can_be_marked_as_done
              ? "text-success"
              : "";
    }

    get checkboxIcon() {
        return this.milestone.is_reached
            ? "fa-solid fa-square-check"
            : "fa-regular fa-square";
    }

    onWillUpdateProps(nextProps) {
        if (nextProps.milestone) {
            Object.assign(this.milestone, nextProps.milestone);
        }
    }

    async toggleIsReached() {
        if (!this.write_mutex) {
            this.write_mutex = true;
            try {
                Object.assign(
                    this.milestone,
                    await this.orm.call(this.resModel, "update_is_reached", [
                        [this.milestone.id],
                        !this.milestone.is_reached,
                    ]),
                );
            } finally {
                this.write_mutex = false;
            }
        }
    }
}
