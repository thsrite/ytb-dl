import yt_dlp
import os
import uuid
import logging
from typing import Optional, Dict, Any
import asyncio
from concurrent.futures import ThreadPoolExecutor
from .config import Config
from .browser_cookies import BrowserCookieExtractor

# Setup logger
logger = logging.getLogger(__name__)


class YTDownloader:
    def __init__(self, download_dir: str = "downloads"):
        self.download_dir = download_dir
        os.makedirs(download_dir, exist_ok=True)
        self.executor = ThreadPoolExecutor(max_workers=3)
        self.active_downloads: Dict[str, Dict[str, Any]] = {}
        self.config = Config()
        # Track download phases for each task (video, audio, merge)
        self.download_phases: Dict[str, Dict[str, Any]] = {}
        # Initialize browser cookie extractor
        self.cookie_extractor = BrowserCookieExtractor()
        # Track 403 errors for automatic retry
        self.error_counts: Dict[str, int] = {}
        # Store 403 notification callbacks per task
        self.notification_callbacks: Dict[str, Any] = {}

    def _progress_hook(self, task_id: str):
        def hook(d):
            if task_id in self.active_downloads:
                # Initialize phases tracking if not exists
                if task_id not in self.download_phases:
                    self.download_phases[task_id] = {
                        'current_phase': 'downloading',  # downloading, merging, completed
                        'files_completed': 0,
                        'current_file': '',
                        'total_downloaded': 0,
                        'total_size': 0
                    }

                phases = self.download_phases[task_id]
                filename = d.get('filename', '')

                if d['status'] == 'downloading':
                    downloaded = d.get('downloaded_bytes', 0)
                    total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
                    speed = d.get('speed', 0)
                    eta = d.get('eta', 0)

                    # Track current file being downloaded
                    if filename and filename != phases['current_file']:
                        phases['current_file'] = filename
                        # If this is a new file and we already completed one, we're on the second download
                        if phases['files_completed'] > 0:
                            phases['current_phase'] = 'downloading_audio'
                        else:
                            phases['current_phase'] = 'downloading_video'

                    # Calculate percentage based on the actual download progress
                    percent = 0
                    if total > 0:
                        percent = (downloaded / total) * 100

                    # Store the actual percentage from yt-dlp
                    self.active_downloads[task_id]['progress'] = {
                        'status': 'downloading',
                        'downloaded_bytes': downloaded,
                        'total_bytes': total,
                        'speed': speed,
                        'eta': eta,
                        'percent': percent,  # Show actual percentage
                        'filename': filename,
                        'phase': phases['current_phase']
                    }

                    self.active_downloads[task_id]['status'] = 'downloading'

                elif d['status'] == 'finished':
                    filename = d.get('filename', '')

                    # Check if this is a download completion (not final merge)
                    if filename and ('.f' in filename or filename.endswith(('.mp4', '.m4a', '.webm'))):
                        phases['files_completed'] += 1
                        phases['total_downloaded'] += d.get('total_bytes', 0)

                        # After each file completes, show it at 100% briefly
                        self.active_downloads[task_id]['progress']['percent'] = 100

                        # If we've downloaded multiple files, we need to merge
                        if phases['files_completed'] >= 2:
                            phases['current_phase'] = 'merging'
                            self.active_downloads[task_id]['progress'] = {
                                'status': 'processing',
                                'percent': 100,  # Keep at 100% during merge
                                'downloaded_bytes': phases['total_downloaded'],
                                'total_bytes': phases['total_downloaded'],
                                'phase': 'merging'
                            }
                            self.active_downloads[task_id]['status'] = 'processing'
                    else:
                        # Final file is ready (after merge or single file download)
                        phases['current_phase'] = 'completed'
                        self.active_downloads[task_id]['progress'] = {
                            'status': 'completed',
                            'percent': 100,
                            'downloaded_bytes': phases['total_downloaded'] or d.get('total_bytes', 0),
                            'total_bytes': phases['total_downloaded'] or d.get('total_bytes', 0),
                            'phase': 'completed'
                        }
                        self.active_downloads[task_id]['status'] = 'processing'

                elif d['status'] == 'error':
                    self.active_downloads[task_id]['status'] = 'error'
                    self.active_downloads[task_id]['error'] = d.get('error_msg', 'Unknown error')

        return hook

    async def get_video_info(self, url: str) -> Dict[str, Any]:
        ydl_opts = self.config.get_ydl_opts({
            'extract_flat': False,
            'no_color': True,
            'logtostderr': False,
            'no_warnings': True,  # Disable warnings to avoid cookie rotation messages
            'ignoreerrors': False,
        })

        loop = asyncio.get_event_loop()

        def extract_info():
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    return ydl.extract_info(url, download=False)
            except Exception as e:
                error_msg = str(e)
                print(f"Error extracting info: {error_msg}")

                # Try with more permissive options if format error
                if "Requested format is not available" in error_msg:
                    print("Retrying with more permissive format options...")
                    fallback_opts = ydl_opts.copy()
                    fallback_opts.update({
                        'format': 'best',
                        'no_warnings': True,
                    })
                    try:
                        with yt_dlp.YoutubeDL(fallback_opts) as ydl_fallback:
                            return ydl_fallback.extract_info(url, download=False)
                    except Exception as e2:
                        print(f"Fallback also failed: {str(e2)}")
                        raise e2
                raise

        info = await loop.run_in_executor(self.executor, extract_info)

        # Format the response
        formats = []
        if info.get('formats'):
            for f in info['formats']:
                if f.get('vcodec') != 'none' or f.get('acodec') != 'none':
                    # Convert quality to string if it's a number
                    quality = f.get('quality', '')
                    if isinstance(quality, (int, float)):
                        quality = str(quality)

                    # Build resolution string
                    width = f.get('width')
                    height = f.get('height')
                    if width and height:
                        resolution = f"{width}x{height}"
                    else:
                        resolution = f.get('resolution', 'N/A')

                    format_data = {
                        'format_id': f.get('format_id', ''),
                        'format_note': f.get('format_note', '') or f.get('format', ''),
                        'ext': f.get('ext', ''),
                        'quality': quality,
                        'filesize': f.get('filesize') or f.get('filesize_approx', 0),
                        'vcodec': f.get('vcodec', ''),
                        'acodec': f.get('acodec', ''),
                        'resolution': resolution,
                        'fps': f.get('fps') or 0,
                        'abr': f.get('abr') or 0,
                        'tbr': f.get('tbr') or 0,  # Total bitrate
                        'vbr': f.get('vbr') or 0   # Video bitrate
                    }
                    formats.append(format_data)

        return {
            'id': info.get('id', ''),
            'title': info.get('title', ''),
            'description': info.get('description', ''),
            'thumbnail': info.get('thumbnail', ''),
            'duration': info.get('duration', 0),
            'uploader': info.get('uploader', ''),
            'upload_date': info.get('upload_date', ''),
            'view_count': info.get('view_count', 0),
            'like_count': info.get('like_count', 0),
            'formats': formats,
            'url': url
        }

    def set_403_notification_callback(self, task_id: str, callback) -> None:
        """Set a 403 notification callback for a specific task"""
        self.notification_callbacks[task_id] = callback

    async def download_video_with_id(self, url: str, task_id: str, format_id: Optional[str] = None) -> str:
        """Download video with pre-assigned task_id (for 403 callback setup)"""

        # Initialize download tracking
        self.active_downloads[task_id] = {
            'status': 'pending',
            'progress': {'percent': 0}
        }

        # Set up download options - use config's default format with fallbacks
        # More aggressive fallback for Docker environments
        is_docker = os.path.exists("/app")

        if is_docker:
            # Docker environment - use more permissive format chain
            default_format = self.config.get_wecom_config().get(
                "default_format_id",
                "best[ext=mp4]/bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best"
            )
        else:
            # Local environment - can be more specific
            default_format = self.config.get_wecom_config().get(
                "default_format_id",
                "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best"
            )

        format_str = format_id or default_format
        output_template = os.path.join(self.download_dir, '%(title)s.%(ext)s')

        # Get base options from config
        base_opts = {
            'format': format_str,
            'outtmpl': output_template,
            'progress_hooks': [self._progress_hook(task_id)],
        }

        # Get options with cookies included
        ydl_opts = self.config.get_ydl_opts(base_opts)

        # Add cookies support
        ydl_opts = self.get_ydl_opts_with_browser_cookies(ydl_opts)

        # Add age limit bypass for age-restricted videos
        ydl_opts['age_limit'] = None  # No age limit
        ydl_opts['skip_download'] = False

        # Build and log the equivalent yt-dlp command
        command_parts = ['yt-dlp']

        # Add URL
        command_parts.append(f'"{url}"')

        # Check if custom params are configured
        custom_params = self.config.config.get('custom_params', [])

        if custom_params:
            # When custom params exist, only add base required params
            # Add cookies if configured
            if ydl_opts.get('cookiefile'):
                command_parts.append(f'--cookies "{ydl_opts["cookiefile"]}"')

            # Add no-check-certificate
            command_parts.append('--no-check-certificate')

            # Add geo-bypass
            command_parts.append('--geo-bypass')

            # Add all custom parameters
            for param in custom_params:
                if param and isinstance(param, str):
                    command_parts.append(param)
        else:
            # Use default parameters when no custom params
            # Add format
            command_parts.append(f'-f "{format_str}"')

            # Add output template
            command_parts.append(f'-o "{output_template}"')

            # Add merge output format
            command_parts.append('--merge-output-format mp4')

            # Add proxy if configured
            if ydl_opts.get('proxy'):
                command_parts.append(f'--proxy "{ydl_opts["proxy"]}"')

            # Add cookies if configured
            if ydl_opts.get('cookiefile'):
                command_parts.append(f'--cookies "{ydl_opts["cookiefile"]}"')

            # Add other common options
            if ydl_opts.get('nocheckcertificate'):
                command_parts.append('--no-check-certificate')
            if ydl_opts.get('geo_bypass'):
                command_parts.append('--geo-bypass')

        # Log the command
        command_str = ' '.join(command_parts)
        logger.info(f"Starting download with task_id: {task_id}")
        logger.info(f"Equivalent yt-dlp command: {command_str}")
        print(f"\n{'='*60}")
        print(f"Task ID: {task_id}")
        print(f"URL: {url}")
        print(f"Format: {format_str}")
        print(f"Output: {output_template}")
        print(f"yt-dlp command: {command_str}")
        print(f"{'='*60}\n")

        def download():
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    filename = ydl.prepare_filename(info)
                    # Handle merged file extension
                    if not filename.endswith('.mp4'):
                        base_name = os.path.splitext(filename)[0]
                        if os.path.exists(f"{base_name}.mp4"):
                            filename = f"{base_name}.mp4"

                    self.active_downloads[task_id]['status'] = 'completed'
                    self.active_downloads[task_id]['filename'] = os.path.basename(filename)
                    self.active_downloads[task_id]['filepath'] = os.path.abspath(filename)
                    return task_id
            except Exception as e:
                error_msg = str(e)
                print(f"Download error: {error_msg}")

                # Handle network connection errors
                if any(err in error_msg.lower() for err in ['connection reset', 'connection aborted', 'network', 'timeout', 'ssl']):
                    print(f"Detected network error for task {task_id}, will retry...")
                    logger.info(f"Network error for task {task_id}: {error_msg}")

                    # Increment network error count
                    if task_id not in self.error_counts:
                        self.error_counts[task_id] = 0
                    self.error_counts[task_id] += 1

                    # Max 3 retries for network errors
                    if self.error_counts[task_id] <= 3:
                        # Send notification about network error retry
                        import asyncio
                        new_loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(new_loop)
                        try:
                            new_loop.run_until_complete(
                                self.notify_network_error(task_id, url, f"网络连接错误，正在第{self.error_counts[task_id]}次重试...",
                                                        retry_count=self.error_counts[task_id])
                            )
                        finally:
                            new_loop.close()

                        # Wait a bit before retry
                        import time
                        wait_time = min(10 * self.error_counts[task_id], 30)  # Exponential backoff, max 30 seconds
                        print(f"Waiting {wait_time} seconds before retry...")
                        time.sleep(wait_time)

                        # Update task status
                        self.active_downloads[task_id]['status'] = 'retrying'
                        self.active_downloads[task_id]['error'] = f'网络错误，第{self.error_counts[task_id]}次重试中...'

                        try:
                            print(f"Retrying download after network error for: {url}")
                            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                                info = ydl.extract_info(url, download=True)
                                filename = ydl.prepare_filename(info)
                                print(f"Retry download completed successfully for task {task_id}")
                                logger.info(f"Network retry successful for task {task_id}, file: {filename}")

                                if not filename.endswith('.mp4'):
                                    base_name = os.path.splitext(filename)[0]
                                    if os.path.exists(f"{base_name}.mp4"):
                                        filename = f"{base_name}.mp4"

                                self.active_downloads[task_id]['status'] = 'completed'
                                self.active_downloads[task_id]['filename'] = os.path.basename(filename)
                                self.active_downloads[task_id]['filepath'] = os.path.abspath(filename)
                                print(f"✅ Task {task_id} completed after network error retry")

                                # Send success notification
                                new_loop = asyncio.new_event_loop()
                                asyncio.set_event_loop(new_loop)
                                try:
                                    new_loop.run_until_complete(
                                        self.notify_network_error(task_id, url, "网络恢复，下载成功",
                                                                retry_count=self.error_counts[task_id],
                                                                success=True)
                                    )
                                finally:
                                    new_loop.close()

                                return task_id
                        except Exception as retry_error:
                            print(f"Network retry {self.error_counts[task_id]} failed: {retry_error}")
                            logger.error(f"Network retry {self.error_counts[task_id]} failed for task {task_id}: {retry_error}")
                            error_msg = str(retry_error)
                            # Continue to next retry or error handling
                    else:
                        # Max retries exceeded for network error
                        print(f"Max network retries exceeded for task {task_id}")
                        logger.error(f"Max network retries exceeded for task {task_id}")

                        # Send final failure notification
                        import asyncio
                        new_loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(new_loop)
                        try:
                            new_loop.run_until_complete(
                                self.notify_network_error(task_id, url, "网络错误，多次重试失败",
                                                        retry_count=self.error_counts[task_id],
                                                        final=True)
                            )
                        finally:
                            new_loop.close()

                        self.active_downloads[task_id]['status'] = 'error'
                        self.active_downloads[task_id]['error'] = f'网络错误: {error_msg[:200]}'
                        raise e

                # Handle 403 Forbidden error
                elif "403" in error_msg or "Forbidden" in error_msg:
                    print(f"Detected 403 error for task {task_id}, attempting cookie refresh...")
                    # Create a new event loop for this thread since we're in an executor
                    import asyncio
                    new_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(new_loop)
                    try:
                        retry_success = new_loop.run_until_complete(self.handle_403_error(task_id, url, format_id))
                    finally:
                        new_loop.close()

                    if retry_success:
                        # Retry with fresh cookies
                        print(f"Cookie refresh successful for task {task_id}, retrying download...")
                        logger.info(f"Starting retry download for task {task_id} after cookie refresh")

                        # Update task status to show retry in progress
                        self.active_downloads[task_id]['status'] = 'downloading'
                        self.active_downloads[task_id]['error'] = None

                        # Get fresh options with updated cookies
                        fresh_opts = ydl_opts.copy()
                        # Add the cookie file path directly
                        cookiecloud_file = os.path.join(self.config.config_dir, 'cookies.txt')
                        if os.path.exists(cookiecloud_file):
                            fresh_opts['cookiefile'] = cookiecloud_file
                            print(f"Using CookieCloud cookies from: {cookiecloud_file}")
                            logger.info(f"Cookie file exists at {cookiecloud_file}, size: {os.path.getsize(cookiecloud_file)} bytes")
                        else:
                            # Fallback to browser cookies
                            fresh_opts = self.get_ydl_opts_with_browser_cookies(ydl_opts)

                        # Add more options for retry to handle age-restricted content
                        fresh_opts['age_limit'] = None  # No age limit
                        fresh_opts['geo_bypass'] = True  # Bypass geographic restrictions
                        fresh_opts['geo_bypass_country'] = 'US'  # Try US region

                        # Check if we have cookie file from CookieCloud or browser
                        cookie_file = fresh_opts.get('cookiefile')
                        if cookie_file and os.path.exists(cookie_file):
                            print(f"Using cookie file: {cookie_file}")
                            logger.info(f"Cookie file exists at {cookie_file}, size: {os.path.getsize(cookie_file)} bytes")

                        # Send success notification BEFORE starting retry
                        import asyncio
                        new_loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(new_loop)
                        try:
                            new_loop.run_until_complete(
                                self.notify_403_error(task_id, url, "",
                                                    retry_count=self.error_counts[task_id],
                                                    final=False, success=True)
                            )
                        finally:
                            new_loop.close()

                        try:
                            print(f"Retrying download with refreshed cookies for: {url}")
                            with yt_dlp.YoutubeDL(fresh_opts) as ydl:
                                info = ydl.extract_info(url, download=True)
                                filename = ydl.prepare_filename(info)
                                print(f"Retry download completed successfully for task {task_id}")
                                logger.info(f"Retry successful for task {task_id}, file: {filename}")

                                if not filename.endswith('.mp4'):
                                    base_name = os.path.splitext(filename)[0]
                                    if os.path.exists(f"{base_name}.mp4"):
                                        filename = f"{base_name}.mp4"

                                self.active_downloads[task_id]['status'] = 'completed'
                                self.active_downloads[task_id]['filename'] = os.path.basename(filename)
                                self.active_downloads[task_id]['filepath'] = os.path.abspath(filename)
                                print(f"✅ Task {task_id} completed after cookie refresh retry")

                                return task_id
                        except Exception as retry_error:
                            print(f"Retry failed after cookie refresh: {retry_error}")
                            logger.error(f"Retry failed for task {task_id}: {retry_error}")
                            error_msg = str(retry_error)

                            # If still 403 after cookie refresh, it might be age-restricted or region-blocked
                            if "403" in str(retry_error) or "Forbidden" in str(retry_error):
                                # Send final failure notification
                                import asyncio
                                new_loop = asyncio.new_event_loop()
                                asyncio.set_event_loop(new_loop)
                                try:
                                    new_loop.run_until_complete(
                                        self.notify_403_error(task_id, url, "Cookie刷新后仍然失败，视频可能需要年龄验证或地区限制",
                                                            retry_count=self.error_counts[task_id],
                                                            final=True)
                                    )
                                finally:
                                    new_loop.close()

                                # Set final error message
                                self.active_downloads[task_id]['status'] = 'error'
                                self.active_downloads[task_id]['error'] = 'Cookie刷新后仍然403错误，视频可能有特殊限制'
                    else:
                        print(f"Cookie refresh failed for task {task_id}, unable to retry")
                        logger.error(f"Cookie refresh failed for task {task_id}")

                # Try multiple fallback strategies if format error
                elif "Requested format is not available" in error_msg:
                    print(f"Retrying download with fallback formats for task {task_id}...")

                    # Define progressive fallback formats
                    fallback_formats = [
                        'best[ext=mp4]',  # First try: best quality MP4
                        'worst[ext=mp4]',  # Second try: any MP4
                        'best',  # Third try: any best format
                        'worst',  # Last resort: any format
                    ]

                    for i, fallback_format in enumerate(fallback_formats, 1):
                        try:
                            print(f"Fallback attempt {i}: Using format '{fallback_format}'")
                            fallback_opts = ydl_opts.copy()
                            fallback_opts['format'] = fallback_format

                            # For Docker, also add more aggressive options
                            if is_docker:
                                fallback_opts.update({
                                    'ignoreerrors': True,
                                    'quiet': True,
                                    'no_warnings': True,
                                    'extract_flat': False,
                                })

                            with yt_dlp.YoutubeDL(fallback_opts) as ydl_fallback:
                                info = ydl_fallback.extract_info(url, download=True)
                                filename = ydl_fallback.prepare_filename(info)

                                self.active_downloads[task_id]['status'] = 'completed'
                                self.active_downloads[task_id]['filename'] = os.path.basename(filename)
                                self.active_downloads[task_id]['filepath'] = os.path.abspath(filename)
                                print(f"Fallback successful with format '{fallback_format}'")
                                return task_id
                        except Exception as e2:
                            print(f"Fallback {i} with format '{fallback_format}' failed: {str(e2)}")
                            if i == len(fallback_formats):  # Last attempt failed
                                print(f"All fallback attempts failed for task {task_id}")
                                self.active_downloads[task_id]['status'] = 'error'
                                self.active_downloads[task_id]['error'] = f"All fallback formats failed. Last error: {str(e2)}"
                                raise e2
                            continue  # Try next fallback format

                self.active_downloads[task_id]['status'] = 'error'
                self.active_downloads[task_id]['error'] = error_msg
                raise e

        # Start download in background
        loop = asyncio.get_event_loop()
        loop.run_in_executor(self.executor, download)

        return task_id

    def get_download_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        return self.active_downloads.get(task_id)

    def cleanup_task(self, task_id: str):
        if task_id in self.active_downloads:
            del self.active_downloads[task_id]
        if task_id in self.download_phases:
            del self.download_phases[task_id]
        if task_id in self.error_counts:
            del self.error_counts[task_id]
        if task_id in self.notification_callbacks:
            del self.notification_callbacks[task_id]

    def get_ydl_opts_with_browser_cookies(self, base_opts: Dict[str, Any] = None) -> Dict[str, Any]:
        """Get yt-dlp options with browser cookies if enabled"""
        opts = base_opts.copy() if base_opts else {}

        # First check for CookieCloud cookies file
        cookiecloud_file = os.path.join(self.config.config_dir, 'cookies.txt')
        if os.path.exists(cookiecloud_file):
            opts['cookiefile'] = cookiecloud_file
            logger.info(f"Using CookieCloud cookie file: {cookiecloud_file}")
            print(f"Using CookieCloud cookies from {cookiecloud_file}")
            return opts

        # Check if browser cookies are enabled in config
        browser_config = self.config.config.get('browser_cookies', {})
        if browser_config.get('enabled', False):
            browser = browser_config.get('browser', 'firefox')

            # Try to get cookies from browser
            cookie_data = self.cookie_extractor.extract_cookies_from_browser(browser)
            if cookie_data:
                # Save cookies to temporary file
                temp_cookie_file = os.path.join(self.download_dir, f'.cookies_{uuid.uuid4().hex}.txt')
                self.cookie_extractor.save_cookies_to_file(cookie_data['cookies'], temp_cookie_file)

                opts['cookiefile'] = temp_cookie_file
                if cookie_data.get('user_agent'):
                    opts['user_agent'] = cookie_data['user_agent']

                logger.info(f"Using browser cookies from {browser}")
                print(f"Using browser cookies from {browser}")
            else:
                logger.warning("Failed to extract browser cookies, using fallback")

        return opts

    async def download_video(self, url: str, format_id: Optional[str] = None) -> str:
        """Original download_video method for backward compatibility"""
        task_id = str(uuid.uuid4())
        return await self.download_video_with_id(url, task_id, format_id)

    async def notify_403_error(self, task_id: str, url: str, status: str, retry_count: int = 0, final: bool = False, success: bool = False) -> None:
        """Send notifications for 403 errors to admins and users via WeChat"""
        # Check if there's a task-specific callback registered
        callback = self.notification_callbacks.get(task_id)
        if callback:
            await callback(task_id, url, status, retry_count, final, success)
        # Otherwise, no notification (for non-WeChat downloads)

    async def notify_network_error(self, task_id: str, url: str, status: str, retry_count: int = 0, final: bool = False, success: bool = False) -> None:
        """Send notifications for network errors to admins and users via WeChat"""
        # Check if there's a task-specific callback registered
        callback = self.notification_callbacks.get(task_id)
        if callback:
            # Call the same callback but with network-specific status
            await callback(task_id, url, f"[网络错误] {status}", retry_count, final, success)
        # Otherwise, no notification (for non-WeChat downloads)

    async def handle_403_error(self, task_id: str, url: str, format_id: Optional[str] = None) -> bool:
        """Handle 403 error by refreshing cookies and retrying"""
        logger.info(f"Handling 403 error for task {task_id}")

        # Increment error count
        self.error_counts[task_id] = self.error_counts.get(task_id, 0) + 1

        # Max 3 retries
        if self.error_counts[task_id] > 3:
            logger.error(f"Max retries exceeded for task {task_id}")
            # Send final failure notification
            await self.notify_403_error(task_id, url, "Max retries exceeded", final=True)
            return False

        # First, check if CookieCloud is enabled and try to sync
        cookiecloud_config = self.config.config.get('cookiecloud', {})
        if cookiecloud_config.get('enabled'):
            logger.info(f"Attempting CookieCloud sync for task {task_id}...")
            print(f"🔄 Syncing cookies from CookieCloud for task {task_id}...")

            # Notify about cookie sync attempt
            await self.notify_403_error(task_id, url, "正在从 CookieCloud 同步 Cookie...", retry_count=self.error_counts[task_id])

            from .cookiecloud import CookieCloud
            cc = CookieCloud(cookiecloud_config)
            success, message = cc.sync_cookies()

            if success:
                logger.info(f"CookieCloud sync successful: {message}")
                print(f"✅ CookieCloud sync successful: {message}")
                self.active_downloads[task_id]['status'] = 'retrying'
                self.active_downloads[task_id]['error'] = 'CookieCloud cookies 已同步，正在重试...'

                await asyncio.sleep(2)
                return True
            else:
                logger.warning(f"CookieCloud sync failed: {message}")
                print(f"⚠️ CookieCloud sync failed: {message}")

        # Try to refresh browser cookies
        browser_config = self.config.config.get('browser_cookies', {})
        if browser_config.get('enabled'):
            browser = browser_config.get('browser', 'firefox')
            logger.info(f"Attempting browser cookie extraction for task {task_id}...")
            print(f"🔄 Extracting cookies from {browser} browser for task {task_id}...")

            # Notify about browser cookie extraction attempt
            await self.notify_403_error(task_id, url, f"正在从 {browser} 浏览器提取 Cookie...", retry_count=self.error_counts[task_id])

            cookie_data = self.cookie_extractor.extract_cookies_from_browser(browser)
            if cookie_data:
                logger.info(f"Successfully extracted browser cookies, retrying download for task {task_id}")
                print(f"✅ Successfully extracted cookies from {browser}")
                self.active_downloads[task_id]['status'] = 'retrying'
                self.active_downloads[task_id]['error'] = f'{browser} 浏览器 Cookie 已提取，正在重试...'

                await asyncio.sleep(2)
                return True
            else:
                logger.warning(f"Failed to extract browser cookies from {browser}")
                print(f"⚠️ Failed to extract cookies from {browser}")

        # If all cookie refresh attempts failed
        await self.notify_403_error(task_id, url, "Cookie refresh failed", final=True)
        return False