/** @odoo-module native */
import { HtmlViewer } from "@html_editor/components/html_viewer/html_viewer";
import { READONLY_MAIN_EMBEDDINGS } from "@html_editor/others/embedded_components/embedding_sets";
import {
    Component,
    markup,
    onMounted,
    onWillDestroy,
    onWillStart,
    proxy,
    t,
    useProps,
} from "@odoo/owl";
import { Notebook } from "@web/components/notebook";
import { loadBundle } from "@web/core/assets";
import { browser } from "@web/core/browser/browser";
import { colorScheme } from "@web/core/color_scheme";
import { useDebugMode } from "@web/core/debug/debug_context";
import {
    deserializeDateTime,
    formatDateTime,
    parseISO,
    toISO,
} from "@web/core/l10n/dates";
import { _t } from "@web/core/translation";
import { user } from "@web/core/user";
import { htmlReplaceAll } from "@web/core/utils/dom/html";
import { memoize } from "@web/core/utils/functions";
import { useService } from "@web/core/utils/hooks";
import { Dialog } from "@web/ui/dialog";

export class HistoryDialog extends Component {
    static template = "html_editor.HistoryDialog";
    static components = { Dialog, HtmlViewer, Notebook };
    static props = {
        recordId: t.number(),
        recordModel: t.string(),
        close: t.function(),
        restoreRequested: t.function(),
        historyMetadata: t.array(),
        versionedFieldName: t.string(),
        title: t.any().optional(_t("History")),
        noContentHelper: t.any().optional(markup("")),
        embeddedComponents: t.any().optional([...READONLY_MAIN_EMBEDDINGS]),
    };
    props = useProps(this.constructor.props);

    DEFAULT_AVATAR = "/mail/static/src/img/smiley/avatar.jpg";

    state = proxy({
        revisionsData: [],
        currentView: "content",
        isComparisonSplit: false,
        revisionContent: null,
        revisionComparison: null,
        revisionId: null,
        revisionLoading: true,
        cssMaxHeight: 400,
    });

    setup() {
        this.debug = useDebugMode();
        this.ui = useService("ui");
        this.size = "fullscreen";
        this.title = this.props.title;
        this.orm = useService("orm");
        this.resizeObserver = null;

        onWillStart(async () => {
            let revisionId = -1;
            const revisionData = [];
            for (const metadata of this.props.historyMetadata) {
                revisionData.push({ ...metadata, revision_id: revisionId });
                revisionId = metadata["revision_id"];
            }
            const record = await this.orm.read(
                this.props.recordModel,
                [this.props.recordId],
                ["create_date", "create_uid"],
            );
            revisionData.push({
                revision_id: revisionId,
                create_date: toISO(
                    deserializeDateTime(record[0]["create_date"], { tz: "UTC" }),
                ),
                create_uid: record[0]["create_uid"][0],
                create_user_name: record[0]["create_uid"][1],
            });

            this.state.revisionsData = revisionData;
            this.resizeObserver = new ResizeObserver(this.resize.bind(this));
            this.resizeObserver.observe(document.body);
        });
        onMounted(() => this.init());
        onWillDestroy(() => {
            this.resizeObserver?.disconnect();
        });
    }

    resize() {
        const dialogContainer = document.querySelector(
            ".html-history-dialog-container",
        );
        const computedStyle = getComputedStyle(dialogContainer);
        this.state.cssMaxHeight =
            parseInt(computedStyle.height.replace("px", "")) - 160;
    }

    getConfig(value) {
        return {
            value: this.state[value],
            embeddedComponents: this.props.embeddedComponents,
        };
    }

    async init() {
        if (this.debug) {
            await loadBundle("html_editor.assets_history_diff");
        }
        await this.updateCurrentRevision(this.state.revisionsData[0]["revision_id"]);
        this.resize();
    }

