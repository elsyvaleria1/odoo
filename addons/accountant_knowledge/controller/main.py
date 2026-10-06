import copy
import logging
import re
from io import BytesIO
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, urlparse

from lxml import html
from markupsafe import Markup
from pypdf.annotations import Link as PdfLink
from pypdf.generic import Fit

from odoo import http, tools
from odoo.fields import Domain
from odoo.http import prepare_content_disposition_header, request
from odoo.libs.json import loads as json_loads
from odoo.tools import (
    format_amount,
    format_date,
    format_datetime,
    format_duration,
    format_time,
    html_sanitize,
)
from odoo.tools.image import image_data_uri
from odoo.tools.pdf import BrandedFileWriter, PdfReader, PdfReadError

if TYPE_CHECKING:
    from odoo.orm.models import BaseModel

_logger = logging.getLogger(__name__)


def convert_html_to_pdf(html, footer=False):
    Report = request.env["ir.actions.report"].with_context(page_format="audit_report")
    body = Report._get_html_with_header_footer(html, footer=footer) if footer else html
    content = Report._render_html_to_pdf([body])
    return PdfReader(BytesIO(content))


def is_html_element_empty(root) -> bool:
    return not root.xpath("//*[translate(normalize-space(.), ' ', '') != '']")


def xpath_has_class(class_name) -> str:
    """Return an XPath predicate matching the elements carrying the given class.
    :param str class_name: class name to look for
    :return: XPath predicate expression
    :rtype: str"""
    return f'contains(concat(" ", normalize-space(@class), " "), " {class_name} ")'


def render_placeholder(text, template_variables):
    for to_replace, value in template_variables.items():
        text = text.replace(to_replace, value)
    return text


def get_toc_pdf(headings, offset=0):
    base_url = request.env["ir.qweb"].get_base_url()
    toc_html = request.env["ir.qweb"]._render(
        "accountant_knowledge.audit_report_table_of_content",
        {"base_url": base_url, "headings": headings, "offset": offset},
    )
    return convert_html_to_pdf(toc_html)


def get_attached_pdfs(root):
    domains = []
    for element in root.xpath(
        f'.//*[@data-embedded="file" or {xpath_has_class("o_file_box")}]'
    ):
        if element.get("data-embedded") == "file":
            embedded_props = json_loads(element.get("data-embedded-props"))
            file_data = embedded_props.get("fileData")
            if file_data:
                file_type = file_data.get("type")
                if file_type == "binary":
                    domains.extend(
                        [
                            [
                                (
                                    "mimetype",
                                    "in",
                                    ["application/pdf", "application/pdf;base64"],
                                ),
                                ("id", "=", file_data.get("id")),
                                ("access_token", "=", file_data.get("access_token")),
                            ]
                        ]
                    )
        else:
            for link in element.xpath(f".//*[{xpath_has_class('o_link_readonly')}]"):
                parsed_url = urlparse(link.get("href"))
                match = re.search(
                    r"^\/web\/content\/(?P<ir_attachment_id>[0-9]+)$", parsed_url.path
                )
                if match:
                    url_params = parse_qs(parsed_url.query)
                    domains.extend(
                        [
                            [
                                (
                                    "mimetype",
                                    "in",
                                    ["application/pdf", "application/pdf;base64"],
                                ),
                                ("id", "=", int(match.group("ir_attachment_id"))),
                                (
                                    "access_token",
                                    "=",
                                    url_params.get("access_token", [False])[0],
                                ),
                            ]
                        ]
                    )
    if not domains:
        return
    all_ir_attachments = request.env["ir.attachment"].search(Domain.OR(domains))
    for domain in domains:
        ir_attachments = all_ir_attachments.filtered_domain(domain)
        if ir_attachments:
            yield PdfReader(BytesIO(ir_attachments[0].raw))


