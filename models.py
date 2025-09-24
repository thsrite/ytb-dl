from pydantic import BaseModel
from typing import Optional, List, Dict
from datetime import datetime


class VideoInfoRequest(BaseModel):
    url: str


class VideoFormat(BaseModel):
    format_id: str
    format_note: str
    ext: str
    quality: Optional[str] = None
    filesize: Optional[int] = None
    vcodec: Optional[str] = None
    acodec: Optional[str] = None
    resolution: Optional[str] = None
    fps: Optional[int] = None
    abr: Optional[float] = None


class VideoInfo(BaseModel):
    id: str
    title: str
    description: Optional[str] = None
    thumbnail: Optional[str] = None
    duration: Optional[int] = None
    uploader: Optional[str] = None
    upload_date: Optional[str] = None
    view_count: Optional[int] = None
    like_count: Optional[int] = None
    formats: List[VideoFormat] = []
    url: str


class DownloadRequest(BaseModel):
    url: str
    format_id: Optional[str] = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
    output_path: Optional[str] = None


class DownloadProgress(BaseModel):
    task_id: str
    status: str  # pending, downloading, processing, completed, error
    progress: float
    speed: Optional[str] = None
    eta: Optional[str] = None
    filename: Optional[str] = None
    message: Optional[str] = None


class DownloadHistory(BaseModel):
    id: str
    url: str
    title: str
    thumbnail: Optional[str] = None
    uploader: Optional[str] = None
    downloaded_at: datetime
    status: str
    file_path: Optional[str] = None
    file_size: Optional[int] = None