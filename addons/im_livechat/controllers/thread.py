from werkzeug.exceptions import NotFound

from odoo.exceptions import AccessError
from odoo.http import request, route
from odoo.libs.debug_log import DebugLog

from odoo.addons.mail.controllers import thread
from odoo.addons.mail.tools.discuss import add_guest_to_context

_debug = DebugLog(__name__)


class ThreadController(thread.ThreadController):
    @route()
    @add_guest_to_context
    def mail_message_post(
        self, thread_model, thread_id, post_data, context=None, **kwargs
    ):
        if selected_answer_id := kwargs.pop("selected_answer_id", None):
            request.update_context(selected_answer_id=selected_answer_id)
        if thread_model == "discuss.channel":
            channel = self._get_thread_with_access_for_post(
                thread_model, thread_id, **kwargs
            )
            if not channel:
                raise NotFound
            if channel._is_livechat_closed_to_current_user():
                _debug.logic("post_refused", channel=channel.id, reason="session_ended")
                raise AccessError(
                    request.env._("This live chat conversation has ended.")
                )
        return super().mail_message_post(
            thread_model, thread_id, post_data, context, **kwargs
        )
