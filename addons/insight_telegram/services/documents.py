import logging

from .catalog import NotFound, find

_logger = logging.getLogger(__name__)

MAX_FILES = 5

# Documents filed in Documents, found by the type of document: the words its
# type's name carries, in Spanish and English.
FILED_KINDS = {
    "guarantee": ("garant", "colateral", "guarantee", "collateral"),
    "promissory_note": ("pagar", "promissory"),
    "identification": ("identi", "ine", "identity"),
    "contract": ("contrat", "contract"),
    "guarantee_release": ("liberaci", "release"),
}

# Documents Odoo prints, by the report that prints them and how the record
# is found: a partner for a statement, else the document's reference.
PRINTED_KINDS = {
    # a statement is the Customer Statement accounting report, not a report
    # action: the follow-up letter Odoo prints for a partner is another thing
    "statement": ("res.partner", ()),
    "invoice": ("account.move", ("account.report_invoice_with_payments",)),
    "payment_receipt": (
        "account.payment",
        ("marin.report_payment_receipt", "account.report_payment_receipt"),
    ),
    "sale_order": ("sale.order", ("sale.report_saleorder",)),
    "purchase_order": ("purchase.order", ("purchase.report_purchaseorder",)),
}

KINDS = (*FILED_KINDS, "credit_file", *PRINTED_KINDS)


def collect(env, kind, params):
    """The files a request for documents asks for, as ``(filename, bytes)``.

    :param env: the environment to read and print in; printing writes report
        caches, so it is a read-write environment
    :param str kind: one of KINDS
    :param dict params: the classifier's parameters (partner, reference)
    :return: the files, at most MAX_FILES, and the names of what matched
    :rtype: tuple[list, list]
    """
    if kind in PRINTED_KINDS:
        return _printed(env, kind, params)
    return _filed(env, kind, params)


def _partner(env, params):
    if params.get("partner_id"):
        found = env["res.partner"].browse(int(params["partner_id"])).exists()
        if found:
            return found.commercial_partner_id
    name = (params.get("partner") or "").strip()
    if not name:
        raise NotFound(env._("Tell me whose documents you want: the name."))
    found = find(env, "res.partner", name, ("name", "vat"))
    if not found:
        raise NotFound(env._("I could not find «%(value)s».", value=name))
    return found[:1].commercial_partner_id


def _filed(env, kind, params):
    partner = _partner(env, params)
    if kind == "credit_file" and "credit_document_ids" in partner._fields:
        documents = partner.credit_document_ids
    else:
        documents = env["document.document"].search(
            [("partner_id", "child_of", partner.id), ("type", "!=", "folder")],
            order="id desc",
        )
        words = FILED_KINDS.get(kind)
        if words:
            documents = documents.filtered(lambda document: _is(document, words))
        if kind == "guarantee":
            # a guarantee release names the guarantee it releases: it is not one
            release = FILED_KINDS["guarantee_release"]
            documents = documents.filtered(lambda document: not _is(document, release))
    documents = documents.filtered("attachment_id")
    files = [
        (document.name or "document.pdf", document.attachment_id.raw)
        for document in documents[:MAX_FILES]
    ]
    return [file for file in files if file[1]], documents.mapped("name")


def _is(document, words) -> bool:
    """Whether a document's type or name carries one of `words`."""
    text = f"{document.document_type_id.display_name or ''} {document.name or ''}"
    return any(word in text.lower() for word in words)


STATEMENT_REPORT = "account.customer_statement_report"


def statement_companies(env, partner):
    """The companies where `partner` has open receivable or payable entries,
    else the current one: each has its own statement."""
    lines = env["account.move.line"].search(
        [
            ("partner_id", "child_of", partner.commercial_partner_id.id),
            ("account_type", "in", ("asset_receivable", "liability_payable")),
            ("parent_state", "=", "posted"),
            ("reconciled", "=", False),
        ]
    )
    return lines.company_id.sorted("id") or env.company


