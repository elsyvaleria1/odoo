from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Self

from odoo import api, models

from . import approval_trace as trace

if TYPE_CHECKING:
    from odoo.addons.web.models.ir_actions_report import RenderedDocument


class IrActionsReport(models.Model):
    _inherit = "ir.actions.report"

    def _check_report_approval(
        self, report_ref: int | str | Any, res_ids: list[int] | int | None
    ) -> models.BaseModel | None:
        if not res_ids:
            return None
        Binding = self.env["approval.binding"]
        if not Binding._enabled():
            return None
        report = self._get_report(report_ref)
        bindings = Binding._bindings_for_action(report.id)
        if not bindings:
            return None
        ids = [res_ids] if isinstance(res_ids, int) else list(res_ids)
        records = self.env[report.model].browse(ids)
        operation = self._get_report_admission(report)
        if set(ids) <= Binding._get_admitted_ids(records, operation):
            return None
        trace.BINDING.event(
            "report_render",
            report=report.id,
            model=report.model,
            records=ids,
            bindings=bindings.ids,
        )
        Binding._gate(records, bindings, report.name, lambda runnable: None)
        return records

    @api.model
    def _get_report_admission(self, report: Self) -> str:
        return f"report:{report.id}"

    def _render_admitted[T](
        self,
        report_ref: int | str | Any,
        res_ids: list[int] | int | None,
        render: Callable[[], T],
    ) -> T:
        records = self._check_report_approval(report_ref, res_ids)
        if records is None:
            return render()
        operation = self._get_report_admission(self._get_report(report_ref))
        return self.env["approval.binding"]._run_admitted(
            records, operation, lambda admitted: render()
        )

    def _render_qweb_pdf_documents(
        self,
        report_ref: int | str | Any,
        res_ids: list[int] | int | None = None,
        data: dict[str, Any] | None = None,
    ) -> tuple[list[RenderedDocument], str]:
        return self._render_admitted(
            report_ref,
            res_ids,
            lambda: super(IrActionsReport, self)._render_qweb_pdf_documents(
                report_ref, res_ids=res_ids, data=data
            ),
        )

    @api.model
    def _render_qweb_html(
        self,
        report_ref: int | str | Any,
        docids: list[int] | int | None,
        data: dict[str, Any] | None = None,
    ) -> tuple[bytes, str]:
        return self._render_admitted(
            report_ref,
            docids,
            lambda: super(IrActionsReport, self)._render_qweb_html(
                report_ref, docids, data=data
            ),
        )

    @api.model
    def _render_qweb_text(
        self,
        report_ref: int | str | Any,
        docids: list[int] | int | None,
        data: dict[str, Any] | None = None,
    ) -> tuple[bytes, str]:
        return self._render_admitted(
            report_ref,
            docids,
            lambda: super(IrActionsReport, self)._render_qweb_text(
                report_ref, docids, data=data
            ),
        )
