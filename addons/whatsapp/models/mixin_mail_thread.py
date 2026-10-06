from odoo import api, models

from odoo.addons.mail.tools.discuss import Store


class MixinMailThread(models.AbstractModel):
    _inherit = "mixin.mail.thread"

    def _thread_to_store(self, store: Store, field_specs, *, request_list=None) -> None:
        super()._thread_to_store(store, field_specs, request_list=request_list)
        if request_list:
            can_send_whatsapp = self.env["whatsapp.template"]._can_use_whatsapp(
                self._name
            )
            store.add(self, {"canSendWhatsapp": can_send_whatsapp}, as_thread=True)

    @api.model
    def _web_push_all_recipients_message_types(self) -> frozenset[str]:
        return super()._web_push_all_recipients_message_types() | {"whatsapp_message"}
