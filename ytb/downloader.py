import yt_dlp
import os
import uuid
import logging
import json
from typing import Optional, Dict, Any
import asyncio
from concurrent.futures import ThreadPoolExecutor
from .config import Config

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
            'no_warnings': False,  # Enable warnings to see what's happening
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

    async def download_video(self, url: str, format_id: Optional[str] = None) -> str:
        task_id = str(uuid.uuid4())

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

        ydl_opts = self.config.get_ydl_opts({
            'format': format_str,
            'outtmpl': output_template,
            'progress_hooks': [self._progress_hook(task_id)],
            'merge_output_format': 'mp4',
        })

        # Build and log the equivalent yt-dlp command
        command_parts = ['yt-dlp']

        # Add URL
        command_parts.append(f'"{url}"')

        # Add format
        command_parts.append(f'-f "{format_str}"')

        # Add output template
        command_parts.append(f'-o "{output_template}"')

        # Add merge format
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

        loop = asyncio.get_event_loop()

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

                # Try multiple fallback strategies if format error
                if "Requested format is not available" in error_msg:
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
        loop.run_in_executor(self.executor, download)

        return task_id

    def get_download_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        return self.active_downloads.get(task_id)

    def cleanup_task(self, task_id: str):
        if task_id in self.active_downloads:
            del self.active_downloads[task_id]
        if task_id in self.download_phases:
            del self.download_phases[task_id]