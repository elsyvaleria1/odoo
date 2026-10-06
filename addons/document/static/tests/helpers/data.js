import { MOVE_ACCESS_CHECK } from "@document/core/document_service";
import { mailModels } from "@mail/../tests/mail_test_helpers";
import {
    fields,
    getKwArgs,
    makeServerError,
    models,
    serverState,
    webModels,
} from "@web/../tests/web_test_helpers";
import { user } from "@web/core/user";

export class DocumentsDocument extends models.Model {
    _name = "document.document";
    _parent_name = "folder_id";

    access_internal = fields.Selection({
        selection: [
            ["edit", "Editor"],
            ["view", "Viewer"],
            ["none", "None"],
        ],
        default: "edit",
    });
    is_download_blocked = fields.Boolean();
    access_via_link = fields.Selection({
        selection: [
            ["edit", "Editor"],
            ["view", "Viewer"],
            ["none", "None"],
        ],
        default: "none",
    });
    is_access_via_link_hidden = fields.Boolean();
    is_access_restricted = fields.Boolean({ string: "Access Restricted" });

    activity_state = fields.Selection({
        selection: [
            ["overdue", "Overdue"],
            ["today", "Today"],
            ["planned", "Planned"],
        ],
    });
    name = fields.Char();
    thumbnail = fields.Binary();
    favorite_user_ids = fields.Many2many({ relation: "res.users" });
    is_user_favorite = fields.Boolean({ string: "Name" });
    is_folder = fields.Boolean();
    is_multipage = fields.Boolean();

    user_can_move = fields.Boolean({ default: true });
    // the server's answers for the current user, recomputed on every write
    is_locked_by_other = fields.Boolean({ compute: "_compute_capabilities" });
    user_can_trash = fields.Boolean({ compute: "_compute_capabilities" });

    _compute_capabilities() {
        for (const record of this) {
            Object.assign(record, documentCapabilities(record));
        }
    }
    is_editable_attachment = fields.Boolean();
    mimetype = fields.Char();
    partner_id = fields.Many2one({
        string: "Related partner",
        relation: "res.partner",
    });
    owner_id = fields.Many2one({ relation: "res.users" });
    previous_attachment_ids = fields.Many2many({
        string: "History",
        relation: "ir.attachment",
    });
    tag_ids = fields.Many2many({ relation: "document.tag" });
    folder_id = fields.Many2one({ relation: "document.document" });
    user_folder_id = fields.Char({ string: "Parent" });
    res_model = fields.Char({ string: "Model (technical)" });
    attachment_id = fields.Many2one({ relation: "ir.attachment" });
    company_id = fields.Many2one({ relation: "res.company" });
    active = fields.Boolean({ default: true });
    activity_ids = fields.One2many({ relation: "mail.activity" });
    my_activity_date_deadline = fields.Date();
    checksum = fields.Char();
    file_extension = fields.Char();
    thumbnail_status = fields.Selection({
        selection: [
            ["present", "Present"],
            ["error", "Error"],
            ["pending", "Pending"],
            ["client_generated", "Client_Generated"],
            ["restricted", "Inaccessible"],
        ],
    });
    lock_uid = fields.Many2one({ relation: "res.users" });
    message_attachment_count = fields.Integer();
    message_follower_ids = fields.One2many({ relation: "mail.followers" });
    message_ids = fields.One2many({ relation: "mail.message" });
    res_id = fields.Many2oneReference({
        string: "Resource ID",
        model_field: "res_model",
        relation: "res.partner",
    });
    res_name = fields.Char({ string: "Resource Name" });
    res_model_name = fields.Char({ string: "Resource Model Name" });
    type = fields.Selection({
        selection: [
            ["binary", "File"],
            ["url", "Url"],
            ["folder", "Folder"],
        ],
        default: "binary",
    });
    shortcut_document_id = fields.Many2one({ relation: "document.document" });
    url = fields.Char();
    url_preview_image = fields.Char({ string: "URL preview image" });
    file_size = fields.Integer();
    raw = fields.Char();
    access_token = fields.Char();
    user_permission = fields.Selection({
        selection: [
            ["edit", "Editor"],
            ["view", "Viewer"],
            ["none", "None"],
        ],
        default: "edit",
    });
    available_embedded_actions_ids = fields.Many2many({
        string: "Available Actions",
        relation: "ir.embedded.actions",
    });
    alias_id = fields.Many2one({ relation: "mail.alias" });
    alias_domain_id = fields.Many2one({ relation: "mail.alias.domain" });
    alias_name = fields.Char();
    alias_email = fields.Char();
    alias_tag_ids = fields.Many2many({ relation: "document.tag" });
    mail_alias_domain_count = fields.Integer();
    create_activity_type_id = fields.Many2one({ relation: "mail.activity.type" });
    create_activity_user_id = fields.Many2one({ relation: "res.users" });
    description = fields.Char({ string: "Attachment description" });
    last_access_date_group = fields.Selection({
        string: "Last Accessed On",
        selection: [
            ["0_older", "Older"],
            ["1_month", "This Month"],
            ["2_week", "This Week"],
            ["3_day", "Today"],
        ],
        default: "3_day",
    });
    activity_user_id = fields.Many2one({ relation: "res.users" });

