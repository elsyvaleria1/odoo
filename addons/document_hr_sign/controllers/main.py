from odoo import Command, http
from odoo.http import request
from odoo.libs.debug_log import DebugLog

from odoo.addons.sign.controllers.main import Sign

_debug = DebugLog(__name__)


class SignContract(Sign):
    @http.route()
    def sign(self, sign_request_id, token, sms_token=False, signature=None, **kwargs):
        """Once a signature request is complete, file its signed documents with
        the employee or the contract version it was sent for."""
        result = super().sign(
            sign_request_id, token, sms_token=sms_token, signature=signature, **kwargs
        )
        # a replayed or refused signature signs nothing: filing again on it
        # made a new set of the signed documents per call to this public route
        if not result.get("success"):
            return result
        request_item = request.env["sign.request.item"]._from_signer_token(token)
        sign_request = request_item.sign_request_id
        if not all(
            state == "completed"
            for state in sign_request.request_item_ids.mapped("state")
        ):
            _debug.logic("sign_documents_skipped", reason="not_completed")
            return result

        employee = (
            request.env["hr.employee"]
            .sudo()
            .with_context(active_test=False)
            .search([("sign_request_ids", "in", sign_request.ids)])
        )
        if employee:
            self._file_signed_documents(
                sign_request, employee, employee, employee.version_id, request_item
            )
        version = (
            request.env["hr.version"]
            .sudo()
            .with_context(active_test=False)
            .search([("sign_request_ids", "in", sign_request.ids)])
            .sorted("date_start", reverse=True)[:1]
        )
        if version:
            self._file_signed_documents(
                sign_request, version.employee_id, version, version, request_item
            )
        return result

    def _file_signed_documents(
        self, sign_request, employee, record, version, request_item
    ):
        # the signed copies, filed in the employee's contracts and linked to
        # the record they were signed for (res_model restricts them to HR)
        if not (
            record.company_id.documents_hr_settings and employee.hr_employee_folder_id
        ):
            return
        sign_request_sudo = sign_request.sudo()
        _debug.pipeline("sign_documents_filed", by=record._name, record=record)
        sign_request_sudo._create_completed_documents()
        partner = employee.partner_id or employee.user_id.partner_id
        owner = (
            employee.user_id
            or employee.search([("partner_id", "=", partner.id)]).user_id
            or version.hr_responsible_id
            or request_item.create_uid
        )
        tag = request.env.ref(
            "document_hr.document_tag_signature_request", raise_if_not_found=False
        )
        request.env["document.document"].sudo().create(
            [
                {
                    "partner_id": partner.id,
                    "owner_id": owner.id,
                    "datas": document.file,
                    "name": f"{sign_request_sudo.display_name}/{document.document_id.name}",
                    "folder_id": employee.hr_employee_contract_folder_id.id,
                    "tag_ids": [Command.link(tag.id)] if tag else [],
                    "res_id": record.id,
                    "res_model": record._name,
                }
                for document in sign_request_sudo.completed_document_ids
            ]
        )
