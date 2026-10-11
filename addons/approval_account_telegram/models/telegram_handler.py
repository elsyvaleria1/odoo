import base64
import logging
import math
import re
from datetime import datetime

from odoo import fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.libs.datetime import timezone
from odoo.libs.json import dumps as json_dumps
from odoo.tools.translate import LazyTranslate

from odoo.addons.telegram.tools import format as tg
from odoo.addons.telegram.tools import keyboard as kb
from odoo.addons.telegram.tools.dispatch import (
    TelegramCommand,
    log_command_execution,
    translation_env,
)

_logger = logging.getLogger(__name__)
_lt = LazyTranslate(__name__)

DEFAULT_TZ = "America/Mexico_City"


def _localize_strict(naive_dt, zone):
    localized = naive_dt.replace(tzinfo=zone)
    if localized.utcoffset() != localized.replace(fold=1).utcoffset():
        msg = f"Local time {naive_dt} is ambiguous or does not exist in {zone}"
        raise ValueError(msg)
    return localized


CFDI_MAP = {
    "g01": "adquisicion de mercancias",
    "g03": "gastos en general",
}
CFDI_NAME_MAP = {v: k for k, v in CFDI_MAP.items()}

_INVISIBLE_CHARS = dict.fromkeys(map(ord, "\ufeff\u200b\u200c\u200d\u2060\u180e"), None)
_INVISIBLE_CHARS.update(dict.fromkeys((0x00A0, 0x2007, 0x202F), " "))


def _strip_invisible(text):
    return (text or "").translate(_INVISIBLE_CHARS)


PROOF_MAX_BYTES = 20 * 1024 * 1024
PROOF_EXTENSIONS = {"image/jpeg": ".jpg", "application/pdf": ".pdf"}

_CALLBACK_DATA = (
    "payment_confirm",
    "payment_cancel",
    "especie_confirm",
    "especie_cancel",
)


