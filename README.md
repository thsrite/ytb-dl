# YouTube Video Downloader

基于Python和纯HTML/CSS/JavaScript的YouTube视频下载器，使用yt-dlp作为核心下载工具。

## 功能特性

- 🎥 支持YouTube视频下载
- 📊 显示视频详细信息（标题、作者、时长、观看数等）
- 🎯 支持多种质量和格式选择
- 🔄 实时下载进度显示
- 🎵 自动合并音视频轨道
- 📝 下载历史记录
- 🎨 美观的用户界面

## 技术栈

### 后端
- Python 3.12+
- FastAPI - Web框架
- yt-dlp - YouTube下载核心
- uvicorn - ASGI服务器

### 前端
- 纯HTML5
- CSS3（响应式设计）
- Vanilla JavaScript（无框架依赖）

## 安装要求

1. Python 3.12 或更高版本
2. ffmpeg（用于音视频合并）

## 安装步骤

### 1. 安装ffmpeg

macOS:
```bash
brew install ffmpeg
```

Windows:
从 https://ffmpeg.org/download.html 下载并配置环境变量

Linux:
```bash
sudo apt update
sudo apt install ffmpeg
```

### 2. 安装Python依赖

```bash
cd backend
pip install -r requirements.txt
```

## 运行项目

### 方法1: 使用启动脚本

```bash
./start.sh
```

### 方法2: 手动启动

1. 启动后端服务器：
```bash
cd backend
python main.py
```

2. 在浏览器中打开：
```
http://localhost:9832/static/index.html
```

## 使用说明

1. 在输入框中粘贴YouTube视频链接
2. 点击"获取信息"按钮获取视频详情
3. 选择下载质量（默认为最佳质量）
4. 点击"开始下载"
5. 等待下载完成，点击"保存文件"

## 项目结构

```
ytb_dl/
├── backend/
│   ├── main.py           # FastAPI主应用
│   ├── downloader.py      # yt-dlp封装
│   ├── models.py          # 数据模型
│   └── requirements.txt   # Python依赖
├── frontend/
│   ├── index.html         # 主页面
│   ├── css/
│   │   └── styles.css     # 样式文件
│   └── js/
│       └── app.js         # JavaScript逻辑
├── downloads/             # 下载文件存储目录
├── start.sh              # 启动脚本
└── README.md             # 项目说明
```

## API端点

- `POST /api/video-info` - 获取视频信息
- `POST /api/download` - 开始下载
- `GET /api/download-status/{task_id}` - 获取下载进度
- `GET /api/history` - 获取下载历史
- `GET /api/download-file/{task_id}` - 下载文件

## 注意事项

1. 确保有足够的磁盘空间存储下载的视频
2. 下载速度取决于网络连接质量
3. 某些视频可能由于版权限制无法下载
4. 请遵守YouTube的服务条款和版权法规

## 故障排除

### ffmpeg未找到
确保ffmpeg已安装并在系统PATH中

### 下载失败
- 检查网络连接
- 确认视频URL正确
- 某些地区可能需要代理

### 端口被占用
修改`backend/main.py`中的端口号：
```python
uvicorn.run(app, host="0.0.0.0", port=8001)  # 改为其他端口
```

## License

本项目仅供学习和个人使用，请勿用于商业用途。