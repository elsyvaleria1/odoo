/** @odoo-module native */
import { ExitSplitToolsDialog } from "@document/owl/components/pdf_exit_dialog/pdf_exit_dialog";
import { PdfGroupName } from "@document/owl/components/pdf_group_name/pdf_group_name";
import {
    makePdfPageStoreData,
    PdfPageStore,
} from "@document/owl/components/pdf_manager/pdf_page_store";
import { PdfPage } from "@document/owl/components/pdf_page/pdf_page";
import { Component, onWillStart, proxy, t, toRaw, useProps } from "@odoo/owl";
import { Dropdown } from "@web/components/dropdown";
import { useDebugMode } from "@web/core/debug/debug_context";
import { makeLogger } from "@web/core/debug/debug_logger";
import { useHotkey } from "@web/core/hotkeys/hotkey_hook";
import { _t } from "@web/core/translation";
import { elementRef } from "@web/core/utils/element_ref";
import { clamp } from "@web/core/utils/format/numbers";
import { uniqueId } from "@web/core/utils/functions";
import { useService } from "@web/core/utils/hooks";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
import { loadPDFJS, pdfjsLib } from "@web/core/utils/pdfjs";
import { useCommand } from "@web/ui/commands";
import { ConfirmationDialog } from "@web/ui/dialog";
import { useActiveElement } from "@web/ui/ui_service";

const log = makeLogger("document.pdf_manager");

/**
 * @param {{x: number, y: number}} a
 * @param {{x: number, y: number}} b
 */
function rectFromCorners(a, b) {
    return {
        left: Math.min(a.x, b.x),
        top: Math.min(a.y, b.y),
        width: Math.abs(a.x - b.x),
        height: Math.abs(a.y - b.y),
    };
}

function rectsOverlap(a, b) {
    return (
        a.left < b.left + b.width &&
        b.left < a.left + a.width &&
        a.top < b.top + b.height &&
        b.top < a.top + a.height
    );
}

const BLANK_PAGE_THRESHOLD = 2500;
const BLANK_PIXEL_FILTER_VALUE = 220;
const NON_LEAVING_MENUS = ["shortcuts", "settings", "support", "documentation"];

export class PdfManager extends Component {
    static components = {
        Dropdown,
        PdfPage,
        PdfGroupName,
    };
    static props = {
        documents: t.array(),
        embeddedActions: t.array().optional([]),
        onProcessDocuments: t.function(),
        close: t.function(),
    };
    static template = "document.component.PdfManager";
    props = useProps(this.constructor.props);