    async updateCurrentRevision(revisionId) {
        if (this.state.revisionId === revisionId) {
            return;
        }
        this.state.revisionLoading = true;
        this.state.revisionId = revisionId;
        this.state.revisionContent = await this.getRevisionContent(revisionId);
        this.state.revisionComparison = await this.getRevisionComparison(revisionId);
        this.state.revisionComparisonSplit =
            await this.getRevisionComparisonSplit(revisionId);
        this.state.revisionLoading = false;
    }

    getRevisionComparison = memoize(
        async function getRevisionComparison(revisionId) {
            if (revisionId === -1) {
                return "";
            }
            const comparison = await this.orm.call(
                this.props.recordModel,
                "html_field_history_get_comparison_at_revision",
                [this.props.recordId, this.props.versionedFieldName, revisionId],
            );
            return this._removeExternalBlockHtml(markup(comparison));
        }.bind(this),
    );

    getRevisionComparisonSplit = memoize(
        async function getRevisionComparisonSplit(revisionId) {
            if (!this.debug || revisionId === -1) {
                return "";
            }
            const unifiedDiffString = await this.orm.call(
                this.props.recordModel,
                "html_field_history_get_unified_diff_at_revision",
                [this.props.recordId, this.props.versionedFieldName, revisionId],
            );
            const scheme = colorScheme.current;
            // eslint-disable-next-line no-undef
            const diffHtml = Diff2Html.html(unifiedDiffString, {
                drawFileList: false,
                matching: "lines",
                outputFormat: "side-by-side",
                colorScheme: scheme,
            });
            return markup(diffHtml);
        }.bind(this),
    );

    getRevisionContent = memoize(
        async function getRevisionContent(revisionId) {
            if (revisionId === -1) {
                const curentContent = await this.orm.read(
                    this.props.recordModel,
                    [this.props.recordId],
                    [this.props.versionedFieldName],
                );
                if (!curentContent || !curentContent.length) {
                    return this.props.noContentHelper;
                }
                return this._removeExternalBlockHtml(
                    markup(curentContent[0][this.props.versionedFieldName]),
                );
            }
            const content = await this.orm.call(
                this.props.recordModel,
                "html_field_history_get_content_at_revision",
                [this.props.recordId, this.props.versionedFieldName, revisionId],
            );
            return this._removeExternalBlockHtml(markup(content));
        }.bind(this),
    );

    async _onRestoreRevisionClick() {
        this.ui.block();
        const restoredContent = await this.getRevisionContent(this.state.revisionId);
        this.props.restoreRequested(restoredContent, this.props.close);
        this.ui.unblock();
    }

    _removeExternalBlockHtml(baseHtml) {
        const filteringRegex = /<[a-z ]+data-embedded="(?:(?!<).)+<\/[a-z]+>/gim;
        const placeholderHtml = markup`<div class="embedded-history-dialog-placeholder">${_t(
            "Dynamic element",
        )}</div>`;
        return htmlReplaceAll(baseHtml, filteringRegex, () => placeholderHtml);
    }

    getRevisionDate(revision) {
        if (!revision || !revision["create_date"]) {
            return "--";
        }
        return formatDateTime(parseISO(revision["create_date"], "UTC"), {
            tz: user.tz,
            showSeconds: false,
        });
    }
    getRevisionClasses(revision) {
        let classesStr = "btn";

        if (
            this.state.revisionId !== -1 &&
            (this.state.revisionId < revision.revision_id ||
                revision.revision_id === -1)
        ) {
            classesStr += " targeted";
        } else if (this.state.revisionId === revision.revision_id) {
            classesStr += " selected";
        }

        return classesStr;
    }
    getRevisionAuthorAvatar(revision) {
        if (!revision || !revision["create_uid"]) {
            return this.DEFAULT_AVATAR;
        }
        return `${browser.location.origin}/web/image?model=res.users&field=avatar_128&id=${revision["create_uid"]}`;
    }

    get currentRevision() {
        const id = this.state?.revisionId || this.state.revisionsData[0]["revision_id"];
        return this.state.revisionsData.find(
            (revision) => revision["revision_id"] === id,
        );
    }
}