def statements(env, partner) -> list:
    """``[(filename, bytes)]``: the Customer Statement of `partner` as Odoo
    exports it to PDF, one per company where it has something open."""
    report = env.ref(STATEMENT_REPORT, raise_if_not_found=False)
    if not report:
        raise NotFound(env._("That document cannot be printed on this database."))
    partner = partner.commercial_partner_id
    companies = statement_companies(env, partner)
    files = []
    for company in companies:
        scoped = env(context={**env.context, "allowed_company_ids": company.ids})
        options = partner.with_env(scoped)._get_partner_account_report_options(
            report.with_env(scoped)
        )
        content = report.with_env(scoped).export_to_pdf(options)["file_content"]
        name = (partner.display_name or "").replace("/", "-")
        suffix = f" - {company.display_name}" if len(companies) > 1 else ""
        files.append((f"{env._('Statement')} - {name}{suffix}.pdf", content))
    return files


def _printed(env, kind, params):
    if kind == "statement":
        partner = _partner(env, params)
        return statements(env, partner), partner.mapped("display_name")
    model, reports = PRINTED_KINDS[kind]
    if model not in env:
        raise NotFound(env._("That document cannot be printed on this database."))
    # the names are report_name values, the template each report prints, not
    # xml ids: an xml id of that name is the template's view, not the report
    report = env["ir.actions.report"].search(
        [("report_name", "in", list(reports)), ("model", "=", model)],
        limit=1,
        order="id",
    )
    if len(reports) > 1 and report:
        # the first name listed is preferred where several are installed
        for name in reports:
            preferred = report.search(
                [("report_name", "=", name), ("model", "=", model)], limit=1
            )
            if preferred:
                report = preferred
                break
    if not report:
        raise NotFound(env._("That document cannot be printed on this database."))
    reference = (params.get("reference") or "").strip()
    domain = [("name", "ilike", reference)] if reference else []
    partner_name = (params.get("partner") or "").strip()
    if partner_name:
        domain.append(("partner_id", "child_of", _partner(env, params).id))
    if not domain:
        raise NotFound(env._("Tell me which one: its number or the partner."))
    if model == "account.move":
        domain.append(("state", "=", "posted"))
    records = env[model].search(domain, order="id desc", limit=MAX_FILES)
    if not records:
        raise NotFound(
            env._("I could not find «%(value)s».", value=reference or partner_name)
        )
    files = []
    for record in records:
        attachment = (
            record.invoice_pdf_report_id
            if model == "account.move" and record.invoice_pdf_report_id
            else None
        )
        if attachment and attachment.raw:
            content = attachment.raw
        else:
            content, _format = env["ir.actions.report"]._render_qweb_pdf(
                report.id, record.ids
            )
        name = (record.display_name or kind).replace("/", "-")
        files.append((f"{name}.pdf", content))
    return files, records.mapped("display_name")


# The report each model's records are sent with once created: Odoo's own
# main print. A model not listed uses the first report its Print menu offers.
MAIN_REPORTS = {
    "purchase.order": ("purchase.report_purchaseorder",),
    "sale.order": ("sale.report_saleorder",),
    "account.move": ("account.report_invoice_with_payments",),
    "account.payment": (
        "marin.report_payment_receipt",
        "account.report_payment_receipt",
    ),
    "stock.picking": ("stock.report_deliveryslip",),
}


def main_report(env, model):
    """The PDF report a record of `model` is printed with, or nothing."""
    Report = env["ir.actions.report"]
    base = [("model", "=", model), ("report_type", "=", "qweb-pdf")]
    for name in MAIN_REPORTS.get(model, ()):
        report = Report.search(base + [("report_name", "=", name)], limit=1)
        if report:
            return report
    return Report.search(
        base + [("binding_model_id", "!=", False)], limit=1, order="id"
    )


def print_records(env, records):
    """``[(filename, bytes)]``: each record printed by its model's main
    report; a model with none, or a report that fails, is left out."""
    report = main_report(env, records._name) if records else None
    if not report:
        return []
    files = []
    for record in records:
        try:
            content, _format = env["ir.actions.report"]._render_qweb_pdf(
                report.id, record.ids
            )
        except Exception:
            _logger.info("insight_telegram could not print %s", record, exc_info=True)
            continue
        name = (record.display_name or report.name).replace("/", "-")
        files.append((f"{name}.pdf", content))
    return files