    setup() {
        this.debug = useDebugMode();
        this.ui = useService("ui");
        this.root = elementRef();
        useActiveElement(this.root);
        this.pageViewer = elementRef();
        this.pagePreview = elementRef();
        this.addFileInput = elementRef();
        this.notification = useService("notification");
        this.dialog = useService("dialog");
        this.store = new PdfPageStore(proxy(makePdfPageStoreData()));
        this.state = proxy({
            uploadingLock: false,
            pageCanvases: {},
            viewedPage: undefined,
            viewedPageName: undefined,
            viewedPageIndex: undefined,
            archive: true,
            fileName: "",
            edit: false,
            isSelecting: false,
            selectionRect: { left: 0, top: 0, width: 0, height: 0 },
        });

        this._exitSplitToolsClick = false;
        this._newFiles = {};
        // in the page viewer's content, which scrolls under the pointer
        this._selectionAnchor = { x: 0, y: 0 };
        this._selectionPointer = null;
        this._hasSplitPages = false;
        this._pendingFileUploads = 0;
        this._placementQueue = Promise.resolve();
        this._previewRequest = 0;
        this._splitDocumentIds = new Set();
        this._previewPending = false;
        this._onMouseDown = this._onMouseDown.bind(this);
        this._onMouseUp = this._onMouseUp.bind(this);
        this._onMouseMove = this._onMouseMove.bind(this);
        this._onShiftDown = this._onShiftDown.bind(this);
        this._objectUrls = [];
        this._pdfDocuments = [];
        this._loadingTasks = new Set();
        this._isDestroyed = false;

        onWillStart(async () => {
            await this._loadAssets();
        });

        useLayoutEffect(
            () => {
                const _onOutsideClick = this._onOutsideClick.bind(this);
                if (this.props.documents.length === 1) {
                    this.state.fileName = this._removePdfExtension(
                        this.props.documents[0].name,
                    );
                }
                for (const pdf_document of this.props.documents) {
                    this._addFile(pdf_document.name, {
                        url: `/documents/content/${encodeURIComponent(pdf_document.access_token)}`,
                        documentId: pdf_document.id,
                    });
                }
                document.addEventListener("click", _onOutsideClick, true);
                document.addEventListener("mousedown", this._onMouseDown, true);
                document.addEventListener("mouseup", this._onMouseUp, true);
                document.addEventListener("mousemove", this._onMouseMove, true);
                document.addEventListener("keydown", this._onShiftDown, true);
                return () => {
                    this._isDestroyed = true;
                    for (const loadingTask of this._loadingTasks) {
                        loadingTask.destroy();
                    }
                    this._loadingTasks.clear();
                    document.removeEventListener("click", _onOutsideClick, true);
                    document.removeEventListener("mousedown", this._onMouseDown, true);
                    document.removeEventListener("mouseup", this._onMouseUp, true);
                    document.removeEventListener("mousemove", this._onMouseMove, true);
                    document.removeEventListener("keydown", this._onShiftDown, true);
                    for (const objectUrl of this._objectUrls) {
                        URL.revokeObjectURL(objectUrl);
                    }
                    for (const pdf of this._pdfDocuments) {
                        this._destroyPdf(pdf);
                    }
                    this._objectUrls = [];
                    this._pdfDocuments = [];
                };
            },
            () => [],
        );

        this._setUseCommand(
            _t("Focus previous page"),
            this._focusNextPage.bind(this, "left", false),
            "arrowleft",
            {
                allowRepeat: true,
            },
        );
        this._setUseCommand(
            _t("Focus next page"),
            this._focusNextPage.bind(this, "right", false),
            "arrowright",
            {
                allowRepeat: true,
            },
        );
        this._setUseCommand(
            _t("Focus first page of previous group"),
            this._focusNextGroup.bind(this, "left"),
            "control+ArrowLeft",
        );
        this._setUseCommand(
            _t("Focus first page of next group"),
            this._focusNextGroup.bind(this, "right"),
            "control+ArrowRight",
        );
        this._setUseCommand(
            _t("Select focused page"),
            this._spaceKeySelect.bind(this),
            "control+space",
        );
        this._setUseCommand(
            _t("Select/Deselect all pages"),
            this._selectAll.bind(this),
            "control+a",
        );
        this._setUseCommand(
            _t("Select previous page"),
            this._focusNextPage.bind(this, "left", true),
            "shift+ArrowLeft",
            {
                allowRepeat: true,
            },
        );
        this._setUseCommand(
            _t("Select next page"),
            this._focusNextPage.bind(this, "right", true),
            "shift+ArrowRight",
            {
                allowRepeat: true,
            },
        );
        this._setUseCommand(
            _t("Select previous pages of the group"),
            this._selectUntilSplit.bind(this, "left"),
            "control+shift+ArrowLeft",
        );
        this._setUseCommand(
            _t("Select next pages of the group"),
            this._selectUntilSplit.bind(this, "right"),
            "control+shift+ArrowRight",
        );
        this._setUseCommand(
            _t("Escape Preview/Deselect/Exit"),
            this._onPushExit.bind(this),
            "escape",
        );
        this._setUseCommand(
            _t("Split selected pages"),
            this._splitSelectionHandler.bind(this),
            "control+s",
        );
        this._setUseCommand(
            _t("Split all white pages"),
            this._splitWhitePagesHandler.bind(this),
            "shift+s",
        );
        this._setUseCommand(
            _t("Delete focused or selected pages"),
            this.onArchive.bind(this),
            "alt+backspace",
        );
        useHotkey("ArrowDown", this._focusNextPage.bind(this, "down", false), {
            allowRepeat: true,
        });
        useHotkey("ArrowUp", this._focusNextPage.bind(this, "up", false), {
            allowRepeat: true,
        });
        useHotkey("shift+ArrowDown", this._focusNextPage.bind(this, "down", true), {
            allowRepeat: true,
        });
        useHotkey("shift+ArrowUp", this._focusNextPage.bind(this, "up", true), {
            allowRepeat: true,
        });
        // toggles do not repeat: a held key would flip them back and forth
        useHotkey("enter", this._togglePreviewer.bind(this));
        useHotkey("delete", this.onArchive.bind(this));
    }

    /**
     * @param {String} name
     * @param {Function} callback
     * @param {String} hotkey
     * @param {Object} options
     * @private
     */
    _setUseCommand(name, callback, hotkey, options) {
        useCommand(name, callback, {
            category: "smart_action",
            hotkey: hotkey,
            hotkeyOptions: options,
        });
    }

    /**
     * @return {String[]}
     */
    get selectedPageIds() {
        return this.store.selectedPageIds;
    }
    /**
     * @return {Boolean}
     */
    get isDebugMode() {
        return Boolean(this.debug);
    }
    /**
     * @return {String[]}
     */
    get sortedPagesIds() {
        return this.store.sortedPageIds;
    }

