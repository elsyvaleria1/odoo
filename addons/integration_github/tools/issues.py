class IssuesMixin:
    def list_issues(
        self,
        owner,
        repo,
        state="open",
        labels=None,
        assignee=None,
        sort="created",
        per_page=100,
        max_pages=10,
    ):
        params = {
            "state": state,
            "sort": sort,
            "per_page": per_page,
        }

        if labels:
            params["labels"] = labels
        if assignee:
            params["assignee"] = assignee

        return list(
            self.paginate(
                f"/repos/{owner}/{repo}/issues",
                params=params,
                max_pages=max_pages,
            )
        )

    def get_issue(self, owner, repo, issue_number):
        return self._client.get(f"/repos/{owner}/{repo}/issues/{issue_number}")["body"]

    def create_issue(
        self,
        owner,
        repo,
        title,
        body=None,
        labels=None,
        assignees=None,
        milestone=None,
    ):
        payload = {"title": title}

        if body:
            payload["body"] = body
        if labels:
            payload["labels"] = labels
        if assignees:
            payload["assignees"] = assignees
        if milestone:
            payload["milestone"] = milestone

        return self._client.post(f"/repos/{owner}/{repo}/issues", json=payload)["body"]

    def update_issue(
        self,
        owner,
        repo,
        issue_number,
        title=None,
        body=None,
        state=None,
        labels=None,
        assignees=None,
    ):
        payload = {}

        if title:
            payload["title"] = title
        if body:
            payload["body"] = body
        if state:
            payload["state"] = state
        if labels is not None:
            payload["labels"] = labels
        if assignees is not None:
            payload["assignees"] = assignees

        return self._client.patch(
            f"/repos/{owner}/{repo}/issues/{issue_number}",
            json=payload,
        )["body"]

    def list_issue_comments(
        self,
        owner,
        repo,
        issue_number,
        since=None,
        per_page=100,
        max_pages=10,
    ):
        params = {"per_page": per_page}
        if since:
            params["since"] = since
        return list(
            self.paginate(
                f"/repos/{owner}/{repo}/issues/{issue_number}/comments",
                params=params,
                max_pages=max_pages,
            ),
        )

    def create_issue_comment(self, owner, repo, issue_number, body):
        payload = {"body": body}
        return self._client.post(
            f"/repos/{owner}/{repo}/issues/{issue_number}/comments",
            json=payload,
        )["body"]

    def list_pull_requests(
        self,
        owner,
        repo,
        state="open",
        head=None,
        base=None,
        sort="created",
        direction="desc",
        per_page=100,
        max_pages=10,
    ):
        params = {
            "state": state,
            "sort": sort,
            "direction": direction,
            "per_page": per_page,
        }

        if head:
            params["head"] = head
        if base:
            params["base"] = base
        return list(
            self.paginate(
                f"/repos/{owner}/{repo}/pulls",
                params=params,
                max_pages=max_pages,
            ),
        )

    def get_pull_request(self, owner, repo, pull_number):
        return self._client.get(f"/repos/{owner}/{repo}/pulls/{pull_number}")["body"]

    def create_pull_request(
        self,
        owner,
        repo,
        title,
        head,
        base,
        body=None,
        draft=False,
        maintainer_can_modify=True,
    ):
        payload = {
            "title": title,
            "head": head,
            "base": base,
            "draft": draft,
            "maintainer_can_modify": maintainer_can_modify,
        }

        if body:
            payload["body"] = body

        return self._client.post(f"/repos/{owner}/{repo}/pulls", json=payload)["body"]

    def merge_pull_request(
        self,
        owner,
        repo,
        pull_number,
        commit_title=None,
        commit_message=None,
        merge_method="merge",
    ):
        payload = {"merge_method": merge_method}

        if commit_title:
            payload["commit_title"] = commit_title
        if commit_message:
            payload["commit_message"] = commit_message

        return self._client.put(
            f"/repos/{owner}/{repo}/pulls/{pull_number}/merge",
            json=payload,
        )["body"]

    def list_pull_request_reviews(
        self,
        owner,
        repo,
        pull_number,
        per_page=100,
        max_pages=10,
    ):
        return list(
            self.paginate(
                f"/repos/{owner}/{repo}/pulls/{pull_number}/reviews",
                params={"per_page": per_page},
                max_pages=max_pages,
            ),
        )

    def create_pull_request_review(
        self,
        owner,
        repo,
        pull_number,
        event="COMMENT",
        body=None,
        comments=None,
    ):
        payload = {"event": event}

        if body:
            payload["body"] = body
        if comments:
            payload["comments"] = comments

        return self._client.post(
            f"/repos/{owner}/{repo}/pulls/{pull_number}/reviews",
            json=payload,
        )["body"]
