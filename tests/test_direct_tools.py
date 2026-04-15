import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")

from kendr.direct_tools import DirectToolDefinition, build_direct_tool_catalog, execute_direct_tool, run_direct_tool_loop


class DirectToolCatalogTests(unittest.TestCase):
    def test_build_direct_tool_catalog_includes_skills_and_mcp_tools(self):
        with (
            patch(
                "kendr.skill_manager.list_runtime_skills",
                return_value=[
                    {
                        "slug": "file-reader",
                        "name": "File Reader",
                        "description": "Read local files.",
                        "input_schema": {"type": "object", "required": ["file_path"]},
                        "metadata": {"permissions": {"requires_approval": False}},
                        "skill_type": "catalog",
                        "category": "Documents",
                    }
                ],
            ),
            patch(
                "kendr.mcp_manager.list_servers",
                return_value=[
                    {
                        "id": "srv1",
                        "name": "Example",
                        "type": "http",
                        "connection": "http://localhost:8000/mcp",
                        "enabled": True,
                        "tools": [
                            {
                                "name": "ping",
                                "description": "Ping tool",
                                "schema": {"type": "object", "required": ["value"]},
                            }
                        ],
                    }
                ],
            ),
        ):
            tools = build_direct_tool_catalog({})

        tool_ids = {tool.tool_id for tool in tools}
        self.assertIn("skill:file-reader", tool_ids)
        self.assertIn("mcp:srv1:ping", tool_ids)

    def test_run_direct_tool_loop_calls_tool_then_returns_final(self):
        tool = DirectToolDefinition(
            tool_id="skill:file-reader",
            kind="skill",
            name="File Reader",
            description="Read local files.",
            input_schema={"type": "object", "required": ["file_path"]},
            requires_approval=False,
            metadata={"slug": "file-reader"},
        )
        llm_outputs = [
            """{"action":"call_tool","tool_id":"skill:file-reader","arguments":{"file_path":"/tmp/note.txt"},"reason":"Need the file contents."}""",
            """{"action":"final","reason":"The tool returned the answer.","response":"The note says the meeting moved to Friday."}""",
        ]

        class _Response:
            def __init__(self, content: str) -> None:
                self.content = content

        with (
            patch("kendr.direct_tools.build_direct_tool_catalog", return_value=[tool]),
            patch("kendr.direct_tools.llm.invoke", side_effect=[_Response(item) for item in llm_outputs]),
            patch(
                "kendr.direct_tools.execute_direct_tool",
                return_value=type(
                    "_ExecResult",
                    (),
                    {
                        "ok": True,
                        "summary": "The meeting moved to Friday.",
                        "awaiting_input": False,
                        "state_updates": {"direct_tool_last_result": {"tool_id": "skill:file-reader", "status": "ok"}},
                    },
                )(),
            ),
        ):
            result = run_direct_tool_loop({"user_query": "what does the note say?"})

        self.assertEqual(result["status"], "final")
        self.assertIn("Friday", result["response"])

    def test_run_direct_tool_loop_uses_native_tool_calling_when_supported(self):
        tool = DirectToolDefinition(
            tool_id="integration:github:get_repo",
            kind="integration",
            name="Get GitHub Repository",
            description="Fetch repository metadata.",
            metadata={"integration_id": "github", "action": "get_repo"},
        )

        class _NativeClient:
            def __init__(self):
                self.calls = 0

            def bind_tools(self, _tools):
                return self

            def invoke(self, _messages):
                self.calls += 1
                if self.calls == 1:
                    return SimpleNamespace(
                        content="",
                        tool_calls=[
                            {
                                "id": "call_1",
                                "name": "integration:github:get_repo",
                                "args": {"repo": "openai/sample"},
                            }
                        ],
                    )
                return SimpleNamespace(content="Repository openai/sample is public.", tool_calls=[])

        with (
            patch("kendr.direct_tools.build_direct_tool_catalog", return_value=[tool]),
            patch("kendr.direct_tools._native_tool_calling_supported", return_value=True),
            patch("kendr.direct_tools._client_for_model", return_value=_NativeClient()),
            patch("kendr.direct_tools.model_for_agent", return_value="gpt-5.4-mini"),
            patch(
                "kendr.direct_tools.execute_direct_tool",
                return_value=type(
                    "_ExecResult",
                    (),
                    {
                        "ok": True,
                        "output": {"full_name": "openai/sample", "private": False},
                        "summary": '{"full_name":"openai/sample","private":false}',
                        "awaiting_input": False,
                        "state_updates": {"direct_tool_last_result": {"tool_id": "integration:github:get_repo", "status": "ok"}},
                    },
                )(),
            ),
            patch("kendr.direct_tools.llm.invoke") as mock_json_llm,
        ):
            result = run_direct_tool_loop({"user_query": "inspect openai/sample"})

        self.assertEqual(result["status"], "final")
        self.assertIn("openai/sample", result["response"])
        self.assertFalse(mock_json_llm.called, "Native tool calling should bypass the JSON decision loop.")

    def test_run_direct_tool_loop_falls_back_to_json_loop_when_native_path_fails(self):
        tool = DirectToolDefinition(
            tool_id="skill:file-reader",
            kind="skill",
            name="File Reader",
            description="Read local files.",
            input_schema={"type": "object", "required": ["file_path"]},
            metadata={"slug": "file-reader"},
        )
        llm_outputs = [
            """{"action":"call_tool","tool_id":"skill:file-reader","arguments":{"file_path":"/tmp/note.txt"},"reason":"Need file output."}""",
            """{"action":"final","reason":"Done","response":"Used JSON fallback."}""",
        ]

        class _BrokenNativeClient:
            def bind_tools(self, _tools):
                raise RuntimeError("native bind failed")

        class _Response:
            def __init__(self, content: str) -> None:
                self.content = content

        with (
            patch("kendr.direct_tools.build_direct_tool_catalog", return_value=[tool]),
            patch("kendr.direct_tools._native_tool_calling_supported", return_value=True),
            patch("kendr.direct_tools._client_for_model", return_value=_BrokenNativeClient()),
            patch("kendr.direct_tools.model_for_agent", return_value="gpt-5.4-mini"),
            patch("kendr.direct_tools.llm.invoke", side_effect=[_Response(item) for item in llm_outputs]),
            patch(
                "kendr.direct_tools.execute_direct_tool",
                return_value=type(
                    "_ExecResult",
                    (),
                    {
                        "ok": True,
                        "summary": "Fallback note content.",
                        "awaiting_input": False,
                        "state_updates": {"direct_tool_last_result": {"tool_id": "skill:file-reader", "status": "ok"}},
                    },
                )(),
            ),
        ):
            state = {"user_query": "where am i?"}
            result = run_direct_tool_loop(state)

        self.assertEqual(result["status"], "final")
        self.assertEqual(result["response"], "Used JSON fallback.")
        self.assertIn("native bind failed", state.get("direct_tool_native_fallback_reason", ""))

    def test_build_direct_tool_catalog_includes_supported_integrations_when_available(self):
        with (
            patch.dict(
                os.environ,
                {
                    "AWS_ACCESS_KEY_ID": "key",
                    "AWS_SECRET_ACCESS_KEY": "secret",
                    "GITHUB_TOKEN": "gh-token",
                },
                clear=False,
            ),
            patch("kendr.skill_manager.list_runtime_skills", return_value=[]),
            patch("kendr.mcp_manager.list_servers", return_value=[]),
            patch("kendr.providers.get_google_access_token", return_value="google-token"),
            patch("kendr.providers.get_slack_bot_token", return_value="slack-token"),
            patch("kendr.providers.get_microsoft_graph_access_token", return_value="graph-token"),
        ):
            tools = build_direct_tool_catalog({})

        tool_ids = {tool.tool_id for tool in tools}
        self.assertIn("integration:aws:list_s3_buckets", tool_ids)
        self.assertIn("integration:gmail:read_inbox", tool_ids)
        self.assertIn("integration:google_drive:list_files", tool_ids)
        self.assertIn("integration:github:clone_repo", tool_ids)
        self.assertIn("integration:github:read_repo_file", tool_ids)
        self.assertIn("integration:github:get_repo", tool_ids)
        self.assertIn("integration:github:create_pull_request", tool_ids)
        self.assertIn("integration:slack:list_channels", tool_ids)
        self.assertIn("integration:microsoft_graph:list_files", tool_ids)

    def test_execute_direct_tool_runs_aws_integration(self):
        tool = DirectToolDefinition(
            tool_id="integration:aws:list_s3_buckets",
            kind="integration",
            name="List S3 Buckets",
            description="List S3 buckets.",
            metadata={"integration_id": "aws", "action": "list_s3_buckets"},
        )

        with (
            patch("tasks.aws_tasks._get_boto3_session", return_value=object()),
            patch(
                "tasks.aws_tasks._execute_allowed_operation",
                return_value={
                    "Buckets": [
                        {"Name": "alpha", "CreationDate": "2026-01-01T00:00:00Z"},
                        {"Name": "beta", "CreationDate": "2026-02-01T00:00:00Z"},
                    ]
                },
            ),
        ):
            result = execute_direct_tool({"aws_authorized": True}, tool, {})

        self.assertTrue(result.ok)
        self.assertEqual(result.output["buckets"][0]["name"], "alpha")
        self.assertIn("alpha", result.summary)

    def test_execute_direct_tool_requests_communication_approval(self):
        tool = DirectToolDefinition(
            tool_id="integration:slack:list_channels",
            kind="integration",
            name="List Slack Channels",
            description="List Slack channels.",
            metadata={"integration_id": "slack", "action": "list_channels"},
        )

        result = execute_direct_tool({"communication_authorized": False}, tool, {})

        self.assertFalse(result.ok)
        self.assertTrue(result.awaiting_input)
        self.assertEqual(result.error_code, "approval_required")
        self.assertEqual(result.state_updates["approval_pending_scope"], "integration_communication_access")

    def test_execute_direct_tool_runs_github_integration(self):
        tool = DirectToolDefinition(
            tool_id="integration:github:list_issues",
            kind="integration",
            name="List GitHub Issues",
            description="List GitHub issues.",
            metadata={"integration_id": "github", "action": "list_issues"},
        )

        with patch(
            "tasks.github_client.GitHubClient.list_issues",
            return_value=[{"number": 12, "title": "Fix regression"}],
        ):
            result = execute_direct_tool({}, tool, {"repo": "openai/sample", "state": "open", "per_page": 10})

        self.assertTrue(result.ok)
        self.assertEqual(result.output[0]["number"], 12)
        self.assertIn("Fix regression", result.summary)

    def test_execute_direct_tool_github_requires_repo_target(self):
        tool = DirectToolDefinition(
            tool_id="integration:github:get_repo",
            kind="integration",
            name="Get GitHub Repository",
            description="Get GitHub repo metadata.",
            metadata={"integration_id": "github", "action": "get_repo"},
        )

        result = execute_direct_tool({}, tool, {})

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "missing_github_repo")

    def test_execute_direct_tool_requests_github_local_git_approval(self):
        tool = DirectToolDefinition(
            tool_id="integration:github:write_repo_file",
            kind="integration",
            name="Write Repository File",
            description="Write a file in a local repo.",
            requires_approval=True,
            metadata={"integration_id": "github", "action": "write_repo_file"},
        )

        result = execute_direct_tool({}, tool, {"repo_dir": "repo", "path": "README.md", "content": "hello"})

        self.assertFalse(result.ok)
        self.assertTrue(result.awaiting_input)
        self.assertEqual(result.error_code, "approval_required")
        self.assertEqual(result.state_updates["approval_pending_scope"], "integration_github_local_git_access")

    def test_execute_direct_tool_requests_github_remote_git_approval(self):
        tool = DirectToolDefinition(
            tool_id="integration:github:push",
            kind="integration",
            name="Push Git Branch",
            description="Push git branch.",
            requires_approval=True,
            metadata={"integration_id": "github", "action": "push"},
        )

        result = execute_direct_tool({}, tool, {"repo_dir": "repo"})

        self.assertFalse(result.ok)
        self.assertTrue(result.awaiting_input)
        self.assertEqual(result.error_code, "approval_required")
        self.assertEqual(result.state_updates["approval_pending_scope"], "integration_github_remote_git_access")

    def test_execute_direct_tool_runs_github_read_repo_file(self):
        tool = DirectToolDefinition(
            tool_id="integration:github:read_repo_file",
            kind="integration",
            name="Read Repository File",
            description="Read a repository file.",
            metadata={"integration_id": "github", "action": "read_repo_file"},
        )

        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("tasks.github_client.GitHubClient.read_repo_file", return_value="hello world"),
        ):
            result = execute_direct_tool(
                {"working_directory": "/tmp/work"},
                tool,
                {"repo_dir": "repo", "path": "README.md"},
            )

        self.assertTrue(result.ok)
        self.assertEqual(result.output["content"], "hello world")
        self.assertIn("hello world", result.summary)

    def test_execute_direct_tool_runs_github_write_repo_file(self):
        tool = DirectToolDefinition(
            tool_id="integration:github:write_repo_file",
            kind="integration",
            name="Write Repository File",
            description="Write a repository file.",
            requires_approval=True,
            metadata={"integration_id": "github", "action": "write_repo_file"},
        )

        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("tasks.github_client.GitHubClient.write_repo_file") as mock_write,
        ):
            result = execute_direct_tool(
                {"working_directory": "/tmp/work", "github_local_git_authorized": True},
                tool,
                {"repo_dir": "repo", "path": "README.md", "content": "updated"},
            )

        self.assertTrue(result.ok)
        self.assertTrue(result.output["written"])
        self.assertTrue(mock_write.called)

    def test_execute_direct_tool_requests_github_write_approval(self):
        tool = DirectToolDefinition(
            tool_id="integration:github:create_pull_request",
            kind="integration",
            name="Create GitHub Pull Request",
            description="Create a PR.",
            requires_approval=True,
            metadata={"integration_id": "github", "action": "create_pull_request"},
        )

        result = execute_direct_tool({}, tool, {"repo": "openai/sample", "title": "Fix", "head": "feature"})

        self.assertFalse(result.ok)
        self.assertTrue(result.awaiting_input)
        self.assertEqual(result.error_code, "approval_required")
        self.assertEqual(result.state_updates["approval_pending_scope"], "integration_github_write_access")

    def test_execute_direct_tool_runs_github_create_pull_request(self):
        tool = DirectToolDefinition(
            tool_id="integration:github:create_pull_request",
            kind="integration",
            name="Create GitHub Pull Request",
            description="Create a PR.",
            requires_approval=True,
            metadata={"integration_id": "github", "action": "create_pull_request"},
        )

        with patch(
            "tasks.github_client.GitHubClient.create_pull_request",
            return_value={"html_url": "https://github.com/openai/sample/pull/15", "number": 15},
        ):
            result = execute_direct_tool(
                {"github_write_authorized": True},
                tool,
                {"repo": "openai/sample", "title": "Fix regression", "head": "feature/fix", "base": "main"},
            )

        self.assertTrue(result.ok)
        self.assertEqual(result.output["number"], 15)
        self.assertIn("pull/15", result.summary)