class TelegramHandlerApprovalAccount(models.AbstractModel):
    _name = "telegram.handler.approval_account"
    _inherit = "mixin.telegram.handler"
    _description = "Telegram: Payment Approvals"
    _telegram_intake_priority = 100

    def _telegram_commands(self) -> dict:
        return {
            "/pago": TelegramCommand(
                "_handle_payment_command",
                "internal",
                starts_flow=True,
                access=("approval.request", "create"),
                description=_lt("Record a payment for approval"),
                company="choose",
            ),
            "/especie": TelegramCommand(
                "_handle_especie_command",
                "internal",
                starts_flow=True,
                access=("approval.request", "create"),
                description=_lt("Record a payment in kind for approval"),
                company="choose",
            ),
        }

    def _telegram_callback_prefixes(self):
        return _CALLBACK_DATA

    def _telegram_flow_label(self, bot, chat):
        if (self._flow_step(chat) or "").startswith("especie_"):
            return self._tr(bot, chat)._("a payment in kind")
        return self._tr(bot, chat)._("a payment record")

    def _on_message(self, bot, chat, message, partner, internal_user):
        step = self._flow_step(chat)
        if step == "payment_details":
            self._process_payment_details(bot, chat, message, internal_user)
        elif step == "payment_proof":
            if message.get("photo"):
                self._handle_payment_proof_file(
                    bot, chat, message, internal_user, is_photo=True
                )
            elif message.get("document"):
                document = message["document"]
                if document.get("mime_type") == "application/pdf":
                    self._handle_payment_proof_file(
                        bot, chat, message, internal_user, is_photo=False
                    )
                else:
                    bot.send_message(
                        chat.chat_id,
                        translation_env(bot, chat)._(
                            "Invalid document type. Please send an image "
                            "(JPEG/PNG) or a PDF."
                        ),
                    )
            else:
                bot.send_message(
                    chat.chat_id,
                    translation_env(bot, chat)._(
                        "Please send an image (JPEG/PNG) or a PDF."
                    ),
                )
        elif step == "especie_details":
            self._process_especie_details(bot, chat, message, internal_user)
        elif step == "especie_proof":
            if message.get("photo"):
                self._handle_especie_proof_file(
                    bot, chat, message, internal_user, is_photo=True
                )
            elif message.get("document"):
                document = message["document"]
                if document.get("mime_type") == "application/pdf":
                    self._handle_especie_proof_file(
                        bot, chat, message, internal_user, is_photo=False
                    )
                else:
                    bot.send_message(
                        chat.chat_id,
                        translation_env(bot, chat)._(
                            "Invalid document type. Please send an image "
                            "(JPEG/PNG) or a PDF."
                        ),
                    )
            else:
                bot.send_message(
                    chat.chat_id,
                    translation_env(bot, chat)._(
                        "Please send an image (JPEG/PNG) or a PDF of the asset."
                    ),
                )
        else:
            return False
        return True

    def _on_callback(self, bot, chat, callback_query, partner, internal_user):
        data = callback_query.get("data")
        step = self._flow_step(chat)
        if step == "payment_confirm":
            if data == "payment_confirm":
                self._confirm_payment_approval(bot, chat, internal_user)
                return True
            if data == "payment_cancel":
                self._flow_end(chat)
                bot.send_message(
                    chat.chat_id,
                    translation_env(bot, chat)._("Operation cancelled."),
                )
                return True
        elif step == "especie_confirm":
            if data == "especie_confirm":
                self._confirm_especie_approval(bot, chat, internal_user)
                return True
            if data == "especie_cancel":
                self._flow_end(chat)
                bot.send_message(
                    chat.chat_id,
                    translation_env(bot, chat)._("Operation cancelled."),
                )
                return True
        return False

    def _get_help_sections(self, bot, partner, internal_user, chat=None):
        sections = []
        if self._offers_command(bot, chat, "/pago", partner, internal_user):
            tr_env = translation_env(bot, chat)
            existing = tr_env._("Name (or part of the name) of an existing customer.")
            pago_cmds = [
                tr_env._("%(command)s - Start recording a payment.")
                % {"command": tg.bold("/pago")},
                tr_env._(
                    "After sending the command, the bot will ask you to send the "
                    "payment details in a single message, one value per line, in "
                    "this order:"
                ),
                "",
                f"1. {tg.bold(tr_env._('Billed to'))}: {tg.escape(existing)}",
                tr_env._("2. %(label)s: %(a)s or %(b)s.")
                % {
                    "label": tg.bold(tr_env._("Product category")),
                    "a": tg.code("Agroquimicos"),
                    "b": tg.code("Papas"),
                },
                tr_env._("3. %(label)s: %(a)s or %(b)s.")
                % {
                    "label": tg.bold(tr_env._("CFDI use")),
                    "a": tg.code("Adquisicion de mercancias"),
                    "b": tg.code("Gastos en general"),
                },
                tr_env._("4. %(label)s: %(a)s, %(b)s, %(c)s, %(d)s, %(e)s.")
                % {
                    "label": tg.bold(tr_env._("Payment method")),
                    "a": tg.code("Transferencia"),
                    "b": tg.code("Efectivo"),
                    "c": tg.code("TC"),
                    "d": tg.code("TD"),
                    "e": tg.code("Cheque"),
                },
                tr_env._("5. %(label)s: %(a)s, %(b)s or %(c)s.")
                % {
                    "label": tg.bold(tr_env._("Company")),
                    "a": tg.code("LMMR"),
                    "b": tg.code("LMMG"),
                    "c": tg.code("N/A"),
                },
                f"6. {tg.bold(tr_env._('Payment applied to'))}: {tg.escape(existing)}",
                tr_env._("7. %(label)s: In %(format)s format.")
                % {
                    "label": tg.bold(tr_env._("Payment date")),
                    "format": tg.code("AAAA-MM-DD"),
                },
                tr_env._("8. %(label)s: Numeric amount (e.g. %(example)s).")
                % {
                    "label": tg.bold(tr_env._("Amount")),
                    "example": tg.code("1500.50"),
                },
                "",
                tr_env._("%(command)s - Cancel the payment being recorded.")
                % {"command": tg.bold("/cancelar")},
            ]
            sections.append((tr_env._("Payment Commands"), pago_cmds))

        if self._offers_command(bot, chat, "/especie", partner, internal_user):
            tr_env = translation_env(bot, chat)
            existing = tr_env._("Name (or part of the name) of an existing customer.")
            especie_cmds = [
                tr_env._("%(command)s - Start recording a payment in kind.")
                % {"command": tg.bold("/especie")},
                tr_env._(
                    "After sending the command, the bot will ask you to send the "
                    "collection details in a single message, one value per line, "
                    "in this order:"
                ),
                "",
                f"1. {tg.bold(tr_env._('Billed to'))}: {tg.escape(existing)}",
                tr_env._("2. %(label)s: %(a)s.")
                % {
                    "label": tg.bold(tr_env._("Product category")),
                    "a": tg.code("Vehiculos"),
                },
                f"3. {tg.bold(tr_env._('Payment applied to'))}: {tg.escape(existing)}",
                tr_env._("4. %(label)s: In %(format)s format.")
                % {
                    "label": tg.bold(tr_env._("Date")),
                    "format": tg.code("AAAA-MM-DD"),
                },
                tr_env._("5. %(label)s: Numeric amount (e.g. %(example)s).")
                % {
                    "label": tg.bold(tr_env._("Amount")),
                    "example": tg.code("1500.50"),
                },
                tr_env._("6. %(label)s: Internal product number (e.g. %(example)s).")
                % {
                    "label": tg.bold(tr_env._("Product reference")),
                    "example": tg.code("174"),
                },
                "",
                tr_env._(
                    "You will then be asked for a photo or PDF of the asset as "
                    "evidence."
                ),
                "",
                tr_env._("%(command)s - Cancel the payment in kind being recorded.")
                % {"command": tg.bold("/cancelar")},
            ]
            sections.append((tr_env._("Payment in Kind Commands"), especie_cmds))

        return sections

    @log_command_execution
    def _handle_payment_command(
        self,
        bot,
        chat,
        args,
        partner=False,
        internal_user=False,
    ) -> None:
        self._flow_start(chat, "payment_details")
        bot.send_message(
            chat.chat_id,
            (
                translation_env(bot, chat)._(
                    "Please send the payment details on 8 separate lines, in the "
                    "format shown in /ayuda.\n\nYou can use /cancelar at any "
                    "time to stop this operation."
                )
            ),
        )

    def _normalize_string(self, string):
        string = _strip_invisible(string).strip().lower()
        replacements = str.maketrans("áéíóú", "aeiou")
        return string.translate(replacements)

    def _get_partner_or_error(
        self, internal_user, partner_name, error_prefix, env=None
    ) -> tuple:
        try:
            partner_model = internal_user.env["res.partner"].with_user(internal_user)
            partners = partner_model.search([("name", "=ilike", partner_name)])
            if not partners:
                partners = partner_model.search([("name", "ilike", partner_name)])
            if not partners:
                return (
                    None,
                    (env or internal_user.env)._(
                        "%(field)s: No customer matched '%(name)s'."
                    )
                    % {"field": error_prefix, "name": partner_name},
                )
            if len(partners) > 1:
                return None, (env or internal_user.env)._(
                    "%(field)s: Several customers matched '%(name)s': %(found)s. "
                    "Please be more specific."
                ) % {
                    "field": error_prefix,
                    "name": partner_name,
                    "found": ", ".join(p.name for p in partners[:5]),
                }
            return partners, None
        except AccessError:
            _logger.warning(
                "AccessError while searching for partner '%s' for user %s.",
                partner_name,
                internal_user.login,
            )
            return (
                None,
                (env or internal_user.env)._(
                    "You do not have permission to search customers. Contact an "
                    "administrator."
                ),
            )

    def _resolve_choice_error(self, value, valid_options, error_msg):
        if self._normalize_string(value) not in valid_options:
            return error_msg
        return None

    def _resolve_cfdi_use(self, cfdi_input) -> tuple:
        normalized_input = self._normalize_string(cfdi_input)

        if normalized_input in CFDI_MAP:
            code = normalized_input
            name = CFDI_MAP[code]
            return name, code

        if normalized_input in CFDI_NAME_MAP:
            name = normalized_input
            code = CFDI_NAME_MAP[name]
            return name, code

        return None, None

    def _get_date_or_error(self, date_str, env) -> tuple:
        try:
            return datetime.strptime(date_str, "%Y-%m-%d").date(), None
        except ValueError:
            return (
                None,
                env._("The date format is wrong ('%(value)s'). Use AAAA-MM-DD.")
                % {"value": date_str},
            )

    def _get_amount_or_error(self, amount_str, env) -> tuple:
        try:
            amount = float(amount_str)
        except ValueError:
            return (
                None,
                env._("The amount '%(value)s' is not a valid number.")
                % {"value": amount_str},
            )
        if not math.isfinite(amount) or amount <= 0:
            return (
                None,
                env._("The amount '%(value)s' must be greater than zero.")
                % {"value": amount_str},
            )
        return amount, None

    def _process_payment_details(self, bot, chat, message, internal_user) -> None:
        lines = _strip_invisible(message.get("text", "")).strip().split("\n")
        if len(lines) != 8:
            bot.send_message(
                chat.chat_id,
                translation_env(bot, chat)._(
                    "Error: 8 lines were expected, but %(count)s were received. "
                    "Please send all the values in a single message, one per line. "
                    "Use /ayuda to see the exact format."
                )
                % {"count": len(lines)},
            )
            return

        (
            p_fx_name,
            category,
            cfdi,
            method,
            company,
            p_cn_name,
            date_str,
            amount_str,
        ) = (line.strip() for line in lines)
        tr_env = translation_env(bot, chat)
        errors = []

        partner_fx, err = self._get_partner_or_error(
            internal_user, p_fx_name, tr_env._("Billed to"), tr_env
        )
        if err:
            errors.append(err)

        partner_cn, err = self._get_partner_or_error(
            internal_user, p_cn_name, tr_env._("Payment applied to"), tr_env
        )
        if err:
            errors.append(err)

        err = self._resolve_choice_error(
            category,
            ["agroquimicos", "papas"],
            tr_env._(
                "Invalid product category: '%(value)s'. Options: Agroquimicos, Papas."
            )
            % {"value": category},
        )
        if err:
            errors.append(err)

        cfdi_name, cfdi_code = self._resolve_cfdi_use(cfdi)
        if not cfdi_name:
            errors.append(
                tr_env._(
                    "Invalid CFDI use: '%(value)s'. Options: Adquisicion de "
                    "mercancias (G01), Gastos en general (G03)."
                )
                % {"value": cfdi}
            )

        err = self._resolve_choice_error(
            method,
            ["transferencia", "efectivo", "tc", "td", "cheque"],
            tr_env._(
                "Invalid payment method: '%(value)s'. Options: Transferencia, "
                "Efectivo, TC, TD, Cheque."
            )
            % {"value": method},
        )
        if err:
            errors.append(err)

        err = self._resolve_choice_error(
            company,
            ["lmmr", "lmmg", "n/a"],
            tr_env._("Invalid company: '%(value)s'. Options: LMMR, LMMG, N/A.")
            % {"value": company},
        )
        if err:
            errors.append(err)

        payment_date, err = self._get_date_or_error(date_str, tr_env)
        if err:
            errors.append(err)

        amount, err = self._get_amount_or_error(amount_str, tr_env)
        if err:
            errors.append(err)

        if errors:
            bot.send_message(
                chat.chat_id,
                tr_env._("The following errors were found:\n\n%(errors)s")
                % {"errors": "\n".join(f"- {tg.escape(e)}" for e in errors)},
            )
            return

        pending_data = {
            "partner_fx_id": partner_fx.id,
            "partner_fx_name": partner_fx.name,
            "product_category": self._normalize_string(category).upper(),
            "cfdi_use": cfdi_name.upper(),
            "cfdi_use_code": cfdi_code.upper(),
            "payment_method": self._normalize_string(method).upper(),
            "company": self._normalize_string(company).upper(),
            "partner_cn_id": partner_cn.id,
            "partner_cn_name": partner_cn.name,
            "date": payment_date.strftime("%Y-%m-%d"),
            "amount": amount,
        }
        chat._flow_advance("payment_proof", pending_data)
        bot.send_message(
            chat.chat_id,
            translation_env(bot, chat)._(
                "Data validated. Please now send the payment receipt (image or PDF)."
            ),
        )

    def _handle_payment_proof_file(
        self, bot, chat, message, internal_user, is_photo
    ) -> None:
        if is_photo:
            file_id = message["photo"][-1]["file_id"]
            file_mimetype = "image/jpeg"
        else:
            file_id = message["document"]["file_id"]
            file_mimetype = "application/pdf"
            if (message["document"].get("file_size") or 0) > PROOF_MAX_BYTES:
                bot.send_message(
                    chat.chat_id,
                    translation_env(bot, chat)._(
                        "The file is larger than 20 MB. Send a smaller photo or PDF."
                    ),
                )
                return

        file_content = bot.get_file_content(file_id)
        if not file_content:
            bot.send_message(
                chat.chat_id,
                translation_env(bot, chat)._(
                    "Error downloading the file. Please try again."
                ),
            )
            return

        pending_data = self._flow_data(chat)
        pending_data["file_b64"] = base64.b64encode(file_content).decode("ascii")
        pending_data["file_mimetype"] = file_mimetype

        chat._flow_advance("payment_confirm", pending_data)

        tr_env = translation_env(bot, chat)
        summary_text = "\n".join(
            [
                tr_env._("Please confirm the data to create the request:"),
                "",
                *(
                    f"- {tg.bold(label)}: {tg.escape(value)}"
                    for label, value in (
                        (tr_env._("Billed to"), pending_data["partner_fx_name"]),
                        (
                            tr_env._("Product category"),
                            pending_data["product_category"],
                        ),
                        (tr_env._("CFDI use"), pending_data["cfdi_use"]),
                        (tr_env._("Payment method"), pending_data["payment_method"]),
                        (tr_env._("Company"), pending_data["company"]),
                        (
                            tr_env._("Payment applied to"),
                            pending_data["partner_cn_name"],
                        ),
                        (tr_env._("Date"), pending_data["date"]),
                        (tr_env._("Amount"), f"${pending_data['amount']:,.2f}"),
                        (tr_env._("Receipt"), tr_env._("(File received)")),
                    )
                ),
            ]
        )
        bot.send_message(
            chat.chat_id,
            summary_text,
            reply_markup=kb.confirm_cancel(
                tr_env._("1. Confirm"),
                "payment_confirm",
                tr_env._("2. Cancel"),
                "payment_cancel",
            ),
        )

    @staticmethod
    def _intake_category(bot, intake):
        return bot.env["approval.category"]._get_telegram_intake_category(
            intake, bot._acting_company()
        )

    def _confirm_payment_approval(self, bot, chat, internal_user) -> None:
        category = self._intake_category(bot, "payment")
        if not category:
            bot.send_message(
                chat.chat_id,
                translation_env(bot, chat)._(
                    "Error: %(company)s has no approval category for payments "
                    "recorded with /pago."
                )
                % {"company": bot._acting_company().name},
            )
            self._flow_end(chat)
            return

        if not internal_user:
            bot.send_message(
                chat.chat_id,
                translation_env(bot, chat)._(
                    "Your Telegram account is not linked to an internal user. "
                    "Contact IT to fix it."
                ),
            )
            self._flow_end(chat)
            return

        data = self._flow_data(chat)

        telegram_data = data.copy()
        telegram_data.pop("file_b64", None)
        telegram_data.pop("file_mimetype", None)

        try:
            date_str = data["date"]
            naive_dt = datetime.strptime(date_str, "%Y-%m-%d").replace(hour=12)
            mexico_tz = timezone(DEFAULT_TZ)
            localized_dt = _localize_strict(naive_dt, mexico_tz)
            user_env = (
                bot.with_user(internal_user)
                .with_context(allowed_company_ids=[bot._acting_company().id])
                .env
            )

            approval_vals = {
                "category_id": category.id,
                "request_owner_id": internal_user.id,
                "company_id": bot._acting_company().id,
                "partner_id": data["partner_fx_id"],
                "date": fields.Datetime.to_string(localized_dt),
                "amount": data["amount"],
                "telegram_data": telegram_data,
                "reason": user_env[
                    "telegram.payment.report.log"
                ]._format_payment_details_html(telegram_data),
            }

            with user_env.cr.savepoint():
                approval = user_env["approval.request"].create(approval_vals)

                safe_name = re.sub(r"[^a-zA-Z0-9]", "_", data["partner_cn_name"])
                attachment_name = (
                    f"comprobante_{safe_name}_{approval.id}"
                    f"{PROOF_EXTENSIONS.get(data.get('file_mimetype'), '')}"
                )
                attachment = user_env["ir.attachment"].create(
                    {
                        "name": attachment_name,
                        "datas": data["file_b64"],
                        "res_model": "approval.request",
                        "res_id": approval.id,
                        "company_id": approval.company_id.id,
                        "type": "binary",
                        "mimetype": data.get(
                            "file_mimetype", "application/octet-stream"
                        ),
                    }
                )

                approval.message_post(
                    body=approval.env._("Proof of payment attached from Telegram."),
                    attachment_ids=[attachment.id],
                )

                approval.action_confirm()

            self._create_payment_log(user_env, chat, internal_user, data, approval)

            base_url = approval.get_base_url()
            message = translation_env(bot, chat)._(
                "Done! Approval request %(name)s was created. /ayuda"
            ) % {"name": tg.code(approval.name)}

            if base_url:
                approval_url = f"{base_url}/web#id={approval.id}&model=approval.request&view_type=form"
                message = translation_env(bot, chat)._(
                    "Done! Approval request %(name)s was created. /ayuda"
                ) % {"name": tg.link(approval.name, approval_url)}

            bot.send_message(chat.chat_id, message)
            self._flow_end(chat)

        except AccessError:
            _logger.exception(
                "AccessError for user %s while creating payment approval",
                internal_user.login,
            )
            bot.send_message(
                chat.chat_id,
                translation_env(bot, chat)._(
                    "You do not have permission to create approval requests."
                ),
            )
            self._flow_end(chat)
        except UserError, ValidationError, ValueError, KeyError:
            _logger.exception(
                "Validation error creating payment approval for user %s",
                internal_user.login,
            )
            bot.send_message(
                chat.chat_id,
                translation_env(bot, chat)._(
                    "An error occurred creating the request in Odoo. Check the "
                    "receipt and try again."
                ),
            )
            self._flow_end(chat)

    @log_command_execution
    def _handle_especie_command(
        self,
        bot,
        chat,
        args,
        partner=False,
        internal_user=False,
    ) -> None:
        self._flow_start(chat, "especie_details")
        bot.send_message(
            chat.chat_id,
            (
                translation_env(bot, chat)._(
                    "Please send the payment-in-kind details on 6 separate lines, "
                    "in the format shown in /ayuda.\n\nYou can use /cancelar "
                    "at any time to stop this operation."
                )
            ),
        )

    def _process_especie_details(self, bot, chat, message, internal_user) -> None:
        lines = _strip_invisible(message.get("text", "")).strip().split("\n")
        if len(lines) != 6:
            bot.send_message(
                chat.chat_id,
                translation_env(bot, chat)._(
                    "Error: 6 lines were expected, but %(count)s were received. "
                    "Please send all the values in a single message, one per line. "
                    "Use /ayuda to see the exact format."
                )
                % {"count": len(lines)},
            )
            return

        (
            p_fx_name,
            category,
            p_cn_name,
            date_str,
            amount_str,
            product_ref,
        ) = (line.strip() for line in lines)
        tr_env = translation_env(bot, chat)
        errors = []

        partner_fx, err = self._get_partner_or_error(
            internal_user, p_fx_name, tr_env._("Billed to"), tr_env
        )
        if err:
            errors.append(err)

        err = self._resolve_choice_error(
            category,
            ["vehiculos"],
            tr_env._("Invalid product category: '%(value)s'. Options: Vehiculos.")
            % {"value": category},
        )
        if err:
            errors.append(err)

        partner_cn, err = self._get_partner_or_error(
            internal_user, p_cn_name, tr_env._("Payment applied to"), tr_env
        )
        if err:
            errors.append(err)

        payment_date, err = self._get_date_or_error(date_str, tr_env)
        if err:
            errors.append(err)

        amount, err = self._get_amount_or_error(amount_str, tr_env)
        if err:
            errors.append(err)

        product_ref = product_ref.strip()
        if not product_ref:
            errors.append(tr_env._("The product reference cannot be empty."))

        if errors:
            bot.send_message(
                chat.chat_id,
                tr_env._("The following errors were found:\n\n%(errors)s")
                % {"errors": "\n".join(f"- {tg.escape(e)}" for e in errors)},
            )
            return

        pending_data = {
            "partner_fx_id": partner_fx.id,
            "partner_fx_name": partner_fx.name,
            "product_category": self._normalize_string(category).upper(),
            "partner_cn_id": partner_cn.id,
            "partner_cn_name": partner_cn.name,
            "date": payment_date.strftime("%Y-%m-%d"),
            "amount": amount,
            "product_reference": product_ref,
        }
        chat._flow_advance("especie_proof", pending_data)
        bot.send_message(
            chat.chat_id,
            translation_env(bot, chat)._(
                "Data validated. Please now send a photo or PDF of the asset as "
                "evidence."
            ),
        )

    def _handle_especie_proof_file(
        self, bot, chat, message, internal_user, is_photo
    ) -> None:
        if is_photo:
            file_id = message["photo"][-1]["file_id"]
            file_mimetype = "image/jpeg"
        else:
            file_id = message["document"]["file_id"]
            file_mimetype = "application/pdf"
            if (message["document"].get("file_size") or 0) > PROOF_MAX_BYTES:
                bot.send_message(
                    chat.chat_id,
                    translation_env(bot, chat)._(
                        "The file is larger than 20 MB. Send a smaller photo or PDF."
                    ),
                )
                return

        file_content = bot.get_file_content(file_id)
        if not file_content:
            bot.send_message(
                chat.chat_id,
                translation_env(bot, chat)._(
                    "Error downloading the file. Please try again."
                ),
            )
            return

        pending_data = self._flow_data(chat)
        pending_data["file_b64"] = base64.b64encode(file_content).decode("ascii")
        pending_data["file_mimetype"] = file_mimetype

        chat._flow_advance("especie_confirm", pending_data)

        tr_env = translation_env(bot, chat)
        summary_text = "\n".join(
            [
                tr_env._(
                    "Please confirm the data to create the payment-in-kind request:"
                ),
                "",
                *(
                    f"- {tg.bold(label)}: {tg.escape(value)}"
                    for label, value in (
                        (tr_env._("Billed to"), pending_data["partner_fx_name"]),
                        (
                            tr_env._("Product category"),
                            pending_data["product_category"],
                        ),
                        (
                            tr_env._("Payment applied to"),
                            pending_data["partner_cn_name"],
                        ),
                        (tr_env._("Date"), pending_data["date"]),
                        (tr_env._("Amount"), f"${pending_data['amount']:,.2f}"),
                        (
                            tr_env._("Product reference"),
                            pending_data["product_reference"],
                        ),
                        (tr_env._("Evidence"), tr_env._("(File received)")),
                    )
                ),
            ]
        )
        bot.send_message(
            chat.chat_id,
            summary_text,
            reply_markup=kb.confirm_cancel(
                tr_env._("1. Confirm"),
                "especie_confirm",
                tr_env._("2. Cancel"),
                "especie_cancel",
            ),
        )

    def _confirm_especie_approval(self, bot, chat, internal_user) -> None:
        category = self._intake_category(bot, "especie")
        if not category:
            bot.send_message(
                chat.chat_id,
                translation_env(bot, chat)._(
                    "Error: %(company)s has no approval category for payments "
                    "in kind recorded with /especie."
                )
                % {"company": bot._acting_company().name},
            )
            self._flow_end(chat)
            return

        if not internal_user:
            bot.send_message(
                chat.chat_id,
                translation_env(bot, chat)._(
                    "Your Telegram account is not linked to an internal user. "
                    "Contact IT to fix it."
                ),
            )
            self._flow_end(chat)
            return

        data = self._flow_data(chat)

        telegram_data = data.copy()
        telegram_data.pop("file_b64", None)
        telegram_data.pop("file_mimetype", None)

        try:
            date_str = data["date"]
            naive_dt = datetime.strptime(date_str, "%Y-%m-%d").replace(hour=12)
            mexico_tz = timezone(DEFAULT_TZ)
            localized_dt = _localize_strict(naive_dt, mexico_tz)
            user_env = (
                bot.with_user(internal_user)
                .with_context(allowed_company_ids=[bot._acting_company().id])
                .env
            )

            approval_vals = {
                "category_id": category.id,
                "request_owner_id": internal_user.id,
                "company_id": bot._acting_company().id,
                "partner_id": data["partner_fx_id"],
                "date": fields.Datetime.to_string(localized_dt),
                "amount": data["amount"],
                "telegram_data": telegram_data,
                "reason": user_env[
                    "telegram.payment.report.log"
                ]._format_payment_details_html(telegram_data),
            }

            with user_env.cr.savepoint():
                approval = user_env["approval.request"].create(approval_vals)

                if data.get("file_b64"):
                    safe_name = re.sub(r"[^a-zA-Z0-9]", "_", data["partner_fx_name"])
                    attachment_name = (
                        f"evidencia_especie_{safe_name}_{approval.id}"
                        f"{PROOF_EXTENSIONS.get(data.get('file_mimetype'), '')}"
                    )
                    attachment = user_env["ir.attachment"].create(
                        {
                            "name": attachment_name,
                            "datas": data["file_b64"],
                            "res_model": "approval.request",
                            "res_id": approval.id,
                            "company_id": approval.company_id.id,
                            "type": "binary",
                            "mimetype": data.get(
                                "file_mimetype", "application/octet-stream"
                            ),
                        }
                    )
                    approval.message_post(
                        body=approval.env._("Asset evidence attached from Telegram."),
                        attachment_ids=[attachment.id],
                    )

                approval.action_confirm()

            self._create_payment_log(user_env, chat, internal_user, data, approval)

            base_url = approval.get_base_url()
            message = translation_env(bot, chat)._(
                "Done! Payment-in-kind request %(name)s was created. /ayuda"
            ) % {"name": tg.code(approval.name)}

            if base_url:
                approval_url = f"{base_url}/web#id={approval.id}&model=approval.request&view_type=form"
                message = translation_env(bot, chat)._(
                    "Done! Payment-in-kind request %(name)s was created. /ayuda"
                ) % {"name": tg.link(approval.name, approval_url)}

            bot.send_message(chat.chat_id, message)
            self._flow_end(chat)

        except AccessError:
            _logger.exception(
                "AccessError for user %s while creating especie approval",
                internal_user.login,
            )
            bot.send_message(
                chat.chat_id,
                translation_env(bot, chat)._(
                    "You do not have permission to create approval requests."
                ),
            )
            self._flow_end(chat)
        except UserError, ValidationError, ValueError, KeyError:
            _logger.exception(
                "Validation error creating especie approval for user %s",
                internal_user.login,
            )
            bot.send_message(
                chat.chat_id,
                translation_env(bot, chat)._(
                    "An error occurred creating the request in Odoo. Check the "
                    "evidence and try again."
                ),
            )
            self._flow_end(chat)

    def _create_payment_log(
        self, user_env, chat, internal_user, payment_data, approval
    ):
        try:
            log_data = {
                k: v
                for k, v in payment_data.items()
                if k not in ("file_b64", "file_mimetype")
            }

            user_env["telegram.payment.report.log"].with_privilege(
                "approval_account_telegram.privilege_log_payment_request",
                reason="the bot logs the payment request it filed for its sender",
            ).create(
                {
                    "chat_id": chat.id,
                    "telegram_chat_id": chat.chat_id,
                    "partner_id": (
                        internal_user.partner_id.id
                        if internal_user.partner_id
                        else False
                    ),
                    "user_id": internal_user.id,
                    "payment_details": json_dumps(log_data),
                    "approval_request_id": approval.id,
                    "amount": payment_data.get("amount", 0.0),
                }
            )
        except AccessError, UserError, ValidationError, ValueError:
            _logger.exception(
                "Failed to create payment report log for approval %s",
                approval.name,
            )
