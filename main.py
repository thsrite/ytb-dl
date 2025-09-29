from fastapi import FastAPI, WebSocket, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse, PlainTextResponse
import os
import logging
import httpx
from datetime import datetime
from typing import List

from ytb.models import (
    VideoInfoRequest, VideoInfo, DownloadRequest
)
from ytb.downloader import YTDownloader
from ytb.config import Config
from ytb.history_manager import HistoryManager
from ytb.updater import YtDlpUpdater
from ytb.browser_cookies import BrowserCookieExtractor
from wecom import WeComService
from wecom.message_templates import MessageTemplates
from version import __version__

app = FastAPI(title="YouTube Video Downloader API")

# CORS配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize downloader with Docker-compatible path
download_dir = "/app/downloads" if os.path.exists("/app") else "downloads"
downloader = YTDownloader(download_dir)

# Initialize config
config = Config()

# Initialize history manager
history_manager = HistoryManager()

# Initialize WeCom integration
wecom_service = WeComService(config, downloader, history_manager)

# Initialize yt-dlp updater
updater = YtDlpUpdater()

# Initialize browser cookie extractor with CookieCloud config
cookie_extractor = BrowserCookieExtractor(cookiecloud_config=config.get_cookiecloud_config())

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# WebSocket connections
active_connections: List[WebSocket] = []


@app.get("/")
async def root():
    """返回主页面"""
    try:
        frontend_path = os.path.join(os.path.dirname(__file__), "frontend", "index.html")
        if os.path.exists(frontend_path):
            return FileResponse(frontend_path)
        else:
            return {"message": "YouTube Downloader API", "version": "1.0.0", "error": "Frontend not found"}
    except Exception as e:
        return {"message": "YouTube Downloader API", "version": "1.0.0", "error": str(e)}


@app.post("/api/video-info", response_model=VideoInfo)
async def get_video_info(request: VideoInfoRequest):
    """获取视频信息"""
    try:
        print(f"Fetching video info for URL: {request.url}")
        info = await downloader.get_video_info(request.url)
        print(f"Video info fetched successfully: {info.get('title', 'Unknown')}")
        return VideoInfo(**info)
    except Exception as e:
        print(f"Error in get_video_info: {str(e)}")
        error_msg = str(e)
        if "Unsupported URL" in error_msg:
            error_msg = "不支持的URL格式，请确保输入正确的YouTube链接"
        elif "Video unavailable" in error_msg:
            error_msg = "视频不可用或已被删除"
        raise HTTPException(status_code=400, detail=error_msg)


