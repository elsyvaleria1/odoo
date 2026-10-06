/** @odoo-module native */
import { assertType, Component, proxy, t, useProps } from "@odoo/owl";
import { omit, pick } from "@web/core/utils/collections/objects";

export class Toolbar extends Component {
    static template = "html_editor.Toolbar";
    static props = {
        class: t.string().optional(),
        getSelection: t.function(),
        focusEditable: t.function(),
        state: t.object({
            namespace: t.string().optional(),
            buttonGroups: t.array(
                t.object({
                    id: t.string(),
                    buttons: t.array(
                        t.customValidator(t.object(), (button) => {
                            const base = {
                                id: t.string(),
                                description: t.string(),
                                isDisabled: t.boolean(),
                            };
                            if (button.Component) {
                                assertType(
                                    button,
                                    t.strictObject({
                                        ...base,
                                        Component: t.function(),
                                        props: t.object().optional(),
                                    }),
                                );
                            } else {
                                assertType(
                                    button,
                                    t.strictObject({
                                        ...base,
                                        run: t.function(),
                                        icon: t.string().optional(),
                                        text: t.string().optional(),
                                        isActive: t.boolean(),
                                    }),
                                );
                            }
                            return true;
                        }),
                    ),
                }),
            ),
        }),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.state = proxy(this.props.state);
    }

    onButtonClick(button) {
        button.run();
        this.props.focusEditable();
    }
}

export const toolbarButtonProps = {
    title: t.or([t.string(), t.function()]),
    getSelection: t.function(),
    isDisabled: t.boolean(),
};

/** @typedef {import("@html_editor/core/user_command_plugin").UserCommand} UserCommand */
/** @typedef {import("./toolbar_plugin").ToolbarCommandItem} ToolbarCommandItem */
/** @typedef {import("./toolbar_plugin").ToolbarCommandButton} ToolbarCommandButton */

/**
 * @param {UserCommand} userCommand
 * @param {ToolbarCommandItem} toolbarItem
 * @returns {ToolbarCommandButton}
 */
export function composeToolbarButton(userCommand, toolbarItem) {
    const description = toolbarItem.description || userCommand.description;
    return {
        ...pick(userCommand, "icon"),
        ...omit(toolbarItem, "commandId", "commandParams"),
        run: () => userCommand.run(toolbarItem.commandParams),
        isAvailable: (selection) =>
            [userCommand.isAvailable, toolbarItem.isAvailable]
                .filter(Boolean)
                .every((predicate) => predicate(selection)),
        description: description instanceof Function ? description : () => description,
    };
}
