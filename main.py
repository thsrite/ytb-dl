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
from wecom import WeComService

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
        task_id = await downloader.download_video(request.url, request.format_id)

        # Get video info for history
        info = await downloader.get_video_info(request.url)

        # Add to history
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
        "phase": progress_info.get('phase', 'downloading')  # Add phase info
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


@app.post("/api/config")
async def update_config(updates: dict):
    """更新配置"""
    if config.update_config(updates):
        # 更新downloader的config
        downloader.config = Config()
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