def get_account_reports_pdfs(root):
    all_account_report_options = []
    for element in root.xpath('.//*[@data-embedded="accountReport"]'):
        embedded_props = json_loads(element.get("data-embedded-props", "{}"))
        all_account_report_options.append(embedded_props.get("options", {}))

    AccountReport = request.env["report.formula"].with_context(
        exclude_page_footer=True, page_format="audit_report"
    )
    all_account_reports = AccountReport.browse(
        {
            account_report_options["report_id"]
            for account_report_options in all_account_report_options
        }
    )

    reports_by_id = all_account_reports.grouped(lambda report: report.id)
    for account_report_options in all_account_report_options:
        account_report_id = account_report_options["report_id"]
        account_report = reports_by_id.get(
            account_report_id, all_account_reports.browse()
        )
        if account_report:
            result = account_report.dispatch_report_action(
                account_report_options, "export_to_pdf"
            )
            yield PdfReader(BytesIO(result.get("file_content")))


def flatten_outline(outlines, depth=0):
    """Traverse the outlines in title order, flattening the nested heading
    hierarchy PyPDF exposes.
    :param outlines: nested outline structure, nesting one level per heading
        level: ``[{"/Title": "h1", ...}, [{"/Title": "h2", ...}]]``
    :param int depth: depth of ``outlines`` in the hierarchy
    :return: generator of ``(depth, outline)`` tuples
    """
    for outline in outlines:
        if isinstance(outline, list):
            yield from flatten_outline(outline, depth + 1)
        else:
            yield (depth, outline)


def get_links_from_pdf(pdf):
    """Returns a generator that yields all links present in the given PDF."""
    for page_number, page in enumerate(pdf.pages):
        if "/Annots" not in page:
            continue
        for annotation in page["/Annots"]:
            object = annotation.get_object()
            if object["/Subtype"] != "/Link":
                continue
            yield {"page_number": page_number, "object": object}


def remove_all_annotations(page) -> None:
    """Delete all annotations from the given page (i.e: the comments, the links,
    the highlights, the form fields and the markups)."""
    if "/Annots" in page:
        del page["/Annots"]


def render_front_cover_pdf(audit_report: BaseModel) -> PdfReader:
    base_url = request.env["ir.qweb"].get_base_url()
    front_cover_layout_pdf = PdfReader(
        BytesIO(request.env.ref("accountant_knowledge.front_cover_layout").raw)
    )
    front_cover_html = request.env["ir.qweb"]._render(
        "accountant_knowledge.audit_report_front_cover",
        {
            "audit_report": audit_report,
            "base_url": base_url,
            "format_addr": tools.formataddr,
            "format_amount": lambda amount, currency, lang_code=None, trailing_zeroes=True: (
                tools.format_amount(
                    request.env, amount, currency, lang_code, trailing_zeroes
                )
            ),
            "format_date": lambda value, lang_code=None, date_format=False: format_date(
                request.env, value, lang_code, date_format
            ),
            "format_datetime": lambda value, tz=False, dt_format="medium", lang_code=None: (
                format_datetime(request.env, value, tz, dt_format, lang_code)
            ),
            "format_duration": format_duration,
            "format_time": lambda value, tz=False, time_format="medium", lang_code=None: (
                format_time(request.env, value, tz, time_format, lang_code)
            ),
            "image_data_uri": image_data_uri,
        },
    )
    front_cover_pdf = convert_html_to_pdf(front_cover_html)

    writer = BrandedFileWriter()
    for k in range(len(front_cover_pdf.pages)):
        page = copy.deepcopy(front_cover_layout_pdf.pages[0])
        page.merge_page(front_cover_pdf.pages[k])
        writer.add_page(page)

    output_stream = BytesIO()
    writer.write(output_stream)
    return PdfReader(output_stream)


def get_back_cover_pdf():
    return PdfReader(
        BytesIO(request.env.ref("accountant_knowledge.back_cover_layout").raw)
    )


