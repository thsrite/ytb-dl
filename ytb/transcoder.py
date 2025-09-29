"""
FFmpeg transcoder module for post-download video processing
"""

import os
import re
import json
import logging
import asyncio
import subprocess
from typing import Optional, Dict, Any, Callable
from pathlib import Path

logger = logging.getLogger(__name__)


class FFmpegTranscoder:
    """Handle video transcoding with FFmpeg"""

    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.active_transcodes: Dict[str, Dict[str, Any]] = {}

    def detect_video_codec(self, filepath: str) -> Optional[str]:
        """Detect video codec using ffmpeg"""
        try:
            # Use ffprobe if available, otherwise ffmpeg
            # Try ffprobe first (faster and more reliable)
            try:
                cmd = [
                    'ffprobe',
                    '-v', 'error',
                    '-select_streams', 'v:0',
                    '-show_entries', 'stream=codec_name',
                    '-of', 'default=noprint_wrappers=1:nokey=1',
                    filepath
                ]
                logger.info(f"Running ffprobe to detect codec for: {filepath}")
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                if result.returncode == 0 and result.stdout.strip():
                    codec = result.stdout.strip()
                    logger.info(f"Detected video codec using ffprobe: {codec}")
                    return codec
            except FileNotFoundError:
                logger.info("ffprobe not found, falling back to ffmpeg")
            except subprocess.TimeoutExpired:
                logger.warning("ffprobe timed out, falling back to ffmpeg")

            # Fallback to ffmpeg
            cmd = [
                'ffmpeg',
                '-i', filepath,
                '-hide_banner'
            ]

            logger.info(f"Running ffmpeg to detect codec for: {filepath}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)  # Increased timeout
            full_output = result.stderr

            # Try to limit output reading for large files
            if len(full_output) > 10000:
                full_output = full_output[:10000]

            logger.info(f"FFmpeg output sample: {full_output[:500] if full_output else 'empty'}")

            # Parse video codec from output
            # Look for patterns like "Video: av1" or "Video: av01" or "Video: h264"
            import re
            video_pattern = r'Stream.*Video:\s*(\w+)'
            match = re.search(video_pattern, full_output)

            if match:
                codec = match.group(1).lower()
                logger.info(f"Detected video codec: {codec}")

                # Normalize codec names
                if codec in ['av01', 'libaom-av1']:
                    return 'av1'
                return codec
            else:
                logger.warning(f"Could not parse video codec from ffmpeg output")
                # Try alternative patterns
                if 'av01' in full_output.lower() or 'av1' in full_output.lower():
                    logger.info("Detected AV1 codec from output text")
                    return 'av1'
                if 'h264' in full_output.lower():
                    return 'h264'
                if 'hevc' in full_output.lower() or 'h265' in full_output.lower():
                    return 'hevc'
                return None

        except subprocess.TimeoutExpired:
            logger.error(f"Timeout detecting video codec for: {filepath}")
            # For timeout, assume it might need transcoding if AV1-only mode is off
            return 'unknown'
        except Exception as e:
            logger.error(f"Error detecting video codec: {e}")

        return None

    def should_transcode(self, filepath: str) -> bool:
        """Check if file needs transcoding based on config"""
        ffmpeg_config = self.config.get('ffmpeg', {})

        logger.info(f"FFmpeg config: enabled={ffmpeg_config.get('enabled')}, av1_only={ffmpeg_config.get('av1_only')}")

        if not ffmpeg_config.get('enabled'):
            logger.info(f"FFmpeg transcoding is disabled")
            return False

        # Check if we should only transcode AV1
        if ffmpeg_config.get('av1_only', True):
            # Only detect codec if av1_only is enabled
            codec = self.detect_video_codec(filepath)
            logger.info(f"Detected codec for {filepath}: {codec}")

            if not codec:
                logger.warning(f"Could not detect video codec for {filepath}")
                return False

            # AV1 codec names: av1, av01, libaom-av1
            should_transcode = codec.lower() in ['av1', 'av01', 'libaom-av1']
            logger.info(f"AV1-only mode: codec={codec}, should_transcode={should_transcode}")
            return should_transcode

        # If not AV1-only mode, transcode everything without checking codec
        logger.info(f"Transcoding all videos mode: will transcode without codec detection")
        return True

    def get_ffmpeg_command(self, input_file: str, output_file: str) -> list:
        """Build FFmpeg command from config"""
        ffmpeg_config = self.config.get('ffmpeg', {})
        command_template = ffmpeg_config.get('command', '-c:v libx264 -preset medium -crf 23 -c:a aac -b:a 192k')

        # Build command: ffmpeg -i input [user_command] output
        cmd_parts = ['ffmpeg', '-i', input_file]

        # Add hide_banner and progress options
        cmd_parts.extend(['-hide_banner', '-progress', 'pipe:1'])

        # Parse the user's command template
        import shlex
        try:
            # Use shlex to properly parse the command with quoted arguments
            user_cmd_parts = shlex.split(command_template)
            cmd_parts.extend(user_cmd_parts)
        except:
            # Fallback to simple split if shlex fails
            for part in command_template.split():
                if part not in ['{input}', '{output}']:
                    cmd_parts.append(part)

        # Add output file
        cmd_parts.append(output_file)

        logger.info(f"[FFMPEG COMMAND] {' '.join(cmd_parts)}")

        return cmd_parts

    async def transcode_video(
        self,
        task_id: str,
        input_file: str,
        progress_callback: Optional[Callable] = None
    ) -> Optional[str]:
        """Transcode video file with progress tracking"""

        if not os.path.exists(input_file):
            logger.error(f"Input file not found: {input_file}")
            return None

        # Check if transcoding is needed
        if not self.should_transcode(input_file):
            logger.info(f"Transcoding not needed for {input_file}")
            return input_file

        # Prepare output filename
        ffmpeg_config = self.config.get('ffmpeg', {})
        output_format = ffmpeg_config.get('output_format', 'mp4')

        input_path = Path(input_file)
        output_file = str(input_path.parent / f"{input_path.stem}_transcoded.{output_format}")

        # Build FFmpeg command
        cmd = self.get_ffmpeg_command(input_file, output_file)

        logger.info(f"Starting transcode: {' '.join(cmd)}")

        # Initialize transcode tracking
        self.active_transcodes[task_id] = {
            'status': 'transcoding',
            'progress': 0,
            'input_file': input_file,
            'output_file': output_file
        }

        try:
            # Get input file duration first
            duration = await self.get_video_duration(input_file)

            # Start FFmpeg process
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            # Parse progress output
            while True:
                line = await process.stdout.readline()
                if not line:
                    break

                line = line.decode('utf-8').strip()

                # Parse progress info
                if 'out_time_ms=' in line:
                    match = re.search(r'out_time_ms=(\d+)', line)
                    if match and duration:
                        current_time_ms = int(match.group(1))
                        current_time = current_time_ms / 1_000_000  # Convert to seconds
                        progress = min(100, (current_time / duration) * 100)

                        self.active_transcodes[task_id]['progress'] = progress

                        if progress_callback:
                            await progress_callback(task_id, 'transcoding', progress)

            # Wait for process to complete
            await process.wait()

            if process.returncode == 0:
                logger.info(f"Transcoding completed: {output_file}")

                # Delete original file after successful transcoding
                try:
                    os.remove(input_file)
                    logger.info(f"Deleted original file: {input_file}")
                except Exception as e:
                    logger.error(f"Error deleting original file: {e}")

                # Keep the transcoded file with _transcoded suffix
                self.active_transcodes[task_id]['status'] = 'completed'
                self.active_transcodes[task_id]['transcoded_file'] = output_file

                # Return the transcoded file path
                return output_file

            else:
                stderr = await process.stderr.read()
                logger.error(f"FFmpeg failed: {stderr.decode('utf-8')}")
                self.active_transcodes[task_id]['status'] = 'error'
                self.active_transcodes[task_id]['error'] = 'Transcoding failed'

                # Clean up partial output file
                if os.path.exists(output_file):
                    os.remove(output_file)

                return None

        except Exception as e:
            logger.error(f"Transcoding error: {e}")
            self.active_transcodes[task_id]['status'] = 'error'
            self.active_transcodes[task_id]['error'] = str(e)

            # Clean up partial output file
            if os.path.exists(output_file):
                os.remove(output_file)

            return None

    async def get_video_duration(self, filepath: str) -> Optional[float]:
        """Get video duration in seconds using ffmpeg"""
        try:
            cmd = [
                'ffmpeg',
                '-i', filepath,
                '-hide_banner'
            ]

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            # Parse duration from stderr
            stderr_text = stderr.decode('utf-8')

            # Look for Duration: HH:MM:SS.ms
            import re
            duration_pattern = r'Duration:\s*(\d+):(\d+):(\d+)\.(\d+)'
            match = re.search(duration_pattern, stderr_text)

            if match:
                hours = int(match.group(1))
                minutes = int(match.group(2))
                seconds = int(match.group(3))
                milliseconds = int(match.group(4))

                total_seconds = hours * 3600 + minutes * 60 + seconds + milliseconds / 100
                logger.info(f"Video duration: {total_seconds} seconds")
                return total_seconds

        except Exception as e:
            logger.error(f"Error getting video duration: {e}")

        return None

    def get_transcode_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get current transcode status"""
        return self.active_transcodes.get(task_id)

    def cleanup_task(self, task_id: str):
        """Clean up completed transcode task"""
        if task_id in self.active_transcodes:
            del self.active_transcodes[task_id]