@app.post("/api/download")
async def start_download(request: DownloadRequest):
    """开始下载视频"""
    try:
        # Generate task_id early
        import uuid
        task_id = str(uuid.uuid4())

        # Set up 403/network error notification callback for Web downloads
        async def web_error_callback(task_id: str, url: str, status: str, retry_count: int = 0, final: bool = False, success: bool = False):
            """Handle 403 and network error notifications for Web downloads"""
            # Get title from history or use a default
            entry = history_manager.get_entry(task_id)
            title = entry.get("title", "Unknown") if entry else "Unknown"

            # Determine error type
            is_network_error = "[网络错误]" in status

            if success:
                # Recovery notification
                if is_network_error:
                    error_msg = "网络错误已恢复"
                else:
                    error_msg = "Cookie刷新成功，下载已恢复"

                await notify_wecom_admins(
                    task_id=task_id,
                    title=title,
                    url=url,
                    source="Web",
                    status="started",
                    error_message=error_msg
                )
            elif final:
                # Final failure notification
                if is_network_error:
                    error_msg = f"网络连接错误（重试{retry_count}次失败）"
                else:
                    error_msg = f"403 Forbidden - 需要登录（重试{retry_count}次失败）"

                await notify_wecom_admins(
                    task_id=task_id,
                    title=title,
                    url=url,
                    source="Web",
                    status="error",
                    error_message=error_msg
                )
            else:
                # Progress notification - use a specific status to indicate retry
                clean_status = status.replace("[网络错误] ", "")

                # Create a notification using the template
                if is_network_error:
                    notification = MessageTemplates.format_admin_notification(
                        task_id=task_id,
                        status='network_retry',
                        user_id="Web User",
                        source="Web",
                        url=url,
                        title=title,
                        error_msg=f"网络错误: {clean_status}",
                        retry_count=retry_count
                    )
                else:
                    notification = MessageTemplates.format_admin_notification(
                        task_id=task_id,
                        status='403_retry',
                        user_id="Web User",
                        source="Web",
                        url=url,
                        title=title,
                        error_msg=clean_status,
                        retry_count=retry_count
                    )

                # Send notification to admins
                wecom_config = config.get_wecom_config()
                if wecom_config.get("notify_admin", False) and wecom_service and wecom_service.client:
                    admin_users = wecom_config.get("admin_users", [])
                    for admin in admin_users:
                        try:
                            await wecom_service.client.send_news(
                                title=notification['title'],
                                description=notification['description'],
                                url=notification['url'] or url,
                                touser=admin
                            )
                            logger.info(f"403/network retry notification sent to admin {admin}")
                        except Exception as e:
                            logger.error(f"Failed to notify admin {admin}: {e}")

        # Get video info BEFORE starting download
        info = await downloader.get_video_info(request.url)

        # Add to history with correct info
        history_entry = {
            "id": task_id,
            "url": request.url,
            "title": info.get("title", "Unknown"),
            "thumbnail": info.get("thumbnail"),
            "uploader": info.get("uploader"),
            "downloaded_at": datetime.now().isoformat(),
            "status": "downloading",
            "file_path": None,
            "file_size": None
        }
        history_manager.add_entry(history_entry)

        # Register the callback
        downloader.set_403_notification_callback(task_id, web_error_callback)

        # Start download with pre-assigned task_id
        actual_task_id = await downloader.download_video_with_id(request.url, task_id, request.format_id)

        # Estimate file size like in WeComService
        estimated_size = None
        if info.get('formats'):
            # Try to get file size from formats
            for fmt in info['formats']:
                if fmt.get('filesize') or fmt.get('filesize_approx'):
                    size = fmt.get('filesize') or fmt.get('filesize_approx')
                    if not estimated_size or size > estimated_size:
                        estimated_size = size

        if estimated_size:
            info['estimated_filesize'] = estimated_size

        # Notify admins if enabled (Web downloads)
        await notify_wecom_admins(
            task_id=task_id,
            title=info.get("title", "Unknown"),
            url=request.url,
            source="Web",
            video_info=info,
            status="started"
        )

        # Start monitoring task for completion
        import asyncio
        asyncio.create_task(monitor_web_download(
            task_id=task_id,
            title=info.get("title", "Unknown"),
            url=request.url,
            video_info=info
        ))

        return {"task_id": task_id, "message": "Download started"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/download-status/{task_id}")
async def get_download_status(task_id: str):
    """获取下载进度"""
    status = downloader.get_download_status(task_id)

    if status is None:
        raise HTTPException(status_code=404, detail="Task not found")

    progress_info = status.get('progress', {})

    # Format speed
    speed = progress_info.get('speed', 0)
    speed_str = None
    if speed:
        if speed > 1024 * 1024:
            speed_str = f"{speed / 1024 / 1024:.2f} MB/s"
        elif speed > 1024:
            speed_str = f"{speed / 1024:.2f} KB/s"
        else:
            speed_str = f"{speed:.0f} B/s"

    # Format sizes
    def format_size(bytes_size):
        if not bytes_size:
            return None
        if bytes_size > 1024 * 1024 * 1024:
            return f"{bytes_size / 1024 / 1024 / 1024:.2f} GB"
        elif bytes_size > 1024 * 1024:
            return f"{bytes_size / 1024 / 1024:.2f} MB"
        elif bytes_size > 1024:
            return f"{bytes_size / 1024:.2f} KB"
        else:
            return f"{bytes_size} B"

    response = {
        "task_id": task_id,
        "status": status.get('status', 'unknown'),
        "progress": progress_info.get('percent', 0),
        "speed": speed_str,
        "downloaded_bytes": progress_info.get('downloaded_bytes', 0),
        "total_bytes": progress_info.get('total_bytes', 0),
        "downloaded_size": format_size(progress_info.get('downloaded_bytes', 0)),
        "total_size": format_size(progress_info.get('total_bytes', 0)),
        "eta": progress_info.get('eta'),
        "filename": status.get('filename'),
        "message": status.get('error') if status.get('status') == 'error' else None,
        "phase": progress_info.get('phase', 'downloading'),  # Add phase info
        "current_time": progress_info.get('current_time'),  # Add transcoding current time
        "total_time": progress_info.get('total_time')  # Add transcoding total time
    }

    # Update history if completed or error
    if status.get('status') in ['completed', 'error']:
        updates = {'status': status.get('status')}
        if status.get('status') == 'completed':
            updates['file_path'] = status.get('filepath')
            if status.get('filepath') and os.path.exists(status.get('filepath')):
                updates['file_size'] = os.path.getsize(status.get('filepath'))
        elif status.get('status') == 'error':
            updates['error_message'] = status.get('error', 'Unknown error')
        history_manager.update_entry(task_id, updates)

    return response


@app.get("/api/history")
async def get_history():
    """获取下载历史"""
    return history_manager.get_all()


@app.delete("/api/history/{task_id}")
async def delete_history(task_id: str):
    """删除历史记录和相关文件"""
    # 查找要删除的记录
    entry_to_delete = history_manager.get_entry(task_id)

    if entry_to_delete:
        # Check if task is currently transcoding and cancel it
        status = downloader.get_download_status(task_id)
        if status and (status.get('status') == 'transcoding' or
                      (status.get('progress', {}).get('phase') == 'transcoding')):
            # Cancel the transcoding process and delete original file
            print(f"Cancelling active transcoding for task {task_id}")
            await downloader.transcoder.cancel_transcode(task_id, delete_input=True)

        # 删除文件
        if entry_to_delete.get('file_path'):
            file_path = entry_to_delete['file_path']
            # 如果是相对路径，转换为绝对路径
            if not os.path.isabs(file_path):
                file_path = os.path.join(os.path.dirname(__file__), file_path.lstrip('/'))

            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    print(f"Deleted file: {file_path}")
                except Exception as e:
                    print(f"Error deleting file: {e}")

        # 从历史中删除
        history_manager.delete_entry(task_id)

        # 清理下载器中的任务
        downloader.cleanup_task(task_id)

        return {"message": "History entry and file deleted"}
    else:
        raise HTTPException(status_code=404, detail="History entry not found")


@app.post("/api/redownload/{task_id}")
async def redownload_video(task_id: str):
    """重新下载视频（删除原文件并重新下载）"""
    # 查找原始下载记录
    entry = history_manager.get_entry(task_id)

    if not entry:
        raise HTTPException(status_code=404, detail="Download record not found")

    # 获取原始URL
    original_url = entry.get('url')
    if not original_url:
        raise HTTPException(status_code=400, detail="Original URL not found in history")

    # 删除原文件
    if entry.get('file_path'):
        file_path = entry['file_path']
        # 如果是相对路径，转换为绝对路径
        if not os.path.isabs(file_path):
            file_path = os.path.join(os.path.dirname(__file__), file_path.lstrip('/'))

        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                print(f"Deleted old file for redownload: {file_path}")
            except Exception as e:
                print(f"Error deleting old file: {e}")

    # 清理旧的下载任务
    downloader.cleanup_task(task_id)

    # 从历史中删除旧记录
    history_manager.delete_entry(task_id)

    # 开始新的下载
    try:
        # Generate new task_id
        import uuid
        new_task_id = str(uuid.uuid4())

        # Get video info BEFORE starting download
        info = await downloader.get_video_info(original_url)

        # Add to history with correct info
        history_entry = {
            "id": new_task_id,
            "url": original_url,
            "title": info.get("title", "Unknown"),
            "thumbnail": info.get("thumbnail"),
            "uploader": info.get("uploader"),
            "downloaded_at": datetime.now().isoformat(),
            "status": "downloading",
            "file_path": None,
            "file_size": None
        }
        history_manager.add_entry(history_entry)

        # Start download with new task_id
        actual_task_id = await downloader.download_video_with_id(original_url, new_task_id)

        # Start monitoring task for completion
        import asyncio
        asyncio.create_task(monitor_web_download(
            task_id=new_task_id,
            title=info.get("title", "Unknown"),
            url=original_url,
            video_info=info
        ))

        return {"task_id": new_task_id, "message": "Redownload started", "original_task_id": task_id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/proxy-thumbnail")
async def proxy_thumbnail(url: str):
    """代理YouTube缩略图"""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url)
            response.raise_for_status()

            # 获取内容类型
            content_type = response.headers.get("content-type", "image/jpeg")

            return StreamingResponse(
                iter([response.content]),
                media_type=content_type,
                headers={
                    "Cache-Control": "public, max-age=3600",
                    "Access-Control-Allow-Origin": "*"
                }
            )
    except Exception as e:
        logger.error(f"Error proxying thumbnail {url}: {e}")
        raise HTTPException(status_code=404, detail="Unable to fetch thumbnail")


@app.websocket("/ws/progress")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket连接用于实时进度更新"""
    await websocket.accept()
    active_connections.append(websocket)

    try:
        while True:
            # Wait for any message from client
            data = await websocket.receive_text()

            # Send current status of all active downloads
            active_tasks = []
            for task_id, status in downloader.active_downloads.items():
                progress_info = status.get('progress', {})
                active_tasks.append({
                    "task_id": task_id,
                    "status": status.get('status'),
                    "progress": progress_info.get('percent', 0)
                })

            await websocket.send_json({"active_tasks": active_tasks})
    except Exception:
        pass
    finally:
        active_connections.remove(websocket)


@app.get("/api/download-file/{task_id}")
async def download_file(task_id: str):
    """下载文件到客户端"""
    # 首先尝试从active downloads获取
    status = downloader.get_download_status(task_id)

    if status and status.get('status') == 'completed':
        filepath = status.get('filepath')
    else:
        # 如果不在active downloads，从历史记录中查找
        filepath = None
        entry = history_manager.get_entry(task_id)
        if entry:
            filepath = entry.get('file_path')

        if not filepath:
            raise HTTPException(status_code=404, detail="File not found in history")

    # 处理文件路径
    if not os.path.isabs(filepath):
        # 如果是相对路径，转换为绝对路径
        filepath = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "downloads", os.path.basename(filepath)))

    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail=f"File not found: {filepath}")

    return FileResponse(
        path=filepath,
        filename=os.path.basename(filepath),
        media_type='application/octet-stream'
    )


@app.get("/api/stream/{task_id}")
async def stream_video(task_id: str):
    """流式播放视频"""
    # 查找文件路径
    filepath = None

    # 从active downloads查找
    status = downloader.get_download_status(task_id)
    if status and status.get('status') == 'completed':
        filepath = status.get('filepath')

    # 从历史记录中查找
    if not filepath:
        entry = history_manager.get_entry(task_id)
        if entry:
            filepath = entry.get('file_path')

    if not filepath:
        raise HTTPException(status_code=404, detail="Video not found")

    # 处理文件路径
    if not os.path.isabs(filepath):
        filepath = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "downloads", os.path.basename(filepath)))

    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail=f"Video file not found: {filepath}")

    # 获取文件大小
    file_size = os.path.getsize(filepath)

    def iterfile():
        with open(filepath, 'rb') as f:
            while chunk := f.read(1024 * 1024):  # 1MB chunks
                yield chunk

    # 根据文件扩展名设置正确的媒体类型
    ext = os.path.splitext(filepath)[1].lower()
    media_type = 'video/mp4' if ext == '.mp4' else 'video/webm' if ext == '.webm' else 'application/octet-stream'

    return StreamingResponse(
        iterfile(),
        media_type=media_type,
        headers={
            "Content-Length": str(file_size),
            "Accept-Ranges": "bytes",
        }
    )


@app.get("/api/config")
async def get_config():
    """获取配置"""
    return config.config


@app.get("/api/version")
async def get_version():
    """获取版本信息"""
    import yt_dlp
    import sys
    return {
        "app_version": __version__,
        "yt_dlp_version": yt_dlp.version.__version__,
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    }


@app.get("/api/yt-dlp/check-update")
async def check_yt_dlp_update():
    """检查yt-dlp更新"""
    return await updater.check_for_updates()


@app.post("/api/yt-dlp/update")
async def update_yt_dlp():
    """更新yt-dlp到最新版本"""
    global updater
    result = updater.update_yt_dlp()
    if result["success"]:
        # Reinitialize updater with new version
        updater = YtDlpUpdater()
    return result


@app.get("/api/yt-dlp/version-info")
async def get_yt_dlp_version_info():
    """获取详细的版本信息"""
    return await updater.get_version_info()


@app.get("/api/browser-cookies/detect")
async def detect_browsers():
    """检测可用的浏览器"""
    return {
        "available_browsers": cookie_extractor.detect_available_browsers(),
        "system_info": cookie_extractor.get_system_info()
    }


@app.post("/api/browser-cookies/import")
async def import_browser_cookies(request: dict):
    """从浏览器导入cookies"""
    browser = request.get('browser', 'firefox')
    domain = request.get('domain', 'youtube.com')

    result = cookie_extractor.extract_cookies_from_browser(browser, domain)

    if result:
        # Save to config
        config.update_config({
            "browser_cookies": {
                "enabled": True,
                "browser": browser,
                "auto_refresh": True,
                "refresh_interval_minutes": 25
            }
        })

        return {
            "success": True,
            "message": f"Successfully imported cookies from {browser}",
            "data": {
                "browser": result['browser'],
                "extracted_at": result['extracted_at'],
                "cookie_count": len(result['cookies'].split('\n')) - 1  # Exclude header
            }
        }
    else:
        return {
            "success": False,
            "message": f"Failed to import cookies from {browser}",
            "error": "Could not extract cookies. Make sure the browser is installed and has active YouTube session."
        }


@app.get("/api/browser-cookies/status")
async def get_browser_cookie_status():
    """获取浏览器Cookie状态"""
    browser_config = config.config.get('browser_cookies', {})

    # Check if cookies exist
    cookies_exist = os.path.exists(cookie_extractor.cookies_file)
    cookies_fresh = False
    cookies_age = None

    if cookies_exist and cookie_extractor.last_extraction_time:
        from datetime import datetime
        age = datetime.now() - cookie_extractor.last_extraction_time
        cookies_age = str(age)
        cookies_fresh = age.total_seconds() < (25 * 60)  # Less than 25 minutes

    return {
        "enabled": browser_config.get('enabled', False),
        "browser": browser_config.get('browser', 'firefox'),
        "auto_refresh": browser_config.get('auto_refresh', True),
        "cookies_exist": cookies_exist,
        "cookies_fresh": cookies_fresh,
        "cookies_age": cookies_age,
        "last_extraction": cookie_extractor.last_extraction_time.isoformat() if cookie_extractor.last_extraction_time else None
    }


@app.post("/api/browser-cookies/refresh")
async def refresh_browser_cookies():
    """手动刷新浏览器cookies"""
    browser_config = config.config.get('browser_cookies', {})
    browser = browser_config.get('browser', 'firefox')

    # Force refresh
    cookie_extractor.last_extraction_time = None
    result = cookie_extractor.extract_cookies_from_browser(browser)

    if result:
        return {
            "success": True,
            "message": "Cookies refreshed successfully",
            "data": {
                "browser": result['browser'],
                "extracted_at": result['extracted_at']
            }
        }
    else:
        return {
            "success": False,
            "message": "Failed to refresh cookies"
        }


@app.post("/api/config")
async def update_config(updates: dict):
    """更新配置"""
    if config.update_config(updates):
        # 不要重新加载配置，直接使用更新后的配置
        downloader.config = config
        # 更新转码器配置
        downloader.transcoder.config = config.config
        return {"message": "Config updated successfully"}
    else:
        raise HTTPException(status_code=500, detail="Failed to update config")


@app.get("/api/wecom/config")
async def get_wecom_config():
    """获取企业微信集成配置"""
    return config.get_wecom_config()


@app.post("/api/wecom/config")
async def update_wecom_config(updates: dict):
    """更新企业微信集成配置并刷新服务"""
    clean_updates = {}
    for key, value in updates.items():
        if key == "agent_id" and value not in (None, ""):
            try:
                clean_updates[key] = int(value)
            except ValueError as exc:  # noqa: BLE001
                raise HTTPException(status_code=400, detail="AgentID 必须是整数") from exc
        else:
            clean_updates[key] = value or ""

    encoding_key = clean_updates.get("encoding_aes_key")
    if encoding_key and len(encoding_key) != 43:
        raise HTTPException(status_code=400, detail="EncodingAESKey 必须为43位")

    current = config.get_wecom_config()
    current.update(clean_updates)

    if not config.update_config({"wecom": current}):
        raise HTTPException(status_code=500, detail="保存配置失败")

    wecom_service.reload_config()
    return {"message": "WeCom config updated"}


async def monitor_web_download(task_id: str, title: str, url: str, video_info: dict) -> None:
    """Monitor Web download task and send completion/error notifications"""
    import asyncio

    try:
        while True:
            await asyncio.sleep(5)
            status = downloader.get_download_status(task_id)

            if not status:
                continue

            current = status.get("status")

            if current == "completed":
                # Get actual file size if available
                filepath = status.get("filepath")
                if filepath and os.path.exists(filepath):
                    try:
                        actual_size = os.path.getsize(filepath)
                        video_info['filesize'] = actual_size
                    except:
                        pass

                # Get actual video info from downloader if available
                if status.get('video_info'):
                    actual_info = status.get('video_info')
                    # Update with real title and info from download
                    history_manager.update_entry(task_id, {
                        "status": "completed",
                        "title": actual_info.get('title', title),
                        "thumbnail": actual_info.get('thumbnail'),
                        "uploader": actual_info.get('uploader'),
                        "file_path": filepath,
                        "file_size": actual_info.get('filesize') or video_info.get('filesize')
                    })
                else:
                    # Fallback to original update
                    history_manager.update_entry(task_id, {
                        "status": "completed",
                        "file_path": filepath,
                        "file_size": video_info.get('filesize')
                    })

                # Generate download link for admins
                wecom_config = config.get_wecom_config()
                public_url = wecom_config.get("public_base_url", "").rstrip("/")
                download_link = f"{public_url}/api/download-file/{task_id}" if public_url else None

                # Notify admins of completion with download link
                await notify_wecom_admins(
                    task_id=task_id,
                    title=title,
                    url=url,
                    source="Web",
                    video_info=video_info,
                    status="completed",
                    download_link=download_link
                )
                break

            elif current == "error":
                error_msg = status.get("error", "未知错误")

                # Update history
                history_manager.update_entry(task_id, {
                    "status": "error",
                    "error_message": error_msg
                })

                # Notify admins of error
                await notify_wecom_admins(
                    task_id=task_id,
                    title=title,
                    url=url,
                    source="Web",
                    video_info=video_info,
                    status="error",
                    error_message=error_msg
                )
                break

    except Exception as e:
        logger.error(f"Error monitoring web download {task_id}: {e}")
    finally:
        # Clean up task
        downloader.cleanup_task(task_id)


async def notify_wecom_admins(
    task_id: str,
    title: str,
    url: str,
    source: str = "Web",
    video_info: dict = None,
    status: str = "started",
    error_message: str = None,
    download_link: str = None
) -> None:
    """Notify admin users about download tasks from Web interface"""
    wecom_config = config.get_wecom_config()

    if not wecom_config.get("notify_admin", False):
        return

    admin_users = wecom_config.get("admin_users", [])
    if not admin_users:
        return

    # Map status to our unified template format
    template_status = 'start'
    if status == "completed":
        template_status = 'complete'
    elif status == "error":
        template_status = 'error'

    # Format file size if available
    file_size_text = None
    if video_info:
        file_size = (video_info.get("filesize") or
                    video_info.get("filesize_approx") or
                    video_info.get("estimated_filesize"))

        if isinstance(file_size, (int, float)) and file_size > 0:
            size_mb = file_size / (1024 * 1024)
            if size_mb >= 1024:
                file_size_text = f"{size_mb/1024:.1f} GB"
            else:
                file_size_text = f"{size_mb:.1f} MB"

            if video_info.get("estimated_filesize") and not video_info.get("filesize"):
                file_size_text += " (预估)"

    # Get unified admin notification template
    notification = MessageTemplates.format_admin_notification(
        task_id=task_id,
        status=template_status,
        user_id="Web User",  # Web downloads don't have specific user
        source=source,
        url=url,
        title=title,
        download_link=download_link,
        error_msg=error_message,
        file_size=file_size_text
    )

    # Get proxy thumbnail URL if available
    picurl = None
    if video_info and video_info.get("thumbnail"):
        public_url = wecom_config.get("public_base_url", "").rstrip("/")
        if public_url:
            import urllib.parse
            encoded_thumbnail = urllib.parse.quote(video_info["thumbnail"], safe='')
            picurl = f"{public_url}/api/proxy-thumbnail?url={encoded_thumbnail}"

    # Send notification to all admins using news format
    if wecom_service and wecom_service.client:
        for admin in admin_users:
            try:
                # Use news format for better presentation
                await wecom_service.client.send_news(
                    title=notification['title'],
                    description=notification['description'],
                    picurl=picurl,
                    url=notification['url'] or url,
                    touser=admin
                )
                logger.info(f"Admin notification sent to {admin} for task {task_id} (status: {status})")
            except Exception as e:
                logger.error(f"Failed to notify admin {admin}: {e}")


@app.post("/api/wecom/test-admin")
async def test_admin_notification():
    """Test admin notification"""
    if not wecom_service:
        raise HTTPException(status_code=503, detail="WeChat Work service is not configured")

    # Reload config to get latest admin settings
    wecom_service.reload_config()

    success = await wecom_service.send_admin_test()

    if success:
        admin_users = config.get_wecom_config().get("admin_users", [])
        return {"success": True, "message": f"测试通知已发送给 {len(admin_users)} 个管理员"}
    else:
        admin_users = config.get_wecom_config().get("admin_users", [])
        if not admin_users:
            return {"success": False, "message": "请先配置管理员用户ID"}
        elif not wecom_service.client:
            return {"success": False, "message": "企业微信客户端未正确配置，请检查CorpID、AgentID和App Secret"}
        else:
            return {"success": False, "message": "发送测试通知失败，请检查配置"}


@app.get("/api/wecom/callback")
async def wecom_verify(
    msg_signature: str,
    timestamp: str,
    nonce: str,
    echostr: str,
):
    """企业微信回调URL验证"""
    echo = wecom_service.verify_url(msg_signature, timestamp, nonce, echostr)
    return PlainTextResponse(echo)


@app.post("/api/wecom/callback")
async def wecom_callback(
    request: Request,
    msg_signature: str,
    timestamp: str,
    nonce: str,
):
    """企业微信消息回调处理"""
    body = (await request.body()).decode("utf-8")
    response_text = await wecom_service.handle_callback(
        msg_signature,
        timestamp,
        nonce,
        body,
    )
    return PlainTextResponse(response_text)


@app.get("/api/config/cookies")
async def get_cookies():
    """获取cookies内容"""
    try:
        # Use Docker-compatible path
        cookies_file = "/app/config/cookies.txt" if os.path.exists("/app") else os.path.join("config", "cookies.txt")
        if os.path.exists(cookies_file):
            with open(cookies_file, 'r', encoding='utf-8') as f:
                content = f.read()
            return {"content": content}
        else:
            return {"content": ""}
    except Exception as e:
        logger.error(f"Error getting cookies: {e}")
        return {"content": ""}

@app.post("/api/config/cookies")
async def upload_cookies(data: dict):
    """上传cookies内容"""
    try:
        content = data.get('content', '')
        if not content:
            raise HTTPException(status_code=400, detail="No cookies content provided")

        # Use Docker-compatible path
        if os.path.exists("/app"):
            cookies_file = "/app/config/cookies.txt"
            config_dir = "/app/config"
        else:
            cookies_file = os.path.join("config", "cookies.txt")
            config_dir = "config"

        # 确保config目录存在
        os.makedirs(config_dir, exist_ok=True)

        with open(cookies_file, 'w', encoding='utf-8') as f:
            f.write(content)

        # 重新加载下载器配置以应用新的cookies
        downloader.config = Config()

        return {"message": "Cookies uploaded successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/cookiecloud/status")
async def get_cookiecloud_status():
    """获取CookieCloud配置状态"""
    cookiecloud_config = config.get_cookiecloud_config()

    # Test connection if configured
    if cookiecloud_config.get('enabled'):
        success, message = cookie_extractor.test_cookiecloud_connection()
        return {
            "enabled": True,
            "configured": bool(cookiecloud_config.get('server_url')),
            "server_url": cookiecloud_config.get('server_url', ''),
            "auto_sync": cookiecloud_config.get('auto_sync', True),
            "sync_interval_minutes": cookiecloud_config.get('sync_interval_minutes', 30),
            "connection_status": success,
            "connection_message": message
        }
    else:
        return {
            "enabled": False,
            "configured": False,
            "server_url": "",
            "auto_sync": False,
            "sync_interval_minutes": 30,
            "connection_status": False,
            "connection_message": "CookieCloud is not enabled"
        }


@app.post("/api/cookiecloud/sync")
async def sync_cookiecloud():
    """手动触发CookieCloud同步"""
    success, message = cookie_extractor.sync_cookiecloud()

    if success:
        # 重新加载下载器配置以应用新的cookies
        downloader.config = Config()
        return {"success": True, "message": message}
    else:
        raise HTTPException(status_code=500, detail=message)


@app.post("/api/cookiecloud/config")
async def update_cookiecloud_config(data: dict):
    """更新CookieCloud配置"""
    try:
        # Update configuration
        config.update_config({
            "cookiecloud": {
                "enabled": data.get('enabled', False),
                "server_url": data.get('server_url', ''),
                "uuid_key": data.get('uuid_key', ''),
                "password": data.get('password', ''),
                "auto_sync": data.get('auto_sync', True),
                "sync_interval_minutes": data.get('sync_interval_minutes', 30)
            }
        })

        # Re-initialize cookie extractor with new config
        global cookie_extractor
        cookie_extractor = BrowserCookieExtractor(cookiecloud_config=config.get_cookiecloud_config())

        # Test connection if enabled
        if data.get('enabled'):
            success, message = cookie_extractor.test_cookiecloud_connection()
            return {
                "message": "Configuration updated",
                "connection_test": {
                    "success": success,
                    "message": message
                }
            }
        else:
            return {"message": "CookieCloud disabled"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/cookiecloud/test")
async def test_cookiecloud_connection(data: dict):
    """测试CookieCloud连接"""
    from ytb.cookiecloud import CookieCloud

    # Create temporary CookieCloud instance for testing
    test_config = {
        'server_url': data.get('server_url', ''),
        'uuid_key': data.get('uuid_key', ''),
        'password': data.get('password', '')
    }

    cookiecloud = CookieCloud(test_config)
    success, message = cookiecloud.test_connection()

    return {
        "success": success,
        "message": message
    }

# Serve frontend static files
frontend_dir = os.path.join(os.path.dirname(__file__), "frontend")
if os.path.exists(frontend_dir):
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")
    # Also serve CSS and JS files directly
    css_dir = os.path.join(frontend_dir, "css")
    js_dir = os.path.join(frontend_dir, "js")
    if os.path.exists(css_dir):
        app.mount("/css", StaticFiles(directory=css_dir), name="css")
    if os.path.exists(js_dir):
        app.mount("/js", StaticFiles(directory=js_dir), name="js")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=9832, reload=True)
