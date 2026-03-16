# coding: utf-8
"""Mobilecli wrapper - executes @mobilenext/mobilecli via npx (auto-download)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from typing import Any


@dataclass
class DeviceInfo:
    id: str
    name: str
    platform: str  # "ios" or "android"
    type: str  # "real", "emulator", "simulator"
    version: str = ""


class MobilecliError(Exception):
    """Error from mobilecli."""
    pass


class Mobilecli:
    """Executes mobilecli commands via npx. No pre-install required."""

    def _cmd_prefix(self) -> list[str]:
        """Return the command prefix for mobilecli.

        Uses MOBILECLI_PATH if set, otherwise npx auto-downloads.
        """
        env_path = os.environ.get("MOBILECLI_PATH")
        if env_path and os.path.isfile(env_path):
            return [env_path]
        return ["npx", "-y", "@mobilenext/mobilecli"]

    def execute(self, args: list[str], timeout: int = 30) -> str:
        """Execute mobilecli command and return stdout as string."""
        cmd = self._cmd_prefix() + args
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            if result.returncode != 0:
                raise MobilecliError(
                    f"mobilecli {' '.join(args)} failed: {result.stderr.strip()}"
                )
            return result.stdout.strip()
        except subprocess.TimeoutExpired:
            raise MobilecliError(f"mobilecli {' '.join(args)} timed out after {timeout}s")
        except FileNotFoundError:
            raise MobilecliError(
                "npx not found. Please install Node.js: https://nodejs.org/"
            )

    def execute_buffer(self, args: list[str], timeout: int = 30) -> bytes:
        """Execute mobilecli command and return stdout as bytes."""
        cmd = self._cmd_prefix() + args
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=timeout,
            )
            if result.returncode != 0:
                raise MobilecliError(
                    f"mobilecli {' '.join(args)} failed: {result.stderr.decode(errors='replace').strip()}"
                )
            return result.stdout
        except subprocess.TimeoutExpired:
            raise MobilecliError(f"mobilecli {' '.join(args)} timed out after {timeout}s")
        except FileNotFoundError:
            raise MobilecliError(
                "npx not found. Please install Node.js: https://nodejs.org/"
            )

    def get_version(self) -> str:
        """Get mobilecli version."""
        return self.execute(["--version"])

    def get_devices(
        self,
        platform_filter: str | None = None,
        type_filter: str | None = None,
        include_offline: bool = False,
    ) -> list[DeviceInfo]:
        """List available devices."""
        args = ["devices"]
        if include_offline:
            args.append("--include-offline")
        if platform_filter:
            args.extend(["--platform", platform_filter])
        if type_filter:
            args.extend(["--type", type_filter])

        output = self.execute(args)
        try:
            data = json.loads(output)
            devices = data.get("data", {}).get("devices", [])
            return [
                DeviceInfo(
                    id=d.get("id", ""),
                    name=d.get("name", ""),
                    platform=d.get("platform", ""),
                    type=d.get("type", ""),
                    version=d.get("version", ""),
                )
                for d in devices
            ]
        except (json.JSONDecodeError, KeyError) as e:
            raise MobilecliError(f"Failed to parse device list: {e}\nOutput: {output}")


# Global instance
_mobilecli: Mobilecli | None = None


def get_mobilecli() -> Mobilecli:
    """Get or create the global mobilecli instance."""
    global _mobilecli
    if _mobilecli is None:
        _mobilecli = Mobilecli()
    return _mobilecli
