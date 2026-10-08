/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { deserializeDate, formatDate } from "@web/core/l10n/dates";
import { useService } from "@web/core/utils/hooks";

export class ProjectMilestone extends Component {
    static props = { context: t.object(), milestone: t.object() };
    static template = "project.ProjectMilestone";
    props = useProps(this.constructor.props);

    setup() {
        this.orm = useService("orm");
        this.writing = false;
    }

    get milestone() {
        return this.props.milestone;
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

    async toggleIsReached() {
        if (this.writing) {
            return;
        }
        this.writing = true;
        try {
            Object.assign(
                this.milestone,
                await this.orm.call(this.resModel, "update_is_reached", [
                    [this.milestone.id],
                    !this.milestone.is_reached,
                ]),
            );
        } finally {
            this.writing = false;
        }
    }
}
