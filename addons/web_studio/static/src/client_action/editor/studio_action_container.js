/** @odoo-module native */
import {
    Component,
    markup,
    onWillStart,
    onWillUnmount,
    onWillUpdateProps,
    t,
    useProps,
    xml,
} from "@odoo/owl";
import { useAppContext } from "@web/core/app_context";
import { rpc } from "@web/core/network";
import { registry } from "@web/core/registry";
import { KeepLast } from "@web/core/utils/concurrency";
import { useEventBus, useService } from "@web/core/utils/hooks";
import { useRender } from "@web/core/utils/render_hooks";
import { resetViewCompilerCache } from "@web/views/view_compiler";
import { ActionContainer } from "@web/webclient/actions";
import { useStudioServiceAsReactive } from "@web_studio/studio_service";

const editorTabRegistry = registry.category("web_studio.editor_tabs");

export class StudioActionContainer extends Component {
    static props = { ...ActionContainer.props, reloadId: t.number() };

    static template = xml`
        <t t-name="web.ActionContainer">
        <div class="o_action_manager">
            <t t-if="this.info.Component" t-component="this.info.Component" className="'o_action'" t-props="this.info.componentProps" t-key="this.info.id"/>
        </div>
        </t>`;
    props = useProps(this.constructor.props);
    render = useRender();

    setup() {
        this.appContext = useAppContext();
        this.bus = useEventBus();
        this.actionService = useService("action");
        this.studio = useStudioServiceAsReactive();
        this.info = {};

        let actionKey = 1;
        const onUiUpdate = ({ detail: info }) => {
            this.info = info;
            actionKey++;
            this.render();
        };
        this.bus.addEventListener("ACTION_MANAGER:UPDATE", onUiUpdate);
        onWillUnmount(() =>
            this.bus.removeEventListener("ACTION_MANAGER:UPDATE", onUiUpdate),
        );

        const doAction = async (action, options) => {
            try {
                await this.actionService.doAction(action, options);
                this.actionKey = actionKey;
            } catch (e) {
                if (action !== "web_studio.action_editor") {
                    this.studio.setParams({ editorTab: "views" });
                }
                throw e;
            }
        };

        onWillStart(async () => {
            const action = await this.getStudioAction();
            this.studioKey = this.studio.requestId;
            doAction(action);
            await Promise.resolve();
        });

        const willUpdateKeepLast = new KeepLast();
        onWillUpdateProps(async () => {
            if (
                this.studio.requestId !== this.studioKey ||
                this.actionKey !== actionKey
            ) {
                const action = await willUpdateKeepLast.add(this.getStudioAction());
                resetViewCompilerCache();
                return new Promise((_resolve) => {
                    const resolve = () => {
                        this.bus.removeEventListener("ACTION_MANAGER:UPDATE", resolve);
                        _resolve();
                    };
                    this.studioKey = this.studio.requestId;
                    doAction(action, {
                        clearBreadcrumbs: true,
                        noEmptyTransition: true,
                    }).finally(() => {
                        this.bus.removeEventListener("ACTION_MANAGER:UPDATE", resolve);
                    });
                    this.bus.addEventListener("ACTION_MANAGER:UPDATE", resolve);
                });
            }
        });
    }
    async getStudioAction() {
        const { editorTab, editedAction, editedReport, editedViewType } = this.studio;
        const tab = editorTabRegistry.get(editorTab);
        if (editorTab === "views") {
            if (
                editedViewType &&
                registry.category("studio_editors").contains(editedViewType)
            ) {
                return "web_studio.view_editor";
            }
            return tab.action;
        }
        if (tab.action) {
            const action = tab.action;
            return action instanceof Function ? action(this.appContext) : action;
        } else if (editorTab === "reports" && editedReport) {
            return "web_studio.report_editor";
        } else {
            const action = await rpc("/web_studio/get_studio_action", {
                action_name: editorTab,
                model: editedAction.res_model,
                view_id: editedAction.view_id && editedAction.view_id[0],
            });
            action.help = action.help && markup(action.help);
            return action;
        }
    }
}