    _compute_alias_email() {
        for (const record of this) {
            const [domain] = record.alias_domain_id
                ? this.env["mail.alias.domain"].browse(record.alias_domain_id)
                : [];
            if (domain && record.alias_name) {
                record.alias_email = `${record.alias_name}@${domain.name}`;
            } else {
                record.alias_email = record.alias_name || false;
            }
        }
    }

    get_deletion_delay() {
        return 30;
    }

    get_document_max_upload_limit() {
        return 67000000;
    }

    get_details_panel_res_models() {
        return [
            "res.partner",
            "res.users",
            "mail.activity",
            "mail.activity.type",
            "mail.channel",
            "mail.channel.member",
            "mail.channel.message",
            "mail.message",
            "document.document",
        ];
    }

    action_create_shortcut() {
        return;
    }

    web_search_read() {
        const domain = arguments[0].domain;
        if (domain?.length > 0) {
            const folderLeafIdx = domain.findIndex(
                (leaf) => leaf[0] === "user_folder_id",
            );
            if (folderLeafIdx !== -1) {
                domain.splice(folderLeafIdx, 1, [
                    "user_folder_id",
                    domain[folderLeafIdx][1],
                    domain[folderLeafIdx][2].toString(),
                ]);
            }
        }
        return super.web_search_read(...arguments);
    }

    action_move_folder(folder, target) {
        const { context } = getKwArgs(arguments, "ids", "target", "before_folder_id");
        this._refuse_move_changing_access(folder, Number(target), context);
        const record = this.filter((r) => folder.id === r.id);
        record.folder_id = target;
    }

    /**
     * @override to
     */
    async search_panel_select_range() {
        const result = { parent_field: "user_folder_id" };
        result.values = await this._get_search_panel_specials();
        for (const record of this.search_read(
            [["type", "=", "folder"]],
            [
                "access_token",
                "access_via_link",
                "active",
                "company_id",
                "description",
                "display_name",
                "user_folder_id",
                "is_download_blocked",
                "is_locked_by_other",
                "is_user_favorite",
                "mail_alias_domain_count",
                "owner_id",
                "shortcut_document_id",
                "user_can_trash",
                "user_permission",
                "alias_domain_id",
                "alias_email",
                "alias_name",
                "alias_tag_ids",
                "create_activity_type_id",
                "create_activity_user_id",
                "partner_id",
                "id",
                "is_folder",
                "type",
            ],
        )) {
            if (!isNaN(record.user_folder_id)) {
                record.user_folder_id = Number(record.user_folder_id);
            }
            if (!record.active) {
                record.user_folder_id = "TRASH";
            }
            if (record.alias_tag_ids) {
                record.alias_tag_ids = record.alias_tag_ids.map((id) => {
                    const [tag] = this.env["document.tag"].browse(id);
                    return { id, color: tag.color, display_name: tag.name };
                });
            }
            result.values.push(record);
        }
        return result;
    }

    async _get_search_panel_specials() {
        if (!(await user.hasGroup("base.group_user"))) {
            return [];
        }
        return [
            {
                bold: true,
                childrenIds: [],
                parentId: false,
                user_permission: "view",
                display_name: "Company",
                id: "COMPANY",
                description: "Common roots for all company users.",
            },
            {
                bold: true,
                childrenIds: [],
                parentId: false,
                user_permission: "edit",
                display_name: "My Drive",
                id: "MY",
                description: "Your individual space.",
            },
            {
                bold: true,
                childrenIds: [],
                parentId: false,
                user_permission: "edit",
                display_name: "Shared with me",
                id: "SHARED",
                description: "Additional documents you have access to.",
            },
            {
                bold: true,
                childrenIds: [],
                parentId: false,
                user_permission: "edit",
                display_name: "Recent",
                id: "RECENT",
                description: "Recently accessed documents.",
            },
            {
                bold: true,
                childrenIds: [],
                parentId: false,
                user_permission: "edit",
                display_name: "Trash",
                id: "TRASH",
                description: "Items in trash will be deleted forever after 30 days.",
            },
        ];
    }

