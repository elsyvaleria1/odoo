from unittest.mock import Mock, patch

from odoo.tests import TransactionCase, tagged

from odoo.addons.integration_github.tools import get_github_client


@tagged("post_install", "-at_install", "integration_github", "github")
class TestPullRequestReads(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.service = cls.env.ref("integration_github.service_github")
        cls.category = cls.env.ref("credential.credential_category_custom")
        cls.company_credential = cls.env["credential.credential"].create(
            {
                "name": "GitHub company token",
                "endpoint_id": cls.service.id,
                "company_id": cls.env.company.id,
                "category_id": cls.category.id,
                "environment": cls.service.environment,
                "bearer_token": "ghp_company",
            }
        )

    def _pages(self, *payloads):
        responses = []
        for payload in (*payloads, []):
            response = Mock(headers={"content-type": "application/json"})
            response.status_code = 200
            response.json.return_value = payload
            responses.append(response)
        return responses

    @patch("requests.Session.request")
    def test_it_reads_comments_from_the_issues_path(self, request):
        request.side_effect = self._pages([{"id": 1, "body": "preview: ok"}])

        comments = get_github_client(self.env).list_issue_comments(
            "Agro-Marin", "agromarin", 12
        )

        self.assertEqual(len(comments), 1)
        self.assertEqual(comments[0]["body"], "preview: ok")
        url = request.call_args_list[0].kwargs["url"]
        self.assertEqual(
            url,
            "https://api.github.com/repos/Agro-Marin/agromarin/issues/12/comments",
        )

    @patch("requests.Session.request")
    def test_it_pages_through_every_comment(self, request):
        request.side_effect = self._pages(
            [{"id": 1}, {"id": 2}],
            [{"id": 3}],
        )

        comments = get_github_client(self.env).list_issue_comments("o", "r", 1)

        self.assertEqual([c["id"] for c in comments], [1, 2, 3])

    @patch("requests.Session.request")
    def test_since_is_sent_only_when_given(self, request):
        request.side_effect = self._pages([])
        client = get_github_client(self.env)

        client.list_issue_comments("o", "r", 1)
        self.assertNotIn("since", request.call_args_list[0].kwargs["params"])

        request.side_effect = self._pages([])
        client.list_issue_comments("o", "r", 1, since="2026-08-01T00:00:00Z")
        self.assertEqual(
            request.call_args_list[-1].kwargs["params"]["since"],
            "2026-08-01T00:00:00Z",
        )

    @patch("requests.Session.request")
    def test_it_reads_reviews_from_the_pulls_path(self, request):
        request.side_effect = self._pages(
            [{"id": 7, "state": "APPROVED", "user": {"login": "someone"}}]
        )

        reviews = get_github_client(self.env).list_pull_request_reviews("o", "r", 12)

        self.assertEqual(reviews[0]["state"], "APPROVED")
        self.assertEqual(
            request.call_args_list[0].kwargs["url"],
            "https://api.github.com/repos/o/r/pulls/12/reviews",
        )

    def test_the_endpoint_admits_personal_credentials(self):
        self.assertTrue(self.service.allow_user_credentials)

    def test_a_developer_with_their_own_token_calls_as_themselves(self):
        developer = self.env["res.users"].create(
            {
                "name": "Dev",
                "login": "dev_github_reads",
                "group_ids": [
                    (
                        6,
                        0,
                        [
                            self.env.ref("base.group_user").id,
                            self.env.ref("credential.group_credential_user").id,
                        ],
                    )
                ],
            }
        )
        personal = self.env["credential.credential"].create(
            {
                "name": "Dev's GitHub PAT",
                "endpoint_id": self.service.id,
                "category_id": self.category.id,
                "environment": self.service.environment,
                "bearer_token": "ghp_dev",
                "owner_user_id": developer.id,
            }
        )

        as_developer = get_github_client(self.env(user=developer))
        self.assertEqual(as_developer._client.credential, personal)

        self.assertEqual(
            get_github_client(self.env)._client.credential,
            self.company_credential,
            "a user without a personal token still spends the company's",
        )
