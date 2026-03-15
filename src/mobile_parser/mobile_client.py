# coding: utf-8
"""MCP Client that connects to mobile-mcp as an internal subprocess."""

from __future__ import annotations

import logging
from contextlib import AsyncExitStack
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

logger = logging.getLogger(__name__)


class MobileClient:
    """Manages a mobile-mcp subprocess and proxies tool calls to it."""

    def __init__(self) -> None:
        self._session: ClientSession | None = None
        self._exit_stack: AsyncExitStack | None = None

    @property
    def is_connected(self) -> bool:
        return self._session is not None

    async def start(self) -> None:
        """Start the mobile-mcp subprocess and establish MCP connection."""
        if self._session is not None:
            return

        params = StdioServerParameters(
            command="npx",
            args=["-y", "@mobilenext/mobile-mcp@latest"],
        )

        self._exit_stack = AsyncExitStack()
        try:
            transport = await self._exit_stack.enter_async_context(
                stdio_client(params)
            )
            read, write = transport
            session = await self._exit_stack.enter_async_context(
                ClientSession(read, write)
            )
            await session.initialize()
            self._session = session
            logger.info("mobile-mcp connected")
        except Exception:
            await self._exit_stack.aclose()
            self._exit_stack = None
            raise

    async def stop(self) -> None:
        """Shut down the mobile-mcp subprocess."""
        if self._exit_stack is not None:
            await self._exit_stack.aclose()
            self._exit_stack = None
            self._session = None
            logger.info("mobile-mcp disconnected")

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        """Call a tool on the mobile-mcp server.

        Returns the result object from the MCP call_tool response.
        """
        if self._session is None:
            raise RuntimeError("mobile-mcp is not connected. Call start() first.")
        return await self._session.call_tool(name, arguments)
