from __future__ import annotations

import asyncio
import logging
import os
import re
from collections import deque
from datetime import datetime
from typing import Any, Deque, Dict, Optional, Set
from xml.etree import ElementTree as ET

from fastapi import HTTPException

from ytb.config import Config
from ytb.downloader import YTDownloader
from ytb.history_manager import HistoryManager

from .client import WeComClient, WeComAPIError
from .crypto import WeComCrypto, WeComCryptoError

logger = logging.getLogger(__name__)


class WeComService:
    """Glue code between WeCom callbacks and the downloader."""

    URL_PATTERN = re.compile(r"https?://\S+")
    YOUTUBE_PATTERN = re.compile(r"(?:(?:https?://)?(?:www\.)?(?:youtube\.com|youtu\.be|m\.youtube\.com))/\S+")

    def __init__(
        self,
        config_manager: Config,
        downloader: YTDownloader,
        history_manager: HistoryManager,
    ) -> None:
        self.config_manager = config_manager
        self.downloader = downloader
        self.history_manager = history_manager
        self.client: Optional[WeComClient] = None
        self.crypto: Optional[WeComCrypto] = None
        self.task_context: Dict[str, Dict[str, Any]] = {}
        self.wecom_config: Dict[str, Any] = {}
        self._recent_msg_ids: Deque[str] = deque(maxlen=500)
        self._recent_msg_index: Set[str] = set()
        self.reload_config()

    def reload_config(self) -> None:
        self.wecom_config = self.config_manager.get_wecom_config()
        if self._is_configured():
            try:
                self.client = WeComClient(self.wecom_config)
                self.crypto = WeComCrypto(
                    token=self.wecom_config.get("token", ""),
                    encoding_aes_key=self.wecom_config.get("encoding_aes_key", ""),
                    corp_id=self.wecom_config.get("corp_id", ""),
                )
                logger.info("WeCom integration initialized")
            except Exception as exc:  # noqa: BLE001
                self.client = None
                self.crypto = None
                logger.error("Failed to initialize WeCom clients: %s", exc)
        else:
            self.client = None
            self.crypto = None
            logger.info("WeCom integration disabled: missing configuration")

    def _is_configured(self) -> bool:
        required = [
            self.wecom_config.get("corp_id"),
            self.wecom_config.get("agent_id") is not None,
            self.wecom_config.get("app_secret"),
            self.wecom_config.get("token"),
            self.wecom_config.get("encoding_aes_key"),
        ]
        return all(required)

    def verify_url(self, msg_signature: str, timestamp: str, nonce: str, echostr: str) -> str:
        if not self.crypto:
            raise HTTPException(status_code=503, detail="WeCom integration is not configured")
        try:
            self.crypto.verify_signature(msg_signature, timestamp, nonce, echostr)
            decrypted, _ = self.crypto.decrypt(echostr)
            return decrypted
        except WeComCryptoError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    async def handle_callback(self, msg_signature: str, timestamp: str, nonce: str, body: str) -> str:
        if not self.crypto:
            raise HTTPException(status_code=503, detail="WeCom integration is not configured")

        encrypt = self._extract_encrypt(body)
        try:
            self.crypto.verify_signature(msg_signature, timestamp, nonce, encrypt)
            decrypted_xml, _ = self.crypto.decrypt(encrypt)
        except WeComCryptoError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        payload = self._parse_xml(decrypted_xml)
        msg_type = payload.get("MsgType", "").lower()

        if msg_type == "text":
            await self._handle_text_message(payload)
        else:
            logger.info("Ignoring unsupported WeCom message type: %s", msg_type)

        # Respond with plaintext "success" as acknowledgement
        return "success"

    async def _handle_text_message(self, payload: Dict[str, Any]) -> None:
        msg_id = str(payload.get("MsgId", ""))

        # 优先检查消息ID重复
        if msg_id and self._is_duplicate_message(msg_id):
            logger.info("Duplicate WeCom message %s ignored", msg_id)
            return

        # 如果消息ID为空，立即标记消息为已处理防止重复（基于内容和时间戳）
        if not msg_id:
            logger.warning("Message ID is empty, using content-based deduplication")
            content_key = f"{payload.get('FromUserName', '')}_{payload.get('Content', '')[:50]}_{payload.get('CreateTime', '')}"
            if self._is_duplicate_message(content_key):
                logger.info("Duplicate content-based message ignored")
                return
            self._mark_message_processed(content_key)

        user_id = payload.get("FromUserName")
        agent_id = payload.get("AgentID")
        content = (payload.get("Content") or "").strip()

        url = self._extract_url(content)
        if not url:
            await self._safe_notify(
                "未检测到有效的视频链接，请直接发送完整的 http(s) 链接。",
                touser=user_id,
            )
            return


        format_id = self.wecom_config.get(
            "default_format_id",
            "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        )
        # 立即标记消息为已处理，防止在任务创建过程中收到重复请求
        if msg_id:
            self._mark_message_processed(msg_id)

        try:
            task_id = await self.downloader.download_video(url, format_id)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to enqueue download for %s", url)
            await self._safe_notify(f"无法开始下载任务：{exc}", touser=user_id)
            return

        video_info: Dict[str, Any] = {}
        try:
            video_info = await self.downloader.get_video_info(url)

            # 从formats中提取文件大小信息
            if video_info.get('formats'):
                estimated_size = None


                # 方法1: 分别找最大的视频和音频格式并相加（优先MP4+M4A）
                estimated_size_separate = None
                combined_size_info = ""

                # 找最大的视频格式（优先MP4）
                best_video_size = 0
                video_formats = [f for f in video_info['formats']
                               if f.get('vcodec') != 'none' and (f.get('filesize') or f.get('filesize_approx'))]

                # 优先选择MP4格式的视频
                mp4_video_formats = [f for f in video_formats if f.get('ext') == 'mp4']

                if mp4_video_formats:
                    best_mp4_format = None
                    for fmt in mp4_video_formats:
                        size = fmt.get('filesize') or fmt.get('filesize_approx')
                        if size and size > best_video_size:
                            best_video_size = size
                            best_mp4_format = fmt
                    if best_mp4_format:
                        combined_size_info += f"视频: {best_mp4_format.get('format_id')}({best_video_size/1024/1024:.2f}MB) + "
                    logger.info(f"Found best MP4 video size: {best_video_size} bytes")
                else:
                    # 如果没有MP4，选择其他格式中的最大
                    best_other_format = None
                    for fmt in video_formats:
                        size = fmt.get('filesize') or fmt.get('filesize_approx')
                        if size and size > best_video_size:
                            best_video_size = size
                            best_other_format = fmt
                    if best_other_format:
                        combined_size_info += f"视频: {best_other_format.get('format_id')}({best_video_size/1024/1024:.2f}MB) + "
                    logger.info(f"Found best non-MP4 video size: {best_video_size} bytes")

                # 找最大的音频格式（优先M4A）
                best_audio_size = 0
                audio_formats = [f for f in video_info['formats']
                               if f.get('acodec') != 'none' and f.get('vcodec') == 'none'
                               and (f.get('filesize') or f.get('filesize_approx'))]

                # 优先选择M4A格式的音频
                m4a_audio_formats = [f for f in audio_formats if f.get('ext') == 'm4a']

                if m4a_audio_formats:
                    best_m4a_format = None
                    for fmt in m4a_audio_formats:
                        size = fmt.get('filesize') or fmt.get('filesize_approx')
                        if size and size > best_audio_size:
                            best_audio_size = size
                            best_m4a_format = fmt
                    if best_m4a_format:
                        combined_size_info += f"音频: {best_m4a_format.get('format_id')}({best_audio_size/1024/1024:.2f}MB)"
                    logger.info(f"Found best M4A audio size: {best_audio_size} bytes")
                else:
                    # 如果没有M4A，选择其他格式中的最大
                    best_other_audio = None
                    for fmt in audio_formats:
                        size = fmt.get('filesize') or fmt.get('filesize_approx')
                        if size and size > best_audio_size:
                            best_audio_size = size
                            best_other_audio = fmt
                    if best_other_audio:
                        combined_size_info += f"音频: {best_other_audio.get('format_id')}({best_audio_size/1024/1024:.2f}MB)"
                    logger.info(f"Found best non-M4A audio size: {best_audio_size} bytes")

                # 如果同时找到了视频和音频大小，相加得到预估总大小
                if best_video_size > 0 and best_audio_size > 0:
                    estimated_size_separate = best_video_size + best_audio_size
                    logger.info(f"Method 1 - Separate formats - Video: {best_video_size}, Audio: {best_audio_size}, Total: {estimated_size_separate} bytes")
                elif best_video_size > 0:
                    # 如果只有视频大小，估算音频大小约为视频的10-20%
                    estimated_size_separate = int(best_video_size * 1.15)
                    logger.info(f"Method 1 - Video only: {best_video_size} -> {estimated_size_separate} bytes")

                # 方法2: 查找完整的合并格式（包含音频和视频），优先MP4
                estimated_size_combined = None
                combined_formats = [f for f in video_info['formats']
                                  if (f.get('acodec') != 'none' and f.get('vcodec') != 'none'
                                      and (f.get('filesize') or f.get('filesize_approx')))]

                # 优先选择MP4格式的合并格式
                mp4_combined = [f for f in combined_formats if f.get('ext') == 'mp4']
                if mp4_combined:
                    # 选择最大的MP4合并格式
                    best_combined = max(mp4_combined, key=lambda x: x.get('filesize') or x.get('filesize_approx') or 0)
                    estimated_size_combined = best_combined.get('filesize') or best_combined.get('filesize_approx')
                    logger.info(f"Method 2 - MP4 combined format size: {estimated_size_combined} bytes")
                elif combined_formats:
                    # 如果没有MP4合并格式，选择其他最大的合并格式
                    best_combined = max(combined_formats, key=lambda x: x.get('filesize') or x.get('filesize_approx') or 0)
                    estimated_size_combined = best_combined.get('filesize') or best_combined.get('filesize_approx')
                    logger.info(f"Method 2 - Non-MP4 combined format size: {estimated_size_combined} bytes")

                # 比较两种方法，选择较大的估算值（通常更准确）
                estimated_size = None
                if estimated_size_separate and estimated_size_combined:
                    if estimated_size_separate > estimated_size_combined:
                        estimated_size = estimated_size_separate
                    else:
                        estimated_size = estimated_size_combined
                elif estimated_size_separate:
                    estimated_size = estimated_size_separate
                elif estimated_size_combined:
                    estimated_size = estimated_size_combined

                # 方法3: 如果还没有，使用任何有大小信息的格式
                if not estimated_size:
                    for fmt in video_info['formats']:
                        if fmt.get('filesize') or fmt.get('filesize_approx'):
                            estimated_size = fmt.get('filesize') or fmt.get('filesize_approx')
                            logger.info(f"Method 3 - Fallback format size: {estimated_size} bytes")
                            break

                if estimated_size:
                    video_info['estimated_filesize'] = estimated_size

            logger.info(f"Video info processed, estimated size: {video_info.get('estimated_filesize')}")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to fetch video info for %s: %s", url, exc)

        history_entry = {
            "id": task_id,
            "url": url,
            "title": video_info.get("title", "Unknown"),
            "thumbnail": video_info.get("thumbnail"),
            "uploader": video_info.get("uploader"),
            "downloaded_at": datetime.now().isoformat(),
            "status": "downloading",
            "file_path": None,
            "file_size": None,
            "source": "wecom",
        }
        self.history_manager.add_entry(history_entry)

        # Send news message with video info and thumbnail
        await self._send_video_news(
            task_id=task_id,
            title=history_entry['title'],
            video_info=video_info,  # 这里包含完整的视频信息
            url=url,
            touser=user_id,
            status_text="已收到下载请求"
        )

        self.task_context[task_id] = {
            "touser": user_id,
            "chatid": payload.get("ChatId"),
            "agent_id": agent_id or self.wecom_config.get("agent_id"),
            "title": history_entry["title"],
            "url": url,
            "duration": video_info.get("duration"),  # 保存时长信息
            "uploader": video_info.get("uploader"),  # 保存作者信息
        }

        asyncio.create_task(self._monitor_task(task_id))

    async def _monitor_task(self, task_id: str) -> None:
        context = self.task_context.get(task_id, {})
        try:
            while True:
                await asyncio.sleep(5)
                status = self.downloader.get_download_status(task_id)
                if not status:
                    continue

                current = status.get("status")
                if current in {"completed", "error"}:
                    await self._handle_completion(task_id, status, context)
                    break
        finally:
            self.task_context.pop(task_id, None)

    async def _handle_completion(self, task_id: str, status: Dict[str, Any], context: Dict[str, Any]) -> None:
        status_name = status.get("status")
        update_payload = {"status": status_name}

        if status_name == "completed":
            filepath = status.get("filepath")
            update_payload["file_path"] = filepath
            if filepath:
                try:
                    update_payload["file_size"] = os.path.getsize(filepath)
                except OSError:
                    update_payload["file_size"] = None

            # Send completion news message
            title = context.get("title", "视频")
            public_url = self.wecom_config.get("public_base_url", "").rstrip("/")
            download_link = f"{public_url}/api/download-file/{task_id}" if public_url else None

            # Get complete video info from history
            history_entry = self.history_manager.get_entry(task_id)
            video_info = {}
            if history_entry:
                # 获取历史记录中保存的完整视频信息
                video_info = {
                    "thumbnail": history_entry.get("thumbnail"),
                    "uploader": history_entry.get("uploader") or context.get("uploader"),
                    "duration": context.get("duration"),  # 从上下文获取时长
                    "file_size": history_entry.get("file_size")
                }

                # 如果上下文中没有时长，尝试重新获取视频信息
                if not video_info.get("duration") and context.get("url"):
                    try:
                        fresh_info = await self.downloader.get_video_info(context.get("url"))
                        video_info.update({
                            "duration": fresh_info.get("duration"),
                            "uploader": fresh_info.get("uploader")
                        })
                    except Exception:
                        pass

                # 添加实际文件大小
                if filepath:
                    try:
                        actual_size = os.path.getsize(filepath)
                        video_info["filesize"] = actual_size
                    except OSError:
                        pass

            await self._send_video_news(
                task_id=task_id,
                title=title,
                video_info=video_info,
                url=context.get("url", ""),
                touser=context.get("touser"),
                status_text="✅ 下载完成",
                download_link=download_link
            )
        else:
            update_payload["error_message"] = status.get("error", "未知错误")
            # For error, send text message
            message = f"❌ 下载任务失败，任务 ID: {task_id}\n原因：{status.get('error', '未知错误')}"
            await self._safe_notify(message, **self._notification_targets(context))

        self.history_manager.update_entry(task_id, update_payload)
        self.downloader.cleanup_task(task_id)

    async def _safe_notify(self, message: str, **targets: Any) -> None:
        if not self.client:
            logger.warning("Cannot send WeCom message: client not configured")
            return
        try:
            await self.client.send_text(message, **targets)
        except WeComAPIError as exc:
            logger.error("Failed to send WeCom message: %s", exc)

    async def _send_video_news(
        self,
        task_id: str,
        title: str,
        video_info: Dict[str, Any],
        url: str,
        touser: str,
        status_text: str,
        download_link: Optional[str] = None
    ) -> None:
        if not self.client:
            logger.warning("Cannot send WeCom news: client not configured")
            return

        try:
            # 构建描述文本
            description_parts = [f"📋 任务 ID: {task_id}", f"📊 状态: {status_text}"]

            if video_info.get("uploader"):
                description_parts.append(f"👤 作者: {video_info['uploader']}")

            if video_info.get("duration"):
                duration = video_info["duration"]
                if isinstance(duration, (int, float)):
                    minutes, seconds = divmod(int(duration), 60)
                    description_parts.append(f"⏱️ 时长: {minutes}:{seconds:02d}")

            # 添加文件大小信息 - 优先使用实际文件大小，然后是预估大小
            file_size = (video_info.get("filesize") or
                        video_info.get("filesize_approx") or
                        video_info.get("file_size") or
                        video_info.get("estimated_filesize"))

            if isinstance(file_size, (int, float)) and file_size > 0:
                size_mb = file_size / (1024 * 1024)
                if size_mb >= 1024:
                    size_text = f"📦 大小: {size_mb/1024:.1f} GB"
                else:
                    size_text = f"📦 大小: {size_mb:.1f} MB"

                # 如果是预估大小，添加标识
                if video_info.get("estimated_filesize") and not (video_info.get("filesize") or video_info.get("file_size")):
                    size_text += " (预估)"

                description_parts.append(size_text)

            # 如果有下载链接，添加到描述中
            if download_link:
                description_parts.append(f"🔗 点击下载文件")

            description = "\n".join(description_parts)

            # 获取代理后的缩略图URL
            picurl = None
            if video_info.get("thumbnail"):
                public_url = self.wecom_config.get("public_base_url", "").rstrip("/")
                if public_url:
                    # 使用代理接口
                    import urllib.parse
                    encoded_thumbnail = urllib.parse.quote(video_info["thumbnail"], safe='')
                    picurl = f"{public_url}/api/proxy-thumbnail?url={encoded_thumbnail}"

            await self.client.send_news(
                title=title or "YouTube 视频",
                description=description,
                picurl=picurl,
                url=download_link or url,
                touser=touser
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to send WeCom news: %s", exc)
            # Fallback to text message
            fallback_message = f"{status_text}\n任务 ID: {task_id}\n视频: {title}"
            await self._safe_notify(fallback_message, touser=touser)

    @staticmethod
    def _extract_url(content: str) -> Optional[str]:
        if not content:
            return None

        # 首先尝试匹配完整的http(s)://URL
        match = WeComService.URL_PATTERN.search(content)
        if match:
            return match.group(0)

        # 然后尝试匹配YouTube URL（可能没有协议）
        youtube_match = WeComService.YOUTUBE_PATTERN.search(content)
        if youtube_match:
            url = youtube_match.group(0)
            # 如果没有协议，添加https://
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url
            return url

        return None

    @staticmethod
    def _extract_encrypt(body: str) -> str:
        try:
            root = ET.fromstring(body)
            encrypt = root.findtext("Encrypt")
            if not encrypt:
                raise ValueError
            return encrypt
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail="Invalid callback payload") from exc

    @staticmethod
    def _parse_xml(xml_text: str) -> Dict[str, Any]:
        root = ET.fromstring(xml_text)
        return {child.tag: child.text for child in root}

    @staticmethod
    def _notification_targets(context: Dict[str, Any]) -> Dict[str, Any]:
        targets: Dict[str, Any] = {}
        if context.get("chatid"):
            targets["chatid"] = context["chatid"]
        else:
            targets["touser"] = context.get("touser")
        return targets

    def _is_duplicate_message(self, msg_id: str) -> bool:
        return msg_id in self._recent_msg_index

    def _mark_message_processed(self, msg_id: str) -> None:
        if msg_id in self._recent_msg_index:
            return
        if len(self._recent_msg_ids) == self._recent_msg_ids.maxlen:
            oldest = self._recent_msg_ids.popleft()
            self._recent_msg_index.discard(oldest)
        self._recent_msg_ids.append(msg_id)
        self._recent_msg_index.add(msg_id)