    toggle_lock(id) {
        const record = this.browse(id)[0];
        // as the server: a lock is taken for oneself
        record.lock_uid = record.lock_uid ? false : serverState.userId;
        this._compute_capabilities();
    }

    get_documents_actions() {
        return [];
    }

    /**
     * The server's refusal of a checked move changing access (tools.py
     * MoveChangesAccess), on a rule without grants: a document takes the
     * folder's link and, unless restricted, its internal access, and what a
     * moved folder contains follows it; shortcuts keep theirs.
     *
     * @param {number[]} ids
     * @param {number} folderId
     * @param {Object} [context]
     */
    _refuse_move_changing_access(ids, folderId, context) {
        if (!context?.[MOVE_ACCESS_CHECK] || !Number.isInteger(folderId)) {
            return;
        }
        const [folder] = this.browse(folderId);
        const internal = new Set();
        let viaLink = false;
        const counts = { documents: 0, contents: 0 };
        const visit = (document, key) => {
            if (document.shortcut_document_id) {
                return;
            }
            let changed = false;
            if (
                !document.is_access_restricted &&
                document.access_internal !== folder.access_internal
            ) {
                internal.add(folder.access_internal);
                changed = true;
            }
            if (document.access_via_link !== folder.access_via_link) {
                viaLink = folder.access_via_link;
                changed = true;
            }
            counts[key] += changed ? 1 : 0;
            for (const child of this.filter((r) => r.folder_id === document.id)) {
                visit(child, "contents");
            }
        };
        for (const document of this.browse(ids)) {
            visit(document, "documents");
        }
        if (counts.documents || counts.contents) {
            throw makeServerError({
                errorName: "odoo.addons.document.tools.MoveChangesAccess",
                message: "Moving these documents changes who can access them.",
                args: [
                    "Moving these documents changes who can access them.",
                    {
                        access_internal: ["none", "view", "edit"].filter((level) =>
                            internal.has(level),
                        ),
                        access_via_link: viaLink,
                        ...counts,
                    },
                ],
            });
        }
    }

    write(ids, values) {
        const { context } = getKwArgs(arguments, "ids", "vals");
        const folderId = values.folder_id ?? Number(values.user_folder_id);
        this._refuse_move_changing_access(ids, folderId, context);
        return super.write(...arguments);
    }
}

export class DocumentsOperation extends models.Model {
    _name = "wizard.document.document.place.folder";

    operation = fields.Selection({
        selection: [
            ["move", "Move"],
            ["shortcut", "Create shortcuts"],
            ["copy", "Duplicate to"],
            ["add", "Add attachment to Documents"],
        ],
    });
    document_ids = fields.Many2many({ relation: "document.document" });
    attachment_id = fields.Many2one({ relation: "ir.attachment" });

    destination = fields.Char({ default: "MY" });
    display_name = fields.Char({ default: "My Drive" });

    user_permission = fields.Char({
        string: "Destination User Permission",
        default: "edit",
    });
    action_confirm(ids) {
        const { context } = getKwArgs(arguments, "ids");
        const [wizard] = this.browse(ids);
        if (wizard.operation === "move") {
            this.env["document.document"]._refuse_move_changing_access(
                wizard.document_ids,
                Number(wizard.destination),
                context,
            );
        }
        return true;
    }

    get_any_editor_destination() {
        for (const record of this.env["document.document"].search_read(
            [["type", "=", "folder"]],
            ["shortcut_document_id", "type", "user_permission"],
        )) {
            if (
                record.type === "folder" &&
                !record.shortcut_document_id &&
                record.user_permission === "edit"
            ) {
                return [
                    {
                        destination: record.id.toString(),
                        display_name: record.display_name,
                    },
                ];
            }
        }
        return [];
    }
}

export class DocumentsTag extends models.Model {
    _name = "document.tag";