def compute_total_assets(audit_report):
    balance_sheet_report = request.env.ref("account.balance_sheet").with_company(
        audit_report.company_id
    )
    balance_sheet_report_options = balance_sheet_report.get_options(
        {
            "selected_variant_id": balance_sheet_report.id,
            "date": {
                "date_from": str(audit_report.start_date),
                "date_to": str(audit_report.end_date),
                "mode": "range",
                "filter": "custom",
            },
            "rounding_unit": "decimals",
        }
    )
    values = balance_sheet_report._get_expression_values(balance_sheet_report_options)
    total_assets_line = request.env.ref(
        "account.account_financial_report_total_assets0"
    )
    for expression, value in values.items():
        if expression.report_line_id == total_assets_line:
            return value
    return 0


def compute_net_profit_and_total_revenue(audit_report) -> dict:
    profit_and_loss_report = request.env.ref("account.profit_and_loss").with_company(
        audit_report.company_id
    )
    profit_and_loss_report_options = profit_and_loss_report.get_options(
        {
            "selected_variant_id": profit_and_loss_report.id,
            "date": {
                "date_from": str(audit_report.start_date),
                "date_to": str(audit_report.end_date),
                "mode": "range",
                "filter": "custom",
            },
            "rounding_unit": "decimals",
        }
    )
    values = profit_and_loss_report._get_expression_values(
        profit_and_loss_report_options
    )

    net_profit = 0
    total_revenue = 0

    net_profit_report_line = request.env.ref(
        "account.account_financial_report_net_profit0"
    )
    total_revenue_report_line = request.env.ref(
        "account.account_financial_report_revenue0"
    )

    for expression, value in values.items():
        if expression.report_line_id == net_profit_report_line:
            net_profit = value
        elif expression.report_line_id == total_revenue_report_line:
            total_revenue = value

    return {"net_profit": net_profit, "total_revenue": total_revenue}


def get_template_variables(article) -> dict:
    audit_report = article.inherited_audit_report_id
    results = compute_net_profit_and_total_revenue(audit_report)
    return {
        "{{ start of period }}": format_date(request.env, audit_report.start_date),
        "{{ end of period }}": format_date(request.env, audit_report.end_date),
        "{{ company name }}": audit_report.company_id.name,
        "{{ total balance sheet }}": format_amount(
            request.env,
            compute_total_assets(audit_report),
            audit_report.company_id.currency_id,
        ),
        "{{ revenue }}": format_amount(
            request.env,
            results.get("total_revenue", 0),
            audit_report.company_id.currency_id,
        ),
        "{{ net accounting result }}": format_amount(
            request.env,
            results.get("net_profit", 0),
            audit_report.company_id.currency_id,
        ),
    }