    /**
     * @public
     * @param {String} groupId
     * @param {Boolean} toggle
     */
    onToggleEdit(groupId, toggle) {
        this.state.edit = toggle ? groupId : false;
    }
    /**
     * @public
     * @param {String} groupId
     */
    onClickGroupName(groupId) {
        this.store.toggleGroupSelection(groupId);
        this.store.focusedPage = undefined;
        this.onToggleEdit(groupId, true);
    }
    /**
     * @private
     */
    _computeCardsPerLine() {
        const allPages = [...document.querySelectorAll(".o_documents_pdf_page_frame")];
        if (!allPages.length) {
            return 1;
        }
        const top = allPages[0].getBoundingClientRect().top;
        return allPages.filter((page) => page.getBoundingClientRect().top === top)
            .length;
    }
    /**
     * @private
     */
    _unSelectPages() {
        this.store.unselectAll();
    }
    /**
     * @private
     */
    _splitSelectionHandler() {
        if (this.state.viewedPage) {
            return;
        }
        this.store.toggleSelectionSeparators();
    }
    async _splitWhitePagesHandler() {
        if (this.store.userGrouped) {
            this.dialog.add(ConfirmationDialog, {
                title: _t("Split on blank pages"),
                body: _t(
                    "This will discard the current grouping and rebuild the groups from the blank pages. This cannot be undone.",
                ),
                confirm: () => this._splitWhitePages(),
                cancel: () => {},
            });
            return;
        }
        await this._splitWhitePages();
    }
    /**
     * @private
     */
    async _splitWhitePages() {
        // one at a time: a second request would measure the same pages again
        if (this._splittingOnBlankPages) {
            return;
        }
        this._splittingOnBlankPages = true;
        try {
            await this._detectBlankPages();
            if (this._isDestroyed) {
                return;
            }
            this.store.splitOnBlankPages({
                blankName: _t("Blank Page"),
                subDocName: (count) => _t("sub-doc-%s", count),
            });
        } catch (error) {
            if (!this._isDestroyed) {
                this._displayErrorNotification(error.message || String(error));
            }
        } finally {
            this._splittingOnBlankPages = false;
        }
    }
    /**
     * @private
     * @param {String} name
     * @param {Object} param1
     * @param {number} [param1.documentId]
     * @param {Object} [param1.file]
     * @param {String} [param1.url]
     */
    async _addFile(name, { documentId, file, url }) {
        // a closed splitter frees what it opened once, on unmount: whatever
        // it opened after would never be released
        if (this._isDestroyed) {
            return;
        }
        let objectUrl;
        if (!url) {
            if (!file && !documentId) {
                return;
            }
            url = objectUrl = URL.createObjectURL(file);
            this._objectUrls.push(url);
        }
        const displayName = name;
        this._pendingFileUploads++;
        this.state.uploadingLock = true;
        const fileId = uniqueId("file");
        // files load together but take their place in the order they were
        // added: a small second document does not land above a large first
        const pdfLoaded = this._getPdf(url);
        pdfLoaded.catch(() => {});
        const turn = this._placementQueue;
        let placed;
        let placedPages = false;
        this._placementQueue = new Promise((resolve) => (placed = resolve));
        try {
            await turn;
            const pdf = await pdfLoaded;

            if (file) {
                this._newFiles[fileId] = { type: "file", file };
            } else if (documentId) {
                this._newFiles[fileId] = { type: "document", documentId };
            }
            if (this._newFiles[fileId]) {
                this._newFiles[fileId].pdf = pdf;
                this._newFiles[fileId].objectUrl = objectUrl;
            }
            name = this._removePdfExtension(name || _t("New File"));

            const pageCount = pdf.numPages;
            const { pageIds, newPages } = this.store.createPagesForFile({
                fileId,
                name,
                pageCount,
                groupPerPage: this.props.documents.length <= 1,
            });
            for (const pageId of pageIds) {
                this.state.pageCanvases[pageId] = {};
            }
            this._newFiles[fileId].pageIds = this._newFiles[fileId].selectedPageIds =
                pageIds;
            placedPages = true;
            placed();

            const end = log.perf("loadCanvases");
            await this._loadCanvases({ fileId, newPages, pageCount, pdf });
            end({ name: displayName, pageCount });
        } catch (error) {
            placed();
            // the user removed the file while it loaded: _removeFile released it
            if (placedPages && !this._newFiles[fileId]) {
                return;
            }
            log.logic("addFileFailed", {
                name: displayName,
                error: error?.name,
                destroyed: this._isDestroyed,
            });
            if (this._newFiles[fileId]) {
                // a file whose pages did not all load is dropped whole
                this._removeFile(fileId);
            } else if (objectUrl) {
                URL.revokeObjectURL(objectUrl);
                this._objectUrls = this._objectUrls.filter(
                    (each) => each !== objectUrl,
                );
            }
            if (!this._isDestroyed) {
                this._displayErrorNotification(
                    error?.name === "PasswordException"
                        ? _t(
                              "%s is password protected and cannot be split.",
                              displayName,
                          )
                        : _t("Could not open %s.", displayName),
                );
            }
        } finally {
            this._pendingFileUploads--;
            if (this._pendingFileUploads <= 0) {
                this.state.uploadingLock = false;
            }
        }
    }
    /**
     * @private
     * @param {String} message
     */
    _displayErrorNotification(message) {
        this.notification.add(message, {
            type: "danger",
        });
    }
    /**
     * @private
     * @param {number} number
     */
    _displayNumberCreatedDocuments(number) {
        this.notification.add(_t("%s new document(s) created", number), {
            type: "success",
        });
    }
    /**
     * @private
     * @param {number} number
     */
    _displayNumberDeletedPages(number) {
        this.notification.add(_t("%s page(s) deleted", number), { type: "success" });
    }
    /** The pages a split takes: the selection, or else the focused page. */
    get _pagesToProcess() {
        const selected = this.store.selectedPageIds;
        if (selected.length) {
            return selected;
        }
        return this.store.focusedPage ? [this.store.focusedPage] : [];
    }
    /**
     * @private
     * @param {number} [actionId]
     */
    /**
     * @param {number} [actionId]
     * @returns {Promise<boolean>} whether the split was committed
     */
    async _applyChanges(actionId) {
        // the lock disables the buttons only from the next render
        if (this._applying) {
            return false;
        }
        const processedPageIds = this._pagesToProcess;
        if (!processedPageIds.length) {
            this._displayErrorNotification(_t("No document has been selected"));
            return false;
        }
        const exit = this.store.ignoredPageIds.every((pageId) =>
            processedPageIds.includes(pageId),
        );
        this._applying = true;
        this.state.uploadingLock = true;
        try {
            let documentIds;
            try {
                documentIds = await this._sendChanges(processedPageIds);
            } catch (error) {
                log.logic("splitFailed", { pages: processedPageIds.length });
                this._displayErrorNotification(error.message || String(error));
                return false;
            }
            log.logic("splitCommitted", {
                pages: processedPageIds.length,
                documentIds,
                actionId,
                exit,
            });
            this._displayNumberCreatedDocuments(documentIds.length);
            if (!exit) {
                this._hasSplitPages = true;
                for (const pageId of processedPageIds) {
                    const file = this._newFiles[this.store.getPage(pageId).fileId];
                    if (file?.type === "document") {
                        this._splitDocumentIds.add(file.documentId);
                    }
                }
                for (const pageId of processedPageIds) {
                    this._removePage(pageId, { fromFile: true });
                }
            }
            try {
                await this.props.onProcessDocuments({ documentIds, actionId, exit });
            } catch (error) {
                this._displayErrorNotification(error.message || String(error));
            }
            if (exit) {
                this.props.close();
            }
            return true;
        } finally {
            this._applying = false;
            this.state.uploadingLock = false;
        }
    }

