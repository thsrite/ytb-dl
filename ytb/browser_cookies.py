"""
Browser cookie extraction module for yt-dlp
Handles automatic cookie extraction from browsers to solve 403 errors
"""

import os
import json
import logging
import tempfile
import platform
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timedelta
import subprocess
from .cookiecloud import CookieCloud

logger = logging.getLogger(__name__)


class BrowserCookieExtractor:
    """Extract cookies from browsers for yt-dlp"""

    SUPPORTED_BROWSERS = ['firefox', 'chrome', 'chromium', 'edge', 'safari', 'brave', 'opera']

    def __init__(self, config_dir: str = None, cookiecloud_config: Dict = None):
        self.last_extraction_time = None
        self.cached_cookies = None
        self.browser_user_agent = None
        self.refresh_interval = timedelta(minutes=25)  # Refresh every 25 minutes (before 30 min expiry)

        # Set config directory for persistent storage
        if config_dir:
            self.config_dir = config_dir
        elif os.path.exists("/app"):
            self.config_dir = "/app/config"
        else:
            self.config_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config")

        # Ensure config directory exists
        os.makedirs(self.config_dir, exist_ok=True)

        # Paths for persistent storage
        self.cookies_file = os.path.join(self.config_dir, "browser_cookies.txt")
        self.metadata_file = os.path.join(self.config_dir, "browser_cookies_meta.json")

        # Check for Cookie Bridge URL (for Docker environments)
        self.cookie_bridge_url = os.environ.get('COOKIE_BRIDGE_URL')
        self.is_docker = os.path.exists("/app")

        # Initialize CookieCloud if config provided
        self.cookiecloud = None
        if cookiecloud_config and cookiecloud_config.get('enabled'):
            self.cookiecloud = CookieCloud(cookiecloud_config)
            self.cookiecloud_auto_sync = cookiecloud_config.get('auto_sync', True)
            self.cookiecloud_sync_interval = timedelta(
                minutes=cookiecloud_config.get('sync_interval_minutes', 30)
            )
            self.last_cookiecloud_sync = None

        # Load cached cookies from disk if available
        self.load_cached_cookies()

    def get_system_info(self) -> Dict[str, str]:
        """Get system information for debugging"""
        return {
            'platform': platform.system(),
            'platform_version': platform.version(),
            'python_version': platform.python_version(),
        }

    def detect_available_browsers(self) -> List[str]:
        """Detect which browsers are installed on the system"""
        available = []
        system = platform.system()

        if system == "Darwin":  # macOS
            browser_paths = {
                'firefox': '/Applications/Firefox.app',
                'chrome': '/Applications/Google Chrome.app',
                'safari': '/Applications/Safari.app',
                'brave': '/Applications/Brave Browser.app',
                'edge': '/Applications/Microsoft Edge.app',
            }
        elif system == "Windows":
            browser_paths = {
                'firefox': r'C:\Program Files\Mozilla Firefox\firefox.exe',
                'chrome': r'C:\Program Files\Google\Chrome\Application\chrome.exe',
                'edge': r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
                'brave': r'C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe',
            }
        else:  # Linux
            browser_paths = {
                'firefox': 'firefox',
                'chrome': 'google-chrome',
                'chromium': 'chromium',
                'brave': 'brave-browser',
            }

        for browser, path in browser_paths.items():
            if system == "Linux":
                # Check if command exists
                result = subprocess.run(['which', path], capture_output=True, text=True)
                if result.returncode == 0:
                    available.append(browser)
            else:
                # Check if file/directory exists
                if os.path.exists(path):
                    available.append(browser)

        return available

    def get_browser_user_agent(self, browser: str) -> Optional[str]:
        """Get the user agent string for the specified browser"""
        user_agents = {
            'firefox': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
            'chrome': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'edge': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0',
            'safari': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 14_2_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15',
            'brave': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        }

        # Adjust user agent based on actual platform
        system = platform.system()
        if system == "Darwin" and browser != 'safari':
            # Mac versions of browsers
            user_agents['firefox'] = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 14.2) Gecko/20100101 Firefox/121.0'
            user_agents['chrome'] = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'

        return user_agents.get(browser)

    def extract_cookies_from_browser(self, browser: str = 'firefox', domain: str = 'youtube.com') -> Optional[Dict[str, Any]]:
        """
        Extract cookies from browser using yt-dlp's Python API

        Args:
            browser: Browser name (firefox, chrome, edge, etc.)
            domain: Domain to extract cookies for

        Returns:
            Dict with cookies and metadata or None if failed
        """
        try:
            # Try CookieCloud sync first if enabled and needed
            if self.cookiecloud and self.cookiecloud_auto_sync and self.should_refresh():
                logger.info("Attempting CookieCloud sync...")
                success, message = self.sync_cookiecloud()
                if success:
                    # Return the synced cookies
                    return {
                        'cookies': self.cached_cookies,
                        'source': 'cookiecloud',
                        'extracted_at': self.last_extraction_time.isoformat(),
                        'message': message
                    }
                else:
                    logger.warning(f"CookieCloud sync failed: {message}, falling back to browser extraction")

            # Check if we need to refresh
            if self.should_refresh():
                logger.info(f"Extracting cookies from {browser} for domain {domain}")

                # Create temporary file for cookies
                with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as tmp_file:
                    cookie_file = tmp_file.name

                # Use yt-dlp Python API to extract cookies
                import yt_dlp

                ydl_opts = {
                    'cookiesfrombrowser': (browser, None),
                    'cookiefile': cookie_file,
                    'quiet': True,
                    'no_warnings': True,
                    'extract_flat': True,
                }

                try:
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        # Extract cookies by processing a YouTube URL
                        # This will trigger cookie extraction without downloading
                        ydl.extract_info(f'https://www.{domain}/', download=False)

                    # Check if cookies were saved
                    if os.path.exists(cookie_file) and os.path.getsize(cookie_file) > 0:
                        # Read the cookies file
                        with open(cookie_file, 'r') as f:
                            cookies_content = f.read()

                        # Clean up temp file
                        os.unlink(cookie_file)

                        # Validate cookies
                        if not self.validate_cookies(cookies_content):
                            logger.error("Invalid cookie format")
                            return None

                        # Update cache
                        self.cached_cookies = cookies_content
                        self.last_extraction_time = datetime.now()
                        self.browser_user_agent = self.get_browser_user_agent(browser)

                        cookies_data = {
                            'cookies': cookies_content,
                            'browser': browser,
                            'user_agent': self.browser_user_agent,
                            'extracted_at': self.last_extraction_time.isoformat(),
                            'domain': domain
                        }

                        # Save to disk for persistence
                        self.save_cached_cookies(cookies_data)

                        logger.info(f"Successfully extracted cookies from {browser}")
                        return cookies_data
                    else:
                        logger.error(f"No cookies were extracted from {browser}")
                        if os.path.exists(cookie_file):
                            os.unlink(cookie_file)
                        return None

                except yt_dlp.utils.DownloadError as e:
                    logger.error(f"yt-dlp error: {e}")
                    if os.path.exists(cookie_file):
                        os.unlink(cookie_file)

                    # Try alternative method: direct browser cookie reading
                    logger.info(f"Trying alternative cookie extraction method for {browser}")
                    return self.extract_cookies_alternative(browser, domain)

                except Exception as e:
                    logger.error(f"Failed to extract cookies: {e}")
                    if os.path.exists(cookie_file):
                        os.unlink(cookie_file)
                    return None

            else:
                # Return cached cookies
                logger.info("Using cached cookies")
                return {
                    'cookies': self.cached_cookies,
                    'browser': browser,
                    'user_agent': self.browser_user_agent,
                    'extracted_at': self.last_extraction_time.isoformat() if self.last_extraction_time else None,
                    'domain': domain
                }

        except subprocess.TimeoutExpired:
            logger.error("Cookie extraction timed out")
            return None
        except Exception as e:
            logger.error(f"Error extracting cookies: {e}")
            return None

    def should_refresh(self) -> bool:
        """Check if cookies should be refreshed"""
        # Check CookieCloud sync first if enabled
        if self.cookiecloud and self.cookiecloud_auto_sync:
            if not self.last_cookiecloud_sync:
                return True
            time_since_sync = datetime.now() - self.last_cookiecloud_sync
            if time_since_sync > self.cookiecloud_sync_interval:
                return True

        if not self.last_extraction_time or not self.cached_cookies:
            return True

        time_since_extraction = datetime.now() - self.last_extraction_time
        return time_since_extraction > self.refresh_interval

    def get_ydl_opts_with_browser_cookies(self, browser: str = 'firefox',
                                          base_opts: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Get yt-dlp options configured with browser cookies

        Args:
            browser: Browser to extract cookies from
            base_opts: Base options to extend

        Returns:
            yt-dlp options dict with cookie configuration
        """
        opts = base_opts or {}

        # Add browser cookie extraction
        opts['cookiesfrombrowser'] = (browser, None)

        # Add user agent
        user_agent = self.get_browser_user_agent(browser)
        if user_agent:
            opts['user_agent'] = user_agent

        # Add other recommended options for avoiding 403
        opts.update({
            'nocheckcertificate': True,
            'geo_bypass': True,
            'no_warnings': True,
            'quiet': True,
        })

        return opts

    def save_cookies_to_file(self, cookies_content: str, filepath: str) -> bool:
        """Save cookies to a file in Netscape format"""
        try:
            # Ensure proper header
            if not cookies_content.startswith('# Netscape HTTP Cookie File'):
                cookies_content = '# Netscape HTTP Cookie File\n' + cookies_content

            with open(filepath, 'w') as f:
                f.write(cookies_content)

            logger.info(f"Cookies saved to {filepath}")
            return True
        except Exception as e:
            logger.error(f"Failed to save cookies: {e}")
            return False

    def validate_cookies(self, cookies_content: str) -> bool:
        """Validate that cookies are in correct format"""
        lines = cookies_content.strip().split('\n')

        # Check header
        if not lines[0].startswith('# Netscape HTTP Cookie File') and \
           not lines[0].startswith('# HTTP Cookie File'):
            return False

        # Check that we have actual cookie entries
        cookie_lines = [l for l in lines if l and not l.startswith('#')]
        if len(cookie_lines) == 0:
            return False

        # Basic format check for cookie lines (should have 7 fields)
        for line in cookie_lines:
            parts = line.split('\t')
            if len(parts) != 7:
                return False

        return True

    def handle_403_error(self, browser: str = 'firefox') -> Optional[Dict[str, Any]]:
        """
        Handle 403 error by refreshing cookies

        Returns:
            New cookie configuration or None if failed
        """
        logger.info("Handling 403 error - forcing cookie refresh")

        # Force refresh
        self.last_extraction_time = None
        self.cached_cookies = None

        # Extract fresh cookies
        result = self.extract_cookies_from_browser(browser)

        if result:
            logger.info("Successfully refreshed cookies after 403 error")
        else:
            logger.error("Failed to refresh cookies for 403 error")

        return result

    def extract_cookies_alternative(self, browser: str, domain: str = 'youtube.com') -> Optional[Dict[str, Any]]:
        """
        Alternative method to extract cookies using browser_cookie3 library

        Args:
            browser: Browser name
            domain: Domain to extract cookies for

        Returns:
            Cookie data or None if failed
        """
        try:
            # Try using browser_cookie3 if available
            try:
                import browser_cookie3
            except ImportError:
                logger.info("browser_cookie3 not available, trying built-in method")
                return self.extract_cookies_builtin(browser, domain)

            # Get cookies based on browser
            if browser.lower() == 'firefox':
                cookies = browser_cookie3.firefox(domain_name=domain)
            elif browser.lower() == 'chrome':
                cookies = browser_cookie3.chrome(domain_name=domain)
            elif browser.lower() == 'edge':
                cookies = browser_cookie3.edge(domain_name=domain)
            elif browser.lower() == 'safari':
                cookies = browser_cookie3.safari(domain_name=domain)
            else:
                logger.error(f"Unsupported browser for browser_cookie3: {browser}")
                return None

            # Convert to Netscape format
            cookie_lines = ['# Netscape HTTP Cookie File']
            for cookie in cookies:
                if domain in cookie.domain:
                    secure = 'TRUE' if cookie.secure else 'FALSE'
                    http_only = 'TRUE' if cookie.has_nonstandard_attr('HttpOnly') else 'FALSE'
                    expires = str(int(cookie.expires)) if cookie.expires else '0'

                    line = '\t'.join([
                        cookie.domain,
                        http_only,
                        cookie.path or '/',
                        secure,
                        expires,
                        cookie.name,
                        cookie.value or ''
                    ])
                    cookie_lines.append(line)

            if len(cookie_lines) > 1:  # Has cookies beyond header
                cookies_content = '\n'.join(cookie_lines)

                # Update cache
                self.cached_cookies = cookies_content
                self.last_extraction_time = datetime.now()
                self.browser_user_agent = self.get_browser_user_agent(browser)

                cookies_data = {
                    'cookies': cookies_content,
                    'browser': browser,
                    'user_agent': self.browser_user_agent,
                    'extracted_at': self.last_extraction_time.isoformat(),
                    'domain': domain
                }

                # Save to disk for persistence
                self.save_cached_cookies(cookies_data)

                logger.info(f"Successfully extracted cookies using browser_cookie3 from {browser}")
                return cookies_data

        except Exception as e:
            logger.error(f"Alternative extraction failed: {e}")

        return None

    def extract_cookies_builtin(self, browser: str, domain: str = 'youtube.com') -> Optional[Dict[str, Any]]:
        """
        Built-in cookie extraction using yt-dlp's internal functions

        Args:
            browser: Browser name
            domain: Domain to extract cookies for

        Returns:
            Cookie data or None if failed
        """
        try:
            import yt_dlp
            from yt_dlp.cookies import extract_cookies_from_browser as yt_extract

            # Extract cookies directly
            logger.info(f"Using yt-dlp built-in extraction for {browser}")

            # Create a temporary file to store cookies
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as tmp_file:
                cookie_file = tmp_file.name

            # Extract cookies
            cookies = yt_extract(browser, logger=logger, profile=None, keyring=None)

            if cookies:
                # Write cookies to file in Netscape format
                with open(cookie_file, 'w') as f:
                    f.write('# Netscape HTTP Cookie File\n')
                    for cookie in cookies:
                        if domain in str(cookie.domain):
                            secure = 'TRUE' if cookie.secure else 'FALSE'
                            http_only = 'TRUE' if getattr(cookie, '_rest', {}).get('HttpOnly') else 'FALSE'
                            expires = str(int(cookie.expires)) if cookie.expires else '0'

                            line = '\t'.join([
                                cookie.domain,
                                http_only,
                                cookie.path or '/',
                                secure,
                                expires,
                                cookie.name,
                                cookie.value or ''
                            ])
                            f.write(line + '\n')

                # Read back the file
                with open(cookie_file, 'r') as f:
                    cookies_content = f.read()

                os.unlink(cookie_file)

                if len(cookies_content.split('\n')) > 2:  # Has actual cookies
                    # Update cache
                    self.cached_cookies = cookies_content
                    self.last_extraction_time = datetime.now()
                    self.browser_user_agent = self.get_browser_user_agent(browser)

                    cookies_data = {
                        'cookies': cookies_content,
                        'browser': browser,
                        'user_agent': self.browser_user_agent,
                        'extracted_at': self.last_extraction_time.isoformat(),
                        'domain': domain
                    }

                    # Save to disk for persistence
                    self.save_cached_cookies(cookies_data)

                    logger.info(f"Successfully extracted cookies using built-in method from {browser}")
                    return cookies_data

        except Exception as e:
            logger.error(f"Built-in extraction failed: {e}")

        return None

    def load_cached_cookies(self) -> bool:
        """Load cached cookies and metadata from disk"""
        try:
            # Load metadata
            if os.path.exists(self.metadata_file):
                with open(self.metadata_file, 'r') as f:
                    metadata = json.load(f)

                # Check if cookies are still fresh
                extracted_at = datetime.fromisoformat(metadata.get('extracted_at', ''))
                if datetime.now() - extracted_at < self.refresh_interval:
                    # Load cookies content
                    if os.path.exists(self.cookies_file):
                        with open(self.cookies_file, 'r') as f:
                            self.cached_cookies = f.read()

                        self.last_extraction_time = extracted_at
                        self.browser_user_agent = metadata.get('user_agent')

                        logger.info(f"Loaded cached cookies from disk (age: {datetime.now() - extracted_at})")
                        return True

        except Exception as e:
            logger.error(f"Failed to load cached cookies: {e}")

        return False

    def sync_cookiecloud(self) -> Tuple[bool, str]:
        """
        Sync cookies from CookieCloud service

        Returns:
            Tuple of (success, message)
        """
        if not self.cookiecloud or not self.cookiecloud.is_enabled():
            return False, "CookieCloud is not configured"

        try:
            logger.info("Syncing cookies from CookieCloud...")
            success, message = self.cookiecloud.sync_cookies(self.config_dir)

            if success:
                # Update sync time
                self.last_cookiecloud_sync = datetime.now()

                # Load the synced cookies
                cookies_file = os.path.join(self.config_dir, "cookies.txt")
                if os.path.exists(cookies_file):
                    with open(cookies_file, 'r') as f:
                        self.cached_cookies = f.read()
                    self.last_extraction_time = datetime.now()

                    # Update metadata
                    metadata = {
                        'source': 'cookiecloud',
                        'extracted_at': self.last_extraction_time.isoformat(),
                        'message': message
                    }
                    with open(self.metadata_file, 'w') as f:
                        json.dump(metadata, f, indent=2)

                    logger.info(f"CookieCloud sync successful: {message}")
                    return True, message
            else:
                logger.error(f"CookieCloud sync failed: {message}")
                return False, message

        except Exception as e:
            error_msg = f"CookieCloud sync error: {str(e)}"
            logger.error(error_msg)
            return False, error_msg

    def test_cookiecloud_connection(self) -> Tuple[bool, str]:
        """
        Test connection to CookieCloud server

        Returns:
            Tuple of (success, message)
        """
        if not self.cookiecloud:
            return False, "CookieCloud is not configured"

        return self.cookiecloud.test_connection()

    def save_cached_cookies(self, cookies_data: Dict[str, Any]) -> bool:
        """Save cookies and metadata to disk for persistence"""
        try:
            # Save cookies content
            with open(self.cookies_file, 'w') as f:
                f.write(cookies_data['cookies'])

            # Save metadata
            metadata = {
                'browser': cookies_data.get('browser'),
                'user_agent': cookies_data.get('user_agent'),
                'extracted_at': cookies_data.get('extracted_at'),
                'domain': cookies_data.get('domain')
            }

            with open(self.metadata_file, 'w') as f:
                json.dump(metadata, f, indent=2)

            logger.info(f"Saved cookies to {self.cookies_file}")
            return True

        except Exception as e:
            logger.error(f"Failed to save cookies: {e}")
            return False