class KnowledgeAuditReportController(http.Controller):
    def _get_template_variables(self, article):
        return get_template_variables(article)

    def _get_html_template_variables(self, article) -> dict:
        return {}

    def _render_front_cover_pdf(self, article) -> PdfReader:
        return render_front_cover_pdf(article.inherited_audit_report_id)

    @http.route(
        '/knowledge_accountant/article/<model("knowledge.article"):root_article>/audit_report',
        type="http",
        auth="user",
        methods=["GET"],
    )
    def export_article_to_pdf(
        self, root_article, include_pdf_files, include_child_articles, **kwargs
    ):

        # Lower `report.print_delay` for the duration of the export: this
        # endpoint renders many separate PDF documents, so any per-document
        # delay is paid once per document.

        IrConfigParameterSudo = request.env["ir.config_parameter"].sudo()
        print_delay = IrConfigParameterSudo.get_param("report.print_delay")
        IrConfigParameterSudo.set_param("report.print_delay", 100)

        body_pdfs = []
        headings = []
        root_article_body = html.fragment_fromstring(
            root_article.body, create_parent="div"
        )
        generate_headings = (
            root_article_body.find('.//*[@data-embedded="articleIndex"]') is not None
        )
        page_offset_in_body = 0
        base_url = request.env["ir.qweb"].get_base_url()

        stack = [root_article]
        template_variables = self._get_template_variables(root_article)
        html_template_variables = self._get_html_template_variables(root_article)

        def render_article_body(root, template_variables):
            def render_html_placeholder(element, template_variables):
                for to_replace, value in template_variables.items():
                    if to_replace not in element.text:
                        continue
                    node = html.fragment_fromstring(value, create_parent="div")
                    element.text = element.text.replace(to_replace, "")
                    element.append(node)

            # Replace all the placeholder values:
            for element in root.iter():
                if element.text:
                    element.text = render_placeholder(element.text, template_variables)
                    render_html_placeholder(element, html_template_variables)
                if element.tail:
                    element.tail = render_placeholder(element.tail, template_variables)

            elements = [
                html.tostring(child, encoding="unicode", method="html")
                for child in root.getchildren()
            ]
            return Markup(html_sanitize("".join(elements)))

        while stack:
            article = stack.pop()
            root = html.fragment_fromstring(article.body, create_parent="div")

            # Remove elements with the `d-print-none` class to avoid empty pages:
            for element in root.xpath(f"//*[{xpath_has_class('d-print-none')}]"):
                parent = element.getparent()
                if parent is not None:
                    parent.remove(element)

            article_headings = root.xpath(
                "//*[self::h1 or self::h2 or self::h3][translate(normalize-space(.), ' ', '') != '']"
            )
            article_has_only_one_nonempty_heading = len(
                article_headings
            ) == 1 and not bool(
                root.xpath(
                    "//text()[translate(normalize-space(.), ' ', '') != '' and not(ancestor::h1 or ancestor::h2 or ancestor::h3)]"
                )
            )

            # Append a title page if the article only contains an h1, h2 or h3
            if article_has_only_one_nonempty_heading:
                title_page_html = request.env["ir.qweb"]._render(
                    "accountant_knowledge.audit_report_title_page",
                    {"base_url": base_url, "title": article_headings[0].text},
                )

                title_page_pdf = convert_html_to_pdf(title_page_html)
                if generate_headings:
                    try:
                        for depth, outline in flatten_outline(title_page_pdf.outlines):
                            headings.append(
                                {
                                    "page_offset_in_body": page_offset_in_body,
                                    "depth": depth,
                                    "outline": outline,
                                }
                            )
                    except PdfReadError:
                        # Old pypdf versions cannot read the outline / headers.
                        _logger.warning(
                            "Unable to generate Audit Report heading, please update your PyPDF version."
                        )
                        generate_headings = False

                body_pdfs.append(title_page_pdf)
                page_offset_in_body += len(title_page_pdf.pages)

            # Append the account reports present in the article:
            account_report_pdfs = list(get_account_reports_pdfs(root))
            body_pdfs.extend(account_report_pdfs)
            page_offset_in_body += sum(
                len(account_report_pdf.pages)
                for account_report_pdf in account_report_pdfs
            )

            # Append the article body if not empty:
            if not article_has_only_one_nonempty_heading and not is_html_element_empty(
                root
            ):
                article_body = render_article_body(root, template_variables)
                article_html = request.env["ir.qweb"]._render(
                    "accountant_knowledge.audit_report_page_layout",
                    {"base_url": base_url, "body": article_body},
                )
                article_pdf = convert_html_to_pdf(article_html)

                if generate_headings:
                    try:
                        for depth, outline in flatten_outline(article_pdf.outlines):
                            headings.append(
                                {
                                    "page_offset_in_body": page_offset_in_body,
                                    "depth": depth,
                                    "outline": outline,
                                }
                            )
                    except PdfReadError:
                        # Old pypdf versions cannot read the outline / headers.
                        _logger.warning(
                            "Unable to generate Audit Report heading, please update your PyPDF version."
                        )
                        generate_headings = False

                body_pdfs.append(article_pdf)
                page_offset_in_body += len(article_pdf.pages)

            # Append the pdf attachments present in the article:
            if include_pdf_files == "true":
                attached_pdfs = list(get_attached_pdfs(root))
                body_pdfs.extend(attached_pdfs)
                page_offset_in_body += sum(
                    len(attached_pdf.pages) for attached_pdf in attached_pdfs
                )

            # Append the child articles:
            if include_child_articles == "true":
                stack.extend(
                    article.child_ids.sorted(lambda child: child.sequence, reverse=True)
                )

        front_cover_pdf = self._render_front_cover_pdf(root_article)
        # Create the PDF output:
        writer = BrandedFileWriter()
        writer.append_pages_from_reader(front_cover_pdf)
        back_cover_pdf = get_back_cover_pdf()
        toc_pdf = False
        toc_links = []
        if headings:
            toc_pdf = get_toc_pdf(headings)
            # Regenerate the table of content to update the page numbers:
            toc_pdf = get_toc_pdf(headings, offset=len(toc_pdf.pages))

            toc_links = list(get_links_from_pdf(toc_pdf))

        if toc_pdf:
            writer.append_pages_from_reader(
                toc_pdf, after_page_append=remove_all_annotations
            )
        for body_pdf in body_pdfs:
            writer.append_pages_from_reader(body_pdf)
        writer.append_pages_from_reader(back_cover_pdf)

        toc_pdf_num_pages = len(toc_pdf.pages) if toc_pdf else 0
        # Add the links:
        for link, heading in zip(toc_links, headings, strict=False):
            writer.add_annotation(
                page_number=link["page_number"] + len(front_cover_pdf.pages),
                annotation=PdfLink(
                    rect=link["object"]["/Rect"],
                    target_page_index=heading["outline"]["/Page"]
                    + len(front_cover_pdf.pages)
                    + toc_pdf_num_pages
                    + heading["page_offset_in_body"],
                    fit=Fit.xyz(
                        left=heading["outline"]["/Left"],
                        top=heading["outline"]["/Top"],
                        zoom=heading["outline"]["/Zoom"],
                    ),
                ),
            )

        # Add the outlines:
        writer.set_page_mode("/UseOutlines")

        bookmarks_stack = []
        for heading in headings:
            parent_heading_depth, parent_bookmark = (
                bookmarks_stack[-1] if bookmarks_stack else (0, None)
            )

            while bookmarks_stack and heading["depth"] <= parent_heading_depth:
                bookmarks_stack.pop()
                parent_heading_depth, parent_bookmark = (
                    bookmarks_stack[-1] if bookmarks_stack else (0, None)
                )

            bookmark = writer.add_outline_item(
                title=heading["outline"]["/Title"],
                page_number=heading["outline"]["/Page"]
                + len(front_cover_pdf.pages)
                + toc_pdf_num_pages
                + heading["page_offset_in_body"],
                parent=parent_bookmark,
                color=None,
                bold=False,
                italic=False,
                fit=Fit.xyz(
                    left=heading["outline"]["/Left"],
                    top=heading["outline"]["/Top"],
                    zoom=heading["outline"]["/Zoom"],
                ),
            )

            if heading["depth"] >= parent_heading_depth:
                # Record heading depth to handle skipped levels
                bookmarks_stack.append((heading["depth"], bookmark))

        # Add the page numbers:
        number_of_pages = (
            len(writer.pages) - len(front_cover_pdf.pages) - len(back_cover_pdf.pages)
        )

        empty_pdf_for_page_numbers = convert_html_to_pdf(
            request.env["ir.qweb"]._render(
                "accountant_knowledge.audit_report_empty_document",
                {"number_of_pages": number_of_pages},
            ),
            footer=request.env["ir.qweb"]._render(
                "accountant_knowledge.audit_report_footer"
            ),
        )

        for k in range(number_of_pages):
            page = writer.pages[k + len(front_cover_pdf.pages)]
            page.merge_page(empty_pdf_for_page_numbers.pages[k])

        output_stream = BytesIO()
        writer.write(output_stream)
        pdf_bytes = output_stream.getvalue()

        # Restore the print delay:
        if print_delay:
            IrConfigParameterSudo.set_param("report.print_delay", print_delay)

        return request.prepare_response(
            pdf_bytes,
            headers=[
                (
                    "Content-Disposition",
                    prepare_content_disposition_header(f"{root_article.name}.pdf"),
                ),  # File name
                ("Content-Type", "application/pdf"),
                ("Content-Length", len(pdf_bytes)),
            ],
        )