    async _isBlankPage(page, canvas) {
        // the thumbnail's pixels first: extracting a page's text is the
        // worker's work, and a page with ink needs none
        if (!this._hasBlankGraphics(canvas)) {
            return false;
        }
        const pageContent = await page.getTextContent();
        return pageContent.items.length === 0;
    }

    _hasBlankGraphics(canvas) {
        const pixels = canvas
            .getContext("2d")
            .getImageData(0, 0, canvas.width, canvas.height, {
                colorSpace: "display-p3",
            }).data;
        let totalSum = 0;
        for (let i = 0; i < pixels.length; i += 4) {
            for (let channel = 0; channel < 3; channel++) {
                const value = pixels[i + channel];
                if (value < BLANK_PIXEL_FILTER_VALUE) {
                    totalSum += 255 - value;
                    if (totalSum >= BLANK_PAGE_THRESHOLD) {
                        return false;
                    }
                }
            }
        }
        return true;
    }

    /**
     * @private
     * @param {String} url
     * @return {PdfJsObject}
     */
    async _getPdf(url) {
        const loadingTask = this._openPdf(url);
        this._loadingTasks.add(loadingTask);
        try {
            const pdf = await loadingTask.promise;
            this._pdfDocuments.push(pdf);
            return pdf;
        } finally {
            this._loadingTasks.delete(loadingTask);
        }
    }
    /**
     * pdf.js documents have no destroy() of their own: their loading task
     * owns the worker transport
     * @private
     * @param {PdfJsObject} pdf
     */
    _destroyPdf(pdf) {
        pdf.loadingTask.destroy();
    }
    /**
     * @private
     * @param {String} url
     * @returns {{ promise: Promise<PdfJsObject>, destroy: () => void }} the
     *      pdf.js loading task: destroying it rejects a pending load
     */
    _openPdf(url) {
        return pdfjsLib.getDocument(url);
    }
    /**
     * @private
     */
    async _loadAssets() {
        await loadPDFJS();
    }
    /**
     * @private
     * @param {Object} [param0]
     * @param {Object} [param0.newPages]
     * @param {number} [param0.pageCount]
     * @param {PdfjsObject} [param0.pdf]
     */
    async _loadCanvases({ fileId, newPages, pageCount, pdf }) {
        // pages can be deleted while they render, their whole file included
        const fileGone = () => this._isDestroyed || !this._newFiles[fileId];
        for (let pageNumber = 1; pageNumber <= pageCount; pageNumber++) {
            if (fileGone()) {
                break;
            }
            const pageId = newPages[pageNumber];
            if (!this.store.getPage(pageId)) {
                continue;
            }
            const page = await pdf.getPage(pageNumber);
            const canvas = await this._renderCanvas(toRaw(page), {
                width: 160,
                height: 230,
            });
            if (fileGone() || !this.store.getPage(pageId)) {
                continue;
            }
            this.state.pageCanvases[pageId] = { page, canvas };
        }
    }
    /**
     * Blankness costs a text extraction and a pixel scan per page, and only
     * the split on blank pages asks: it is measured then, once per page.
     *
     * @private
     */
    async _detectBlankPages() {
        const end = log.perf("detectBlankPages");
        let measured = 0;
        for (const pageId of this.store.sortedPageIds) {
            if (this._isDestroyed) {
                break;
            }
            const storePage = this.store.getPage(pageId);
            const { page, canvas } = this.state.pageCanvases[pageId] || {};
            if (storePage && storePage.isBlank === undefined && page && canvas) {
                storePage.isBlank = await this._isBlankPage(toRaw(page), canvas);
                measured++;
            }
        }
        end({ measured });
    }
    /**
     * @private
     * @param {Object} page
     * @param {Object} param1
     * @param {number} param1.width
     * @param {number} param1.height
     * @return {DomElement}
     */
    async _renderCanvas(page, { width, height }) {
        const viewPort = page.getViewport({ scale: 1 });
        const isLandscape = viewPort.width > viewPort.height;
        const canvas = document.createElement("canvas");
        canvas.className = "o_documents_pdf_canvas";
        canvas.width = width;
        canvas.height = height;
        const scale = isLandscape
            ? Math.min(canvas.width / viewPort.height, canvas.height / viewPort.width)
            : Math.min(canvas.width / viewPort.width, canvas.height / viewPort.height);
        await page.render({
            canvasContext: canvas.getContext("2d"),
            // getViewport takes an absolute rotation: a landscape page turns
            // a quarter on top of the /Rotate it already carries
            viewport: page.getViewport({
                scale,
                rotation: isLandscape
                    ? (viewPort.rotation + 270) % 360
                    : viewPort.rotation,
            }),
        }).promise;
        // the canvas holds the picture now: pdf.js would otherwise keep the
        // page's operator list and decoded images for the whole session
        page.cleanup();
        return canvas;
    }
    /**
     * @private
     */
    async _sendChanges(processedPageIds) {
        const processed = new Set(processedPageIds);
        // only the local files this split takes pages from are uploaded
        const usedFileIds = new Set(
            processedPageIds.map((pageId) => this.store.getPage(pageId).fileId),
        );
        const fileIds = [];
        const files = [];
        for (const key in this._newFiles) {
            if (this._newFiles[key].type === "file" && usedFileIds.has(key)) {
                files.push(this._newFiles[key].file);
                fileIds.push(key);
            }
        }
        const newFiles = [];
        for (const groupId of this.store.groupIds) {
            const group = this.store.getGroup(groupId);
            const pageIds = group.pageIds.filter((pageId) => processed.has(pageId));
            if (!pageIds.length) {
                continue;
            }
            newFiles.push({
                name: group.name,
                new_pages: pageIds.map((pageId) => {
                    const page = this.store.getPage(pageId);
                    const file = this._newFiles[page.fileId];
                    return {
                        old_file_type: file.type,
                        old_file_index:
                            file.type === "file"
                                ? fileIds.indexOf(page.fileId)
                                : file.documentId,
                        old_page_number: page.localPageNumber,
                    };
                }),
            });
        }
        newFiles.reverse();
        const sourceDocument = this.props.documents[0];
        const data = new FormData();
        data.append("csrf_token", odoo.csrf_token);
        for (const file of files) {
            data.append("ufile", file);
        }
        data.append("new_files", JSON.stringify(newFiles));
        data.append("archive", this.state.archive);
        data.append(
            "vals",
            JSON.stringify({
                folder_id: sourceDocument.folder_id?.id ?? false,
                tag_ids: sourceDocument.tag_ids.currentIds,
                owner_id: sourceDocument.owner_id?.id ?? false,
                partner_id: sourceDocument.partner_id?.id ?? false,
            }),
        );
        const response = await fetch("/documents/pdf_split", {
            method: "post",
            body: data,
        });
        if (!response.ok) {
            throw new Error(_t("PDF split failed (status %s).", response.status));
        }
        return response.json();
    }
    /**
     * @private
     * @param {String} pageId
     * @param {Object} [param1]
     * @param {boolean} [param1.fromFile]
     */
    _removePage(pageId, { fromFile } = {}) {
        const page = this.store.getPage(pageId);
        if (!page) {
            return;
        }
        this.store.removePage(pageId);
        if (fromFile && page.fileId && this._newFiles[page.fileId]) {
            const selectedPageIds = this._newFiles[page.fileId].selectedPageIds;
            this._newFiles[page.fileId].selectedPageIds = selectedPageIds.filter(
                (number) => number !== pageId,
            );
            if (this._newFiles[page.fileId].selectedPageIds.length === 0) {
                this._removeFile(page.fileId);
            } else {
                delete this.state.pageCanvases[pageId];
            }
            page.fileId = false;
        }
    }
    /**
     * @private
     * @param {String} fileId
     */
    _removeFile(fileId) {
        const fileData = this._newFiles[fileId];
        if (!fileData) {
            return;
        }
        for (const pageId of fileData.pageIds || []) {
            delete this.state.pageCanvases[pageId];
            this.store.deletePage(pageId);
        }
        if (fileData.pdf) {
            this._destroyPdf(fileData.pdf);
            this._pdfDocuments = this._pdfDocuments.filter(
                (pdf) => pdf !== fileData.pdf,
            );
        }
        if (fileData.objectUrl) {
            URL.revokeObjectURL(fileData.objectUrl);
            this._objectUrls = this._objectUrls.filter(
                (url) => url !== fileData.objectUrl,
            );
        }
        delete this._newFiles[fileId];
    }
    /**
     * @private
     * @param {String} name
     */
    _removePdfExtension(name) {
        return name.replace(/\.pdf$/gi, "");
    }
    /**
     * @private
     */
    _exitSplitTools(formerTargetCallback = () => {}) {
        this.dialog.add(ExitSplitToolsDialog, {
            hasSplitPages: this._hasSplitPages,
            onDeleteRemainingPages: async () => {
                await this.props.close();
                formerTargetCallback();
            },
            onGatherRemainingPages: async () => {
                // a gather that failed leaves the user where they were
                if (await this._exitByGatheringRemainingPages()) {
                    formerTargetCallback();
                }
            },
            close: () => {},
        });
    }
    /**
     * @private
     */
    /** @returns {Promise<boolean>} whether the remaining pages were saved */
    async _exitByGatheringRemainingPages() {
        const grouping = this.store.snapshot();
        this.store.regroupAll({
            name: this.state.fileName
                ? _t("%s (remaining pages)", this.state.fileName)
                : _t("Remaining Pages"),
            isSelected: true,
        });
        if (await this._applyChanges()) {
            return true;
        }
        this.store.restore(grouping);
        return false;
    }

