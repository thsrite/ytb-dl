import subprocess
import sys
import json
import logging
from typing import Dict, Any, Optional
import httpx
import yt_dlp
from packaging import version

logger = logging.getLogger(__name__)


class YtDlpUpdater:
    """Handle yt-dlp version checking and updates"""

    GITHUB_API_URL = "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest"

    def __init__(self):
        self.current_version = yt_dlp.version.__version__

    async def check_for_updates(self) -> Dict[str, Any]:
        """Check if a new version of yt-dlp is available"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(self.GITHUB_API_URL)
                response.raise_for_status()

                latest_release = response.json()
                latest_version = latest_release['tag_name']

                # Remove 'v' prefix if present
                if latest_version.startswith('v'):
                    latest_version = latest_version[1:]

                # Compare versions
                current = version.parse(self.current_version)
                latest = version.parse(latest_version)

                update_available = latest > current

                return {
                    "current_version": self.current_version,
                    "latest_version": latest_version,
                    "update_available": update_available,
                    "release_notes": latest_release.get('body', ''),
                    "release_date": latest_release.get('published_at', ''),
                    "download_url": latest_release.get('html_url', '')
                }

        except httpx.HTTPError as e:
            logger.error(f"Failed to check for updates: {e}")
            return {
                "current_version": self.current_version,
                "error": f"Failed to check for updates: {str(e)}",
                "update_available": False
            }
        except Exception as e:
            logger.error(f"Unexpected error checking for updates: {e}")
            return {
                "current_version": self.current_version,
                "error": f"Unexpected error: {str(e)}",
                "update_available": False
            }

    def update_yt_dlp(self) -> Dict[str, Any]:
        """Update yt-dlp to the latest version"""
        try:
            # Use pip to update yt-dlp
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp"],
                capture_output=True,
                text=True,
                timeout=60
            )

            if result.returncode == 0:
                # Reload the module to get the new version
                import importlib
                importlib.reload(yt_dlp.version)
                new_version = yt_dlp.version.__version__

                return {
                    "success": True,
                    "message": "yt-dlp updated successfully",
                    "old_version": self.current_version,
                    "new_version": new_version,
                    "output": result.stdout
                }
            else:
                return {
                    "success": False,
                    "message": "Failed to update yt-dlp",
                    "error": result.stderr,
                    "output": result.stdout
                }

        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "message": "Update operation timed out",
                "error": "The update process took too long and was terminated"
            }
        except Exception as e:
            logger.error(f"Failed to update yt-dlp: {e}")
            return {
                "success": False,
                "message": "Failed to update yt-dlp",
                "error": str(e)
            }

    async def get_version_info(self) -> Dict[str, Any]:
        """Get detailed version information"""
        try:
            # Get Python version
            python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"

            # Get pip version
            pip_result = subprocess.run(
                [sys.executable, "-m", "pip", "--version"],
                capture_output=True,
                text=True
            )
            pip_version = pip_result.stdout.split()[1] if pip_result.returncode == 0 else "Unknown"

            # Check for updates
            update_info = await self.check_for_updates()

            return {
                "yt_dlp_version": self.current_version,
                "python_version": python_version,
                "pip_version": pip_version,
                "update_info": update_info
            }

        except Exception as e:
            logger.error(f"Failed to get version info: {e}")
            return {
                "yt_dlp_version": self.current_version,
                "error": str(e)
            }