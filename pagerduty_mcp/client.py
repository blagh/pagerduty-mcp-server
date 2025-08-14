import logging
import os
from contextvars import ContextVar
from functools import lru_cache
from importlib import metadata

import pagerduty
from dotenv import load_dotenv
from pydantic import BaseModel

from pagerduty_mcp import DIST_NAME

from pagerduty.rest_api_v2_client import RestApiV2Client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

API_KEY = os.getenv("PAGERDUTY_USER_API_KEY")
API_HOST = os.getenv("PAGERDUTY_API_HOST", "https://api.pagerduty.com")

class AuthMethod(BaseModel):
    api_key: str
    api_host: str = "https://api.pagerduty.com"
    auth_method: str = "api_key"

    def auth_header(self) -> dict[str, str]:
        return {"Authorization": f"Token token={self.api_key}"}

    def get_credential(self) -> str:
        return self.api_key

class PagerdutyMCPClient(RestApiV2Client):
    def __init__(self, auth_method: AuthMethod):
        self.auth_method = auth_method

        super().__init__(auth_method.get_credential())

    @property
    def auth_header(self) -> dict[str, str]:
        return self.auth_method.auth_header()

    @property
    def user_agent(self) -> str:
        return f"{DIST_NAME}/{metadata.version(DIST_NAME)} {super().user_agent}"

pd_client_config: ContextVar[AuthMethod | None] = ContextVar("pd_auth_method", default=None)


@lru_cache(maxsize=1)
def _get_cached_client(auth_method: AuthMethod) -> RestApiV2Client:
    """Get a cached PagerDuty client."""
    return create_pd_client(auth_method)


def create_pd_client(auth_method: AuthMethod) -> RestApiV2Client:
    """Get the PagerDuty client."""
    pd_client = PagerdutyMCPClient(auth_method)
    if auth_method.api_host:
        pd_client.url = auth_method.api_host

    return pd_client


def get_client() -> RestApiV2Client:
    """Get the PagerDuty client, using cached configuration if available.

    This function will check if client config information is stored in a context var.
    If it is, that means the package is being used in a remote MCP server context, and
    we need to update the client credentials for each request, since remote MCP servers
    need to support multi tenancy.
    """

    client_config: AuthMethod | None = None

    if API_KEY is not None:
        client_config = AuthMethod(api_key=API_KEY, api_host=API_HOST)
    elif client_config := pd_client_config.get():
        pass

    if client_config is None:
        raise ValueError("PagerDuty API key is not set. Please set the PAGERDUTY_USER_API_KEY environment variable or provide client config via context variables.")

    logger.info(f"Authorization with PagerDuty API using #{client_config.auth_method}")

    client = _get_cached_client(client_config)

    logger.info(f"Using PagerDuty client with API key: {client_config.api_key}")
    return client
