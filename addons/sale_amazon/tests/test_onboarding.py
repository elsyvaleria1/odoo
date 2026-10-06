import time
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, urlencode, urlsplit

from odoo.libs.json import dumps as json_dumps
from odoo.libs.json import loads as json_loads
from odoo.tests import HttpCase, new_test_user, tagged
from odoo.tools import hash_sign, hmac, mute_logger, security

from odoo.addons.sale_amazon import utils as amazon_utils
from odoo.addons.sale_amazon.controllers import onboarding
from odoo.addons.sale_amazon.tests.common import ORDER_MOCK


@tagged("post_install", "-at_install")
class TestAmazonOnboardingSignature(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        marketplace = cls.env["amazon.marketplace"].search(
            [("api_ref", "=", ORDER_MOCK["MarketplaceId"])]
        )
        cls.branch = cls.env["res.company"].create(
            {"name": "Amazon branch", "parent_id": cls.env.company.id}
        )
        cls.env.ref("base.user_admin").company_ids += cls.branch
        cls.account, cls.other_account = cls.env["amazon.account"].create(
            [
                {
                    "name": name,
                    "base_marketplace_id": marketplace.id,
                    "available_marketplace_ids": [marketplace.id],
                    "active_marketplace_ids": [marketplace.id],
                    "company_id": cls.env.company.id,
                }
                for name in ("Signed", "Other")
            ]
        )
        new_test_user(
            cls.env,
            login="amazon_other",
            groups="sale.group_sale_manager",
            company_id=cls.env.company.id,
        )

    def setUp(self):
        super().setUp()
        self.authenticate("admin", "admin")

    def _state(self, account):
        action = self.call_jsonrpc(
            "/web/dataset/call_button",
            {
                "model": "amazon.account",
                "method": "action_redirect_to_oauth_url",
                "args": [account.ids],
                "kwargs": {},
            },
        )
        return json_loads(parse_qs(urlsplit(action["url"]).query)["state"][0])

    def _return(self, state):
        query = urlencode(
            {
                "selling_partner_id": "A seller",
                "spapi_oauth_code": "A code",
                "state": json_dumps(state),
            }
        )
        return self.url_open(f"/amazon/return?{query}", allow_redirects=False)

    def _return_refused(self, state):
        with (
            patch.object(amazon_utils, "exchange_authorization_code") as exchange,
            mute_logger("odoo.addons.sale_amazon.controllers.onboarding"),
        ):
            response = self._return(state)
        self.assertEqual(response.status_code, 403, response.text)
        self.assertIn("invalid, has expired or was already used", response.text)
        exchange.assert_not_called()
        return response

    def _return_accepted(self, state):
        with (
            patch.object(amazon_utils, "exchange_authorization_code") as exchange,
            patch.object(
                type(self.env["amazon.account"]), "action_update_available_marketplaces"
            ),
        ):
            response = self._return(state)
        self.assertEqual(response.status_code, 303, response.text)
        exchange.assert_called_once()
        return exchange.call_args.args[1]

    def test_the_state_is_accepted_once_for_the_account_it_was_issued_for(self):
        state = self._state(self.account)
        self.assertEqual(set(state), {"return_url", "token"})
        self.assertEqual(self._return_accepted(state), self.account)
        self.assertEqual(self.account.seller_key, "A seller")
        self._return_refused(state)

    def test_an_expired_state_is_refused(self):
        state = self._state(self.account)
        later = SimpleNamespace(
            time=lambda: time.time() + onboarding._OAUTH_STATE_MAX_AGE_SECONDS + 1
        )
        with patch.object(security, "time", later):
            self._return_refused(state)
        self.assertFalse(self.account.seller_key)

    def test_a_tampered_state_is_refused(self):
        state = self._state(self.account)
        token = state["token"]
        forged_claims = {
            "account_id": self.other_account.id,
            "company_id": self.env.company.id,
            "db": self.env.cr.dbname,
            "uid": self.env.ref("base.user_admin").id,
            "nonce": "n",
        }
        legacy = {
            "account_id": self.account.id,
            "return_url": state["return_url"],
            "signature": hmac(self.env, onboarding.OAUTH_SCOPE, str(self.account.id)),
        }
        for tampered in (
            {
                **state,
                "token": token[:-2] + ("A" if token[-2] != "A" else "B") + token[-1],
            },
            {
                **state,
                "token": hash_sign(self.env, onboarding.OAUTH_SCOPE, forged_claims, 1),
            },
            {**state, "token": 5},
            {"return_url": state["return_url"]},
            legacy,
            "not json",
        ):
            with self.subTest(tampered=tampered):
                self._state(self.account)
                self._return_refused(tampered)
        self.assertFalse(self.account.seller_key)

    def test_a_state_issued_for_another_account_or_user_is_refused(self):
        self.authenticate("amazon_other", "amazon_other")
        foreign = self._state(self.other_account)
        self.authenticate("admin", "admin")
        self._state(self.account)
        self._return_refused(foreign)
        self.assertFalse(self.other_account.seller_key)

    def test_a_state_for_an_account_since_moved_to_another_company_is_refused(self):
        self.opener.cookies.set("cids", f"{self.env.company.id}-{self.branch.id}")
        state = self._state(self.account)
        self.account.write(
            {
                "company_id": self.branch.id,
                "team_id": self.env["team.team"]
                .create({"name": "Branch", "company_id": self.branch.id})
                .id,
                "location_id": self.env["stock.location"]
                .create(
                    {
                        "name": "Branch",
                        "usage": "internal",
                        "company_id": self.branch.id,
                    }
                )
                .id,
            }
        )
        self._return_refused(state)
        self.assertFalse(self.account.seller_key)
