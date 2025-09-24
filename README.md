# YouTube Video Downloader

一个基于 FastAPI 和 yt-dlp 的 YouTube 视频下载器，提供 Web 界面和 API 接口。

## 功能特性

- 🎥 支持多种视频质量下载（1080p, 720p, 480p, 360p）
- 🎵 支持纯音频下载（MP3 格式）
- 📊 实时下载进度显示（WebSocket）
- 📝 下载历史记录管理
- 🔍 视频信息预览
- 💾 自定义下载路径
- 🌐 Web 界面操作
- 🔄 断点续传支持

## 技术栈

- **后端**: FastAPI + Python 3.8+
- **前端**: HTML5 + CSS3 + JavaScript
- **下载核心**: yt-dlp
- **实时通信**: WebSocket
- **数据存储**: JSON 文件

## 项目结构

```
ytb_dl/
├── main.py              # FastAPI 主应用
├── downloader.py        # YouTube 下载器核心逻辑
├── models.py            # 数据模型定义
├── config.py            # 配置管理
├── history_manager.py   # 下载历史管理
├── requirements.txt     # 依赖包列表
├── frontend/           # 前端文件
│   ├── index.html      # 主页面
│   ├── css/
│   │   └── styles.css  # 样式文件
│   └── js/
│       └── app.js      # JavaScript 逻辑
├── downloads/          # 默认下载目录
└── config/            # 配置文件目录
```

## 安装部署

### 环境要求

- Python 3.8+
- ffmpeg (音频转换需要)

### 安装步骤

1. 克隆仓库
```bash
git clone https://github.com/thsrite/ytb-dl.git
cd ytb-dl
```

2. 创建虚拟环境（推荐）
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或
venv\Scripts\activate  # Windows
```

3. 安装依赖
```bash
pip install -r requirements.txt
```

4. 安装 ffmpeg
```bash
# Ubuntu/Debian
sudo apt update && sudo apt install ffmpeg

# macOS
brew install ffmpeg

# Windows
# 从 https://ffmpeg.org/download.html 下载并配置环境变量
```

5. 运行应用
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

6. 访问应用
```
http://localhost:8000
```

## API 接口

### 获取视频信息
```http
POST /api/video/info
Content-Type: application/json

{
  "url": "https://www.youtube.com/watch?v=VIDEO_ID"
}
```

### 下载视频
```http
POST /api/download
Content-Type: application/json

{
  "url": "https://www.youtube.com/watch?v=VIDEO_ID",
  "quality": "1080p",
  "audio_only": false
}
```

### 获取下载历史
```http
GET /api/history?limit=10&offset=0
```

### 删除历史记录
```http
DELETE /api/history/{history_id}
```

### WebSocket 连接
```javascript
ws://localhost:8000/ws

// 接收下载进度
{
  "type": "progress",
  "data": {
    "percent": 45.2,
    "speed": "2.3MB/s",
    "eta": "00:01:23",
    "downloaded_bytes": 23456789,
    "total_bytes": 52345678
  }
}
```

## 配置说明

配置文件位于 `config/settings.json`：

```json
{
  "download_path": "./downloads",
  "max_concurrent_downloads": 3,
  "proxy": "",
  "ffmpeg_location": "",
  "output_format": "mp4",
  "audio_quality": "192",
  "video_codec": "h264",
  "keep_video_after_extract": false
}
```

### 配置项说明

- `download_path`: 下载文件保存路径
- `max_concurrent_downloads`: 最大并发下载数
- `proxy`: 代理服务器地址（可选）
- `ffmpeg_location`: ffmpeg 可执行文件路径（可选）
- `output_format`: 输出视频格式
- `audio_quality`: 音频比特率（kbps）
- `video_codec`: 视频编解码器
- `keep_video_after_extract`: 提取音频后是否保留原视频

## 使用说明

### Web 界面使用

1. 打开浏览器访问 `http://localhost:8000`
2. 在输入框粘贴 YouTube 视频链接
3. 点击"获取视频信息"查看视频详情
4. 选择下载质量（视频质量或仅音频）
5. 点击"下载"开始下载
6. 实时查看下载进度
7. 在历史记录中查看已下载的视频

### 命令行使用

```python
from downloader import YTDownloader

# 初始化下载器
dl = YTDownloader()

# 获取视频信息
info = dl.get_video_info("https://www.youtube.com/watch?v=VIDEO_ID")

# 下载视频
dl.download_video(
    url="https://www.youtube.com/watch?v=VIDEO_ID",
    quality="1080p",
    audio_only=False
)
```

## 常见问题

### Q: 下载速度很慢？
A: 可以在配置文件中设置代理服务器，或检查网络连接。

### Q: 提示 ffmpeg 未找到？
A: 请确保已安装 ffmpeg 并正确配置环境变量，或在配置文件中指定 ffmpeg 路径。

### Q: 无法下载某些视频？
A: 某些视频可能有地区限制或需要登录，可尝试使用代理或 cookies。

### Q: 如何下载播放列表？
A: 目前版本暂不支持播放列表下载，后续版本将添加此功能。

## 注意事项

- 请遵守 YouTube 服务条款，仅下载有权访问的内容
- 下载的内容仅供个人使用，请勿用于商业用途
- 尊重内容创作者的版权

## 贡献指南

欢迎提交 Issue 和 Pull Request！

1. Fork 本仓库
2. 创建功能分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 提交 Pull Request

## 许可证

本项目采用 MIT 许可证 - 查看 [LICENSE](LICENSE) 文件了解详情

## 联系方式

- GitHub: [@thsrite](https://github.com/thsrite)
- Issues: [项目问题](https://github.com/thsrite/ytb-dl/issues)

## 更新日志

### v1.0.0 (2025-09-24)
- 初始版本发布
- 支持视频下载功能
- 支持音频提取功能
- Web 界面实现
- 下载历史记录功能
- WebSocket 实时进度更新
