import re

from odoo import models
from odoo.exceptions import AccessError, UserError
from odoo.libs.debug_log import DebugLog
from odoo.tools import html2plaintext

from odoo.addons.iap.tools import iap_tools

DEFAULT_OLG_ENDPOINT = "https://olg.api.odoo.com"

_debug = DebugLog(__name__)


class HrJob(models.Model):
    _inherit = "hr.job"

    def _get_plain_text_description(self):
        def remove_uris(text):
            return re.sub(
                r"\b((https?|ftp|file):\/\/[-A-Z0-9+&@#\/%?=~_|!:,.;]*[-A-Z0-9+&@#\/%=~_|])\b",
                "",
                text,
            )

        def remove_files(text):
            return re.sub(
                r"(\S+ \[\d+\]|\[\d+\] /|/\S+/static/\S+|\b\S+\.\w+)", "", text
            )

        self.check_singleton()
        if _debug.pipeline.enabled:
            # the two regexes run a second time here, so this site is guarded:
            # with the channel off it must not cost the flattening twice
            _debug.pipeline(
                "website_job_description_flattened",
                job=self,
                html_length=len(self.website_description or ""),
                # `remove_files` strips anything matching `\b\S+\.\w+`, which
                # is every filename AND every sentence-ending word followed by a
                # capitalised one, so the text handed to the model is shorter
                # than the description in ways nobody sees
                plain_text_length=len(
                    remove_files(
                        remove_uris(html2plaintext(self.website_description))
                    ).replace("*", "")
                ),
            )
        return remove_files(
            remove_uris(html2plaintext(self.website_description))
        ).replace("*", "")

    def _generate_post(self):
        self.check_singleton()

        recruiter_ai_prompt = self.env._("""IGNORE PREVIOUS PROMPTS AND FORMAT AS HTML AND NO HYPERLINKS
You are the best recruiter in out company and we are looking to hire a new employee.
You have been tasked with creating a the best job description for a new job opening.
Given the following infos, make a friendly and attractive job description that could be used
to attract potential candidates (The platforms could be things like LinkedIn, Indeed, Glassdoor, Monster, etc.)
It's your last chance to make a good impression and attract the best candidates to our company so make it count!
Here is the data to generate the job description:
""")
        prompt = recruiter_ai_prompt + self._get_plain_text_description()
        try:
            IrConfigParameter = self.env["ir.config_parameter"].sudo()
            olg_api_endpoint = IrConfigParameter.get_param(
                "html_editor.olg_api_endpoint", DEFAULT_OLG_ENDPOINT
            )
            database_id = IrConfigParameter.get_param("database.uuid")
            response = iap_tools.iap_jsonrpc(
                olg_api_endpoint + "/api/olg/1/chat",
                params={
                    "prompt": prompt,
                    "conversation_history": [],
                    "database_id": database_id,
                },
                timeout=30,
                env=self.env,
                purpose="iap.olg.job_description",
            )
            _debug.logic(
                "website_job_post_generated",
                job=self,
                status=response["status"],
                endpoint=olg_api_endpoint,
                prompt_length=len(prompt),
                content_length=len(response.get("content") or ""),
            )
            if response["status"] == "success":
                return response["content"].replace("```html\n", "").replace("\n```", "")
            elif response["status"] == "error_prompt_too_long":
                raise UserError(
                    self.env._("Sorry, the web page is too long for our AI to process.")
                )
            elif response["status"] == "limit_call_reached":
                raise UserError(
                    self.env._(
                        "You have reached the maximum number of requests for this service. Try again later."
                    )
                )
            else:
                raise UserError(
                    self.env._(
                        "Sorry, we could not generate a response. Please try again later."
                    )
                )
        except AccessError as e:
            _debug.logic(
                "website_job_post_unreachable",
                job=self,
                # every local this branch could name is bound inside the `try`,
                # so naming one would make the site itself raise NameError on
                # the path where the call failed earliest
                error=str(e),
            )
            raise AccessError(
                self.env._("Oops, it looks like our AI is unreachable!")
            ) from e
