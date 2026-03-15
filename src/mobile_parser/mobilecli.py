# coding: utf-8
"""Mobilecli binary wrapper - finds and executes the @mobilenext/mobilecli binary."""

from __future__ import annotations

import json
import os
import platform
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
    """Error from mobilecli binary."""
    pass


class Mobilecli:
    """Wrapper around the @mobilenext/mobilecli binary."""

    def __init__(self) -> None:
        self._binary_path: str | None = None

    @property
    def binary_path(self) -> str:
        if self._binary_path is None:
            self._binary_path = self._find_binary()
        return self._binary_path

    def _find_binary(self) -> str:
        """Find the mobilecli binary, matching mobile-mcp's resolution logic."""
        # 1. Environment variable
        env_path = os.environ.get("MOBILECLI_PATH")
        if env_path and os.path.isfile(env_path):
            return env_path

        # 2. Determine platform and architecture
        system = platform.system().lower()
        if system == "darwin":
            plat = "darwin"
        elif system == "linux":
            plat = "linux"
        elif system == "windows":
            plat = "windows"
        else:
            plat = system

        machine = platform.machine().lower()
        if machine in ("arm64", "aarch64"):
            arch = "arm64"
        else:
            arch = "amd64"

        ext = ".exe" if plat == "windows" else ""
        binary_name = f"mobilecli-{plat}-{arch}{ext}"

        # 3. Try to find via npx/npm global
        search_paths = []

        # Check if @mobilenext/mobilecli is installed globally or locally
        try:
            result = subprocess.run(
                ["npm", "root", "-g"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                global_path = os.path.join(
                    result.stdout.strip(),
                    "@mobilenext", "mobilecli", "bin", binary_name
                )
                search_paths.append(global_path)
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        # Check local node_modules
        cwd = os.getcwd()
        local_path = os.path.join(
            cwd, "node_modules", "@mobilenext", "mobilecli", "bin", binary_name
        )
        search_paths.append(local_path)

        # Check relative to this script
        script_dir = os.path.dirname(os.path.abspath(__file__))
        for parent in [script_dir, os.path.dirname(script_dir), os.path.dirname(os.path.dirname(script_dir))]:
            candidate = os.path.join(
                parent, "node_modules", "@mobilenext", "mobilecli", "bin", binary_name
            )
            search_paths.append(candidate)

        for path in search_paths:
            if os.path.isfile(path):
                os.chmod(path, 0o755)
                return path

        # 4. Try installing via npx
        try:
            result = subprocess.run(
                ["npx", "-y", "@mobilenext/mobilecli", "--version"],
                capture_output=True, text=True, timeout=60
            )
            if result.returncode == 0:
                # npx installed it, now find the binary
                npm_cache_result = subprocess.run(
                    ["npm", "root", "-g"],
                    capture_output=True, text=True, timeout=10
                )
                if npm_cache_result.returncode == 0:
                    global_path = os.path.join(
                        npm_cache_result.stdout.strip(),
                        "@mobilenext", "mobilecli", "bin", binary_name
                    )
                    if os.path.isfile(global_path):
                        os.chmod(global_path, 0o755)
                        return global_path
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        raise MobilecliError(
            f"mobilecli binary not found. Install it with: npm install -g @mobilenext/mobilecli\n"
            f"Or set MOBILECLI_PATH environment variable.\n"
            f"Searched for: {binary_name}"
        )

    def execute(self, args: list[str], timeout: int = 30) -> str:
        """Execute mobilecli command and return stdout as string."""
        cmd = [self.binary_path] + args
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

    def execute_buffer(self, args: list[str], timeout: int = 30) -> bytes:
        """Execute mobilecli command and return stdout as bytes."""
        cmd = [self.binary_path] + args
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
