"""Modular discovery connectors. Add a source = add one class implementing SourceConnector."""
from job_agent.connectors.base import CONNECTOR_TYPES, SourceConnector, build_connector

# Import concrete connectors so their @register decorators populate CONNECTOR_TYPES.
from job_agent.connectors import ats_api, github_list, linkedin_supervised  # noqa: E402,F401

__all__ = ["CONNECTOR_TYPES", "SourceConnector", "build_connector"]