    name = fields.Char({ string: "Tag Name" });
    color = fields.Integer({ default: 1 });
    sequence = fields.Integer();
}

export class DocumentsSharing extends models.Model {
    _name = "wizard.document.document.share";

    access_internal = fields.Selection({
        selection: [
            ["edit", "Editor"],
            ["write_edit", "Editor"],
            ["view", "Viewer"],
            ["write_view", "Viewer"],
            ["none", "None"],
            ["write_none", "None"],
            ["mixed", "Mixed rights"],
        ],
    });
}

export class IrEmbeddedActions extends models.Model {
    _name = "ir.embedded.actions";

    name = fields.Char({ string: "Action Name" });
}

export class MailAlias extends models.Model {
    _name = "mail.alias";

    alias_name = fields.Char({ string: "Alias Name" });
}

export class MailAliasDomain extends models.Model {
    _name = "mail.alias.domain";

    name = fields.Char({ string: "Alias Domain Name" });
}

/**
 * @param {Number} id
 * @param {String} name
 * @param {object?} data
 * @return {{}}
 */
/** Who the mock server answers for: patch `isManager` for a Documents manager. */
export const documentsMockUser = { isManager: false };

/**
 * What the server computes for the current user: a lock held by anyone else
 * stops them, unless a manager, and the trash wants an editor.
 *
 * @param {Object} data
 * @returns {{is_locked_by_other: boolean, user_can_trash: boolean}}
 */
export function documentCapabilities(data) {
    const lockedBy = data.lock_uid?.id ?? data.lock_uid;
    const isLockedByOther =
        !documentsMockUser.isManager &&
        Boolean(lockedBy) &&
        lockedBy !== serverState.userId;
    return {
        is_locked_by_other: isLockedByOther,
        user_can_trash:
            data.active !== false &&
            data.user_permission === "edit" &&
            !isLockedByOther,
    };
}

export function makeDocumentRecordData(id, name, data = {}) {
    const strippedName = name.replace(/\s/g, "");
    const defaultValues = {
        available_embedded_actions_ids: [],
        folder_id: false,
        company_id: false,
        owner_id: false,
        partner_id: false,
        type: "binary",
    };
    const documentType = data.type || defaultValues.type;
    const user_folder_id =
        data.user_folder_id ||
        (data.folder_id
            ? data.folder_id.toString()
            : data.owner_id
              ? data.owner_id === serverState.userId
                  ? "MY"
                  : "SHARED"
              : "COMPANY");
    return {
        ...defaultValues,
        id,
        access_token: `accessToken${strippedName}`,
        is_folder: documentType === "folder",
        name,
        type: documentType,
        user_folder_id,
        ...data,
    };
}

/**
 * @returns {Object}
 */
export function getDocumentsTestServerModelsData(additionalRecords = []) {
    return {
        "res.users": [
            { name: "OdooBot", id: serverState.odoobotId },
            {
                name: serverState.partnerName,
                id: serverState.userId,
                active: true,
                partner_id: serverState.partnerId,
            },
        ],
        "document.document": [
            makeDocumentRecordData(1, "Folder 1", {
                type: "folder",
                user_permission: "edit",
            }),
            ...additionalRecords,
        ],
        "document.tag": [
            {
                id: 1,
                name: "Colorless",
                color: 0,
            },
            {
                id: 2,
                name: "Colorful",
                color: 1,
            },
        ],
        "mail.alias": [
            {
                id: 1,
                alias_name: "alias",
            },
        ],

        "mail.alias.domain": [
            {
                id: 1,
                name: "odoo.com",
            },
            {
                id: 2,
                name: "runbot.odoo.com",
            },
        ],

        "res.company": serverState.companies,
    };
}

export const DocumentsModels = {
    ...mailModels,
    IrEmbeddedActions,
    MailAlias,
    MailAliasDomain,
    ResCompany: webModels.ResCompany,
    DocumentsDocument,
    DocumentsOperation,
    DocumentsTag,
    DocumentsSharing,
};

export function getDocumentsModel(modelName) {
    return Object.values(DocumentsModels).find(
        (model) => model.getModelName() === modelName,
    );
}

export const mimetypeExamplesBase64 = {
    WEBP: "UklGRjoAAABXRUJQVlA4IC4AAAAwAQCdASoBAAEAAUAmJaAAA3AA/u/uY//8s//2W/7LeM///5Bj/dl/pJxGAAAA",
};
