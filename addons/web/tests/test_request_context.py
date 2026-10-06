import functools
from unittest.mock import patch

from odoo import Command
from odoo.libs.collections import FrozenList
from odoo.tests import common


@common.tagged("post_install", "-at_install", "web_http")
class TestRequestContextCompanies(common.HttpCase):
    def test_a_json_rpc_context_reaches_the_model_with_frozen_company_ids(self):
        second = self.env["res.company"].create({"name": "Request Context Second"})
        companies = [second.id, self.env.company.id]
        common.new_test_user(
            self.env,
            "request_context_user",
            password="request_context_pw",
            company_id=second.id,
            company_ids=[Command.set(companies)],
        )
        partner_class = type(self.env["res.partner"])
        original = partner_class.web_search_read
        seen = []

        @functools.wraps(original)
        def web_search_read(model, *args, **kwargs):
            context = model.env.context
            hash(context)
            seen.append(
                (
                    type(context["allowed_company_ids"]),
                    context["allowed_company_ids"],
                    getattr(context, "_hash", None) is not None,
                )
            )
            return original(model, *args, **kwargs)

        self.authenticate("request_context_user", "request_context_pw")
        with patch.object(partner_class, "web_search_read", web_search_read):
            result = self.call_jsonrpc(
                "/web/dataset/call_kw/res.partner/web_search_read",
                {
                    "model": "res.partner",
                    "method": "web_search_read",
                    "args": [],
                    "kwargs": {
                        "specification": {"name": {}},
                        "domain": [],
                        "limit": 1,
                        "context": {"lang": "en_US", "allowed_company_ids": companies},
                    },
                },
            )

        self.assertIn("records", result)
        self.assertEqual(seen, [(FrozenList, companies, True)])