    /**
     * @private
     */
    _keepFocusedPageInScreen() {
        if (!this.store.focusedPage || !this.pageViewer.el) {
            return;
        }
        const card = document.querySelector(
            `[data-id="${CSS.escape(this.store.focusedPage)}"]`,
        );
        if (!card) {
            return;
        }
        const focusedCardCoordinates = card.getBoundingClientRect();
        const pageViewerCoordinates = this.pageViewer.el.getBoundingClientRect();
        const bottomDifference =
            focusedCardCoordinates.bottom - pageViewerCoordinates.bottom;
        const topDifference = focusedCardCoordinates.top - pageViewerCoordinates.top;
        if (bottomDifference > 0) {
            this.pageViewer.el.scrollBy(0, bottomDifference + 60);
        }
        if (topDifference < 0) {
            this.pageViewer.el.scrollBy(0, topDifference - 10);
        }
    }

    /**
     * @private
     * @param {Event} ev
     */
    _onShiftDown(ev) {
        if (
            ev.repeat ||
            this.ui.activeElement !== this.root.el ||
            document.activeElement.classList.contains("o_pdf_name_input")
        ) {
            return;
        }
        if (
            ev.key === "Shift" &&
            !ev.metaKey &&
            !ev.ctrlKey &&
            !ev.altKey &&
            !this.state.viewedPage &&
            this.store.focusedPage
        ) {
            this.store.toggleSelected(this.store.focusedPage);
        }
    }
    /**
     * @private
     * @param {String} direction
     * @param {Boolean} doSelect
     */
    _focusNextPage(direction, doSelect) {
        if (this.state.viewedPage) {
            if (direction === "left") {
                this.onClickPrevious();
            }
            if (direction === "right") {
                this.onClickNext();
            }
            return;
        }
        this.store.focusNextPage(direction, doSelect, () =>
            this._computeCardsPerLine(),
        );
        this._keepFocusedPageInScreen();
    }
    /**
     * @private
     * @param {String} direction
     */
    _focusNextGroup(direction) {
        if (this.state.viewedPage) {
            return;
        }
        this.store.focusNextGroup(direction);
        this._keepFocusedPageInScreen();
    }
    /**
     * @private
     */
    _togglePreviewer() {
        if (this.store.focusedPage && !this.state.viewedPage) {
            this.onClickPage(this.store.focusedPage);
        }
        if (this.store.focusedPage && this.state.viewedPage) {
            this._onPushExit();
        }
    }
    /**
     * @private
     */
    _spaceKeySelect() {
        if (this.store.focusedPage && !this.state.viewedPage) {
            this.store.toggleSelected(this.store.focusedPage);
        }
    }
    /**
     * @private
     * @param {String} direction
     */
    _selectUntilSplit(direction) {
        if (this.state.viewedPage) {
            return;
        }
        this.store.selectUntilSplit(direction);
    }
    /**
     * @private
     */
    _selectAll() {
        if (this.state.viewedPage) {
            return;
        }
        this.store.toggleSelectAll();
    }
    /**
     * @private
     */
    _onPushExit() {
        if (this.state.viewedPage || this._previewPending) {
            this._closePreview();
            return;
        }
        if (this.selectedPageIds.length) {
            this._unSelectPages();
            return;
        }
        if (this.store.focusedPage) {
            this.store.focusedPage = undefined;
            return;
        }
        this._exitSplitTools();
    }

