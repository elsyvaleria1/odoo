from .catalog import NotFound, find

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
    "statement": ("res.partner", ("account_followup.report_followup_print_all",)),
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


def _printed(env, kind, params):
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
    if model == "res.partner":
        records = _partner(env, params)
    else:
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
