"""Integration registry for external service connections.

This module is the canonical surface for static service integrations such as
Slack, GitHub, Gmail, or AWS. These integrations are distinct from runtime
plugins, which are packaged code extensions discovered by ``kendr.discovery``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class IntegrationAction:
    """A single raw action exposed by an integration."""

    name: str
    description: str
    required_inputs: tuple[str, ...] = ()


@dataclass(frozen=True)
class IntegrationCard:
    """Describes an external service integration and its raw capabilities."""

    id: str
    name: str
    description: str
    icon: str
    category: str
    required_env_vars: tuple[str, ...]
    actions: tuple[IntegrationAction, ...] = field(default_factory=tuple)
    docs_url: str = ""

    @property
    def is_configured(self) -> bool:
        return all(os.environ.get(v, "").strip() for v in self.required_env_vars)

    @property
    def missing_vars(self) -> list[str]:
        return [v for v in self.required_env_vars if not os.environ.get(v, "").strip()]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "icon": self.icon,
            "category": self.category,
            "required_env_vars": list(self.required_env_vars),
            "missing_vars": self.missing_vars,
            "is_configured": self.is_configured,
            "docs_url": self.docs_url,
            "actions": [
                {"name": action.name, "description": action.description, "required_inputs": list(action.required_inputs)}
                for action in self.actions
            ],
        }


_INTEGRATIONS: tuple[IntegrationCard, ...] = (
    IntegrationCard(
        id="slack",
        name="Slack",
        description="Connect to Slack workspaces. Read and send messages, post to channels, listen to events.",
        icon="💬",
        category="Communications",
        required_env_vars=("SLACK_BOT_TOKEN",),
        docs_url="https://api.slack.com/",
        actions=(
            IntegrationAction("send_message", "Post a message to a channel or user", ("channel", "text")),
            IntegrationAction("read_messages", "Fetch recent messages from a channel", ("channel",)),
            IntegrationAction("get_channel", "Get channel info by name or ID", ("channel",)),
            IntegrationAction("list_channels", "List all accessible channels"),
        ),
    ),
    IntegrationCard(
        id="whatsapp",
        name="WhatsApp",
        description="Send and receive WhatsApp messages via the WhatsApp Business API.",
        icon="📱",
        category="Communications",
        required_env_vars=("WHATSAPP_ACCESS_TOKEN",),
        actions=(IntegrationAction("send_message", "Send a WhatsApp message", ("to", "text")),),
    ),
    IntegrationCard(
        id="telegram",
        name="Telegram",
        description="Send messages and manage Telegram bots.",
        icon="✈️",
        category="Communications",
        required_env_vars=("TELEGRAM_BOT_TOKEN",),
        actions=(IntegrationAction("send_message", "Send a Telegram message", ("chat_id", "text")),),
    ),
    IntegrationCard(
        id="gmail",
        name="Gmail",
        description="Read and send emails via Gmail. Supports OAuth 2.0.",
        icon="📧",
        category="Communications",
        required_env_vars=("GMAIL_CLIENT_ID",),
        docs_url="https://developers.google.com/gmail/api",
        actions=(
            IntegrationAction("send_email", "Send an email", ("to", "subject", "body")),
            IntegrationAction("read_inbox", "Read recent inbox messages", ("max_results",)),
            IntegrationAction("search_emails", "Search emails by query", ("query",)),
        ),
    ),
    IntegrationCard(
        id="github",
        name="GitHub",
        description="Interact with GitHub repositories. Manage issues, pull requests, files, and branches.",
        icon="🐙",
        category="Development",
        required_env_vars=("GITHUB_TOKEN",),
        docs_url="https://docs.github.com/en/rest",
        actions=(
            IntegrationAction("list_issues", "List issues in a repository", ("repo",)),
            IntegrationAction("create_issue", "Create a new issue", ("repo", "title", "body")),
            IntegrationAction("get_file", "Read a file from a repository", ("repo", "path")),
            IntegrationAction("list_prs", "List pull requests", ("repo",)),
            IntegrationAction("create_pr", "Open a pull request", ("repo", "title", "head", "base")),
            IntegrationAction("add_comment", "Comment on an issue or PR", ("repo", "number", "body")),
        ),
    ),
    IntegrationCard(
        id="google_drive",
        name="Google Drive",
        description="Access and manage files in Google Drive. Upload, download, list, and share documents.",
        icon="📁",
        category="Productivity",
        required_env_vars=("GOOGLE_DRIVE_CLIENT_ID",),
        docs_url="https://developers.google.com/drive/api",
        actions=(
            IntegrationAction("list_files", "List files in Drive or a folder", ("folder_id",)),
            IntegrationAction("get_file", "Download a file by ID", ("file_id",)),
            IntegrationAction("upload_file", "Upload a file to Drive", ("file_path", "name")),
            IntegrationAction("create_folder", "Create a new folder", ("name",)),
        ),
    ),
    IntegrationCard(
        id="microsoft_graph",
        name="Microsoft 365",
        description="Connect to Microsoft 365 services: Outlook, OneDrive, Teams, and SharePoint.",
        icon="🪟",
        category="Productivity",
        required_env_vars=("MICROSOFT_CLIENT_ID",),
        docs_url="https://learn.microsoft.com/en-us/graph/",
        actions=(
            IntegrationAction("send_email", "Send an Outlook email", ("to", "subject", "body")),
            IntegrationAction("list_files", "List OneDrive files", ("folder_id",)),
            IntegrationAction("get_file", "Download a OneDrive file", ("file_id",)),
        ),
    ),
    IntegrationCard(
        id="aws",
        name="AWS",
        description="Interact with Amazon Web Services: EC2, S3, Lambda, IAM, and more.",
        icon="☁️",
        category="Cloud",
        required_env_vars=("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"),
        docs_url="https://docs.aws.amazon.com/",
        actions=(
            IntegrationAction("list_s3_buckets", "List S3 buckets"),
            IntegrationAction("invoke_lambda", "Invoke a Lambda function", ("function_name", "payload")),
            IntegrationAction("describe_ec2", "Describe EC2 instances", ("region",)),
        ),
    ),
    IntegrationCard(
        id="qdrant",
        name="Qdrant",
        description="Connect to a Qdrant vector database for semantic search and RAG pipelines.",
        icon="🗄️",
        category="Data",
        required_env_vars=("QDRANT_URL",),
        docs_url="https://qdrant.tech/documentation/",
        actions=(
            IntegrationAction("search", "Semantic vector search", ("collection", "query")),
            IntegrationAction("upsert", "Insert or update vectors", ("collection", "vectors")),
            IntegrationAction("delete", "Delete vectors by ID", ("collection", "ids")),
        ),
    ),
    IntegrationCard(
        id="elevenlabs",
        name="ElevenLabs",
        description="Text-to-speech synthesis using ElevenLabs AI voices.",
        icon="🔊",
        category="Media",
        required_env_vars=("ELEVENLABS_API_KEY",),
        docs_url="https://docs.elevenlabs.io/",
        actions=(
            IntegrationAction("synthesize", "Convert text to speech", ("text", "voice_id")),
            IntegrationAction("list_voices", "List available voices"),
        ),
    ),
    IntegrationCard(
        id="serpapi",
        name="SerpAPI",
        description="Perform web searches via SerpAPI (Google, Bing, DuckDuckGo).",
        icon="🔍",
        category="Research",
        required_env_vars=("SERPAPI_API_KEY",),
        docs_url="https://serpapi.com/",
        actions=(IntegrationAction("search", "Run a web search", ("query", "engine")),),
    ),
    IntegrationCard(
        id="nmap",
        name="Nmap",
        description="Network scanning and security auditing via the Nmap tool.",
        icon="🔒",
        category="Security",
        required_env_vars=("NMAP_PATH",),
        actions=(IntegrationAction("scan", "Run an Nmap network scan", ("target", "flags")),),
    ),
    IntegrationCard(
        id="zap",
        name="OWASP ZAP",
        description="Web application security scanning via OWASP ZAP.",
        icon="🕷️",
        category="Security",
        required_env_vars=("ZAP_API_KEY",),
        actions=(IntegrationAction("scan", "Run a ZAP security scan", ("target_url",)),),
    ),
)

INTEGRATION_REGISTRY: dict[str, IntegrationCard] = {integration.id: integration for integration in _INTEGRATIONS}

# Maps agent-name prefix → (integration_id, required_env_vars)
AGENT_INTEGRATION_MAP: dict[str, tuple[str, tuple[str, ...]]] = {
    "slack_": ("slack", ("SLACK_BOT_TOKEN",)),
    "whatsapp_": ("whatsapp", ("WHATSAPP_ACCESS_TOKEN",)),
    "telegram_": ("telegram", ("TELEGRAM_BOT_TOKEN",)),
    "github_": ("github", ("GITHUB_TOKEN",)),
    "aws_": ("aws", ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY")),
    "qdrant_": ("qdrant", ("QDRANT_URL",)),
    "elevenlabs_": ("elevenlabs", ("ELEVENLABS_API_KEY",)),
    "serpapi_": ("serpapi", ("SERPAPI_API_KEY",)),
    "gmail_": ("gmail", ("GMAIL_CLIENT_ID",)),
    "google_drive_": ("google_drive", ("GOOGLE_DRIVE_CLIENT_ID",)),
    "microsoft_": ("microsoft_graph", ("MICROSOFT_CLIENT_ID",)),
    "onedrive_": ("microsoft_graph", ("MICROSOFT_CLIENT_ID",)),
    "nmap_": ("nmap", ("NMAP_PATH",)),
    "zap_": ("zap", ("ZAP_API_KEY",)),
}


def check_agent_integration_config(
    agent_name: str,
    existing_config_hint: str = "",
) -> tuple[str, list[str], bool, str]:
    """Check whether the agent depends on an integration and whether it is configured."""

    name_lower = agent_name.lower()
    for prefix, (integration_id, required_vars) in AGENT_INTEGRATION_MAP.items():
        if name_lower.startswith(prefix):
            missing = [value for value in required_vars if not os.environ.get(value, "").strip()]
            if missing:
                hint = existing_config_hint or (
                    f"Requires {integration_id} credentials. "
                    f"Set {', '.join(missing)} in Setup & Config."
                )
                return integration_id, missing, True, hint
            return integration_id, [], False, existing_config_hint
    return "", [], False, existing_config_hint


def list_integrations(category: str = "") -> list[IntegrationCard]:
    """Return all integrations, optionally filtered by category."""

    if not category:
        return list(_INTEGRATIONS)
    return [integration for integration in _INTEGRATIONS if integration.category == category]


def list_configured_integrations() -> list[IntegrationCard]:
    """Return only integrations whose required env vars are all present."""

    return [integration for integration in _INTEGRATIONS if integration.is_configured]


def list_unconfigured_integrations() -> list[IntegrationCard]:
    """Return integrations that are missing at least one required credential."""

    return [integration for integration in _INTEGRATIONS if not integration.is_configured]


def get_integration(integration_id: str) -> IntegrationCard | None:
    """Look up an integration by its ID."""

    return INTEGRATION_REGISTRY.get(integration_id)


def integration_categories() -> list[str]:
    seen: dict[str, None] = {}
    for integration in _INTEGRATIONS:
        seen[integration.category] = None
    return list(seen.keys())