    /**
     * @private
     * @param {Event} ev
     */
    _onMouseDown(ev) {
        // listened on the document: a popover or a dialog above the manager
        // is not the page area
        if (
            !this.root.el?.contains(ev.target) ||
            ev.target.closest(".o_pdf_page") ||
            ev.target.closest(".o_page_splitter_wrapper") ||
            ev.target.closest(".o_documents_pdf_manager_top_bar") ||
            ev.target.closest(".o_main_navbar") ||
            ev.target.closest(".o_documents_pdf_page_preview") ||
            ev.target.closest(".o_pdf_group_name_block") ||
            ev.button !== 0
        ) {
            return;
        }
        this._selectionAnchor = this._toViewerPoint(ev);
        this._selectionPointer = null;
        this.state.selectionRect = rectFromCorners(
            this._selectionAnchor,
            this._selectionAnchor,
        );
        this.state.isSelecting = true;
        if (!ev.ctrlKey && !ev.metaKey && !ev.shiftKey) {
            if (!this.selectedPageIds.length) {
                this.store.focusedPage = undefined;
            }
            this.state.edit = false;
            this._unSelectPages();
        }
    }
    /**
     * @private
     * @param {Event} ev
     */
    _onMouseMove(ev) {
        if (!this.state.isSelecting) {
            return;
        }
        this.store.focusedPage = false;
        this._selectionPointer = ev;
        this._updateAreaSelection();
    }
    /**
     * The viewer scrolled under a held selection: the pointer now points
     * elsewhere in the pages.
     *
     * @private
     */
    _onViewerScroll() {
        if (this.state.isSelecting && this._selectionPointer) {
            this._updateAreaSelection();
        }
    }
    /**
     * @private
     * @param {{clientX: number, clientY: number}} pointer
     * @returns {{x: number, y: number}}
     */
    _toViewerPoint({ clientX, clientY }) {
        const viewer = this.pageViewer.el;
        const bounds = viewer.getBoundingClientRect();
        return {
            x: clamp(clientX - bounds.left + viewer.scrollLeft, 0, viewer.scrollWidth),
            y: clamp(clientY - bounds.top + viewer.scrollTop, 0, viewer.scrollHeight),
        };
    }
    /**
     * Selects the pages the rectangle from the anchor to the pointer covers,
     * computed rather than read back from the box, which renders later.
     *
     * @private
     */
    _updateAreaSelection() {
        const pointer = this._selectionPointer;
        const rect = rectFromCorners(
            this._selectionAnchor,
            this._toViewerPoint(pointer),
        );
        this.state.selectionRect = rect;
        const viewer = this.pageViewer.el;
        const bounds = viewer.getBoundingClientRect();
        const additive = pointer.metaKey || pointer.ctrlKey || pointer.shiftKey;
        for (const card of viewer.querySelectorAll(".o_pdf_page")) {
            const cardBounds = card.getBoundingClientRect();
            const cardRect = {
                left: cardBounds.left - bounds.left + viewer.scrollLeft,
                top: cardBounds.top - bounds.top + viewer.scrollTop,
                width: cardBounds.width,
                height: cardBounds.height,
            };
            if (rectsOverlap(rect, cardRect)) {
                this.store.setSelected(card.dataset.id, !pointer.shiftKey);
            } else if (!additive) {
                this.store.setSelected(card.dataset.id, false);
            }
        }
    }
    /**
     * @private
     */
    _onMouseUp() {
        this.state.isSelecting = false;
    }
    /**
     * @public
     * @param {number} actionId
     */
    onClickEmbeddedAction(actionId) {
        this._applyChanges(actionId);
    }
    /**
     * @public
     */
    onClickSplit() {
        this._applyChanges();
    }
    /**
     * @public
     * @param {MouseEvent} ev
     */
    onClickArchive(ev) {
        ev.target.blur();
        this.state.archive = !this.state.archive;
    }
    /**
     * @public
     */
    onClickGlobalAdd() {
        this.addFileInput.el.click();
    }
    /**
     * @public
     */
    async onArchive() {
        let pagesToDelete = this.selectedPageIds;
        if (
            pagesToDelete.length === 0 &&
            !this.store.focusedPage &&
            !this.state.viewedPage
        ) {
            this._displayErrorNotification(_t("No document has been selected"));
            return;
        }
        const sortedPagesIds = this.sortedPagesIds;
        let messageInput = _t(
            "Are you sure that you want to delete the selected page(s)",
        );
        let nextFocusedPageId = this.store.focusedPage;
        // a preview deletes the page it shows: the focus may already be on
        // the next one, still rendering
        const shownPage = this.state.viewedPage;
        if (
            shownPage ||
            pagesToDelete.length === 0 ||
            (this.store.focusedPage && !pagesToDelete.includes(this.store.focusedPage))
        ) {
            const pageId = shownPage || this.store.focusedPage;
            pagesToDelete = [pageId];
            messageInput = shownPage
                ? _t("Are you sure that you want to delete this page ?")
                : _t("Are you sure that you want to delete the focused page ?");
            const pageIndex = sortedPagesIds.indexOf(pageId);
            nextFocusedPageId =
                sortedPagesIds[pageIndex + 1] ?? sortedPagesIds[pageIndex - 1];
        }
        this.dialog.add(ConfirmationDialog, {
            body: messageInput,
            confirm: async () => {
                log.logic("deletePages", () => ({
                    pages: pagesToDelete.length,
                    remaining: this.store.numberOfPages - pagesToDelete.length,
                }));
                for (const pageId of pagesToDelete) {
                    this._removePage(pageId, { fromFile: true });
                }
                if (this.store.numberOfPages === 0) {
                    // a document some pages were split from stays as the
                    // split left it (archived or not, as the user chose)
                    await this.props.onProcessDocuments({
                        emptiedDocumentIds: this.props.documents
                            .map((document) => document.id)
                            .filter((id) => !this._splitDocumentIds.has(id)),
                    });
                    await this.props.close();
                }
                this._displayNumberDeletedPages(pagesToDelete.length);
                if (shownPage && nextFocusedPageId) {
                    await this.onClickPage(nextFocusedPageId);
                } else {
                    this._closePreview();
                    this.store.focusedPage = nextFocusedPageId;
                }
            },
            cancel: () => {},
        });
    }
    /**
     * @public
     * @param {MouseEvent} ev
     */
    async onFileInputChange(ev) {
        if (!ev.target.files.length) {
            return;
        }
        this.state.fileName = "";
        const files = ev.target.files;
        for (const file of files) {
            await this._addFile(file.name, { file });
        }
        ev.target.value = null;
    }
    /**
     * @public
     */
    onClickExit() {
        this._exitSplitTools();
    }
    /**
     * @private
     * @param {HTMLElement} target
     * @returns {boolean}
     */
    _isLeavingClick(target) {
        // the small-screen Action menu is a popover, outside this.root
        if (this.root.el?.contains(target) || target.closest(".o_pdf_manager_menu")) {
            return false;
        }
        if (target.closest(".o_burger_menu_content")) {
            return true;
        }
        const menuItem = target.closest(".dropdown-item");
        if (!menuItem && !target.closest(".o_menu_toggle")) {
            return false;
        }
        if (NON_LEAVING_MENUS.includes(menuItem?.dataset.menu)) {
            return false;
        }
        return true;
    }
    /**
     * @private
     * @param {Event} ev
     */
    _onOutsideClick(ev) {
        if (this._exitSplitToolsClick || !this._isLeavingClick(ev.target)) {
            return;
        }
        ev.stopPropagation();
        ev.preventDefault();
        this._exitSplitTools(() => {
            this._exitSplitToolsClick = true;
            ev.target.click();
            this._exitSplitToolsClick = false;
        });
    }
    /**
     * @public
     * @param {String} pageId
     */
    async onClickPage(pageId) {
        this.store.focusedPage = pageId;
        const page = this.state.pageCanvases[pageId]?.page;
        if (!page) {
            return;
        }
        // the page shown is the last one asked for, and none once Escape
        // closed the preview meanwhile (_onPushExit bumps the request)
        const request = ++this._previewRequest;
        this._previewPending = true;
        const ratio = 18 / 13;
        const width = this.pagePreview.el.clientWidth - (30 * window.innerWidth) / 100;
        let canvas;
        try {
            canvas = await this._renderCanvas(toRaw(page), {
                width: width,
                height: width * ratio,
            });
        } finally {
            if (request === this._previewRequest) {
                this._previewPending = false;
            }
        }
        // a newer request, a close, or the page deleted meanwhile
        if (
            request !== this._previewRequest ||
            this._isDestroyed ||
            !this.store.getPage(pageId)
        ) {
            return;
        }
        this.previewCanvas = canvas;
        this.state.viewedPage = pageId;
        const targetGroup = this.store.getGroupOfPage(pageId);
        this.state.viewedPageName =
            targetGroup.name + "-p" + (targetGroup.pageIds.indexOf(pageId) + 1);
        const sortedPagesIds = this.sortedPagesIds;
        this.state.viewedPageIndex = sortedPagesIds.indexOf(pageId);
    }
    /**
     * @public
     */
    async onClickPrevious() {
        if (this.state.viewedPageIndex > 0) {
            await this.onClickPage(this.sortedPagesIds[this.state.viewedPageIndex - 1]);
        }
    }
    /**
     * @public
     */
    async onClickNext() {
        if (this.state.viewedPageIndex < this.store.numberOfPages - 1) {
            await this.onClickPage(this.sortedPagesIds[this.state.viewedPageIndex + 1]);
        }
    }
    /**
     * @public
     * @param {customEvent} ev
     */
    onClickExitPreview(ev) {
        if (
            ev.target.classList.contains("o_documents_pdf_page_preview") ||
            ev.target.closest(".o_close_button")
        ) {
            this._closePreview();
        }
    }
    /**
     * Closes the preview, and any render still on its way to it: the focus
     * stays on the page that was shown.
     */
    _closePreview() {
        this._previewRequest++;
        this._previewPending = false;
        if (this.state.viewedPage) {
            this.store.focusedPage = this.state.viewedPage;
        }
        this.previewCanvas = undefined;
        this.state.viewedPage = undefined;
    }
    /**
     * @public
     * @param {String} pageId
     * @param {Boolean} isRangeSelection
     */
    onSelectClicked(pageId, isRangeSelection) {
        this.store.clickSelect(pageId, { isRangeSelection });
    }
    /**
     * @public
     * @param {String} pageId
     * @param {String} groupId
     */
    onClickPageSeparator(pageId, groupId) {
        this.store.toggleSeparator(pageId, groupId);
    }
    /**
     * @public
     * @param {String} groupId
     * @param {String} name
     */
    onEditName(groupId, name) {
        this.store.renameGroup(groupId, name);
    }
    /**
     * @public
     * @param {String} ev.detail.targetPageId
     * @param {String} ev.detail.pageId
     */
    onPageDrop(targetPageId, pageId) {
        this.store.movePage(pageId, targetPageId);
    }
}
