// API Base URL - dynamically determined based on current page location
const API_BASE_URL = window.location.origin || `${window.location.protocol}//${window.location.host}`;

// Log the API base URL for debugging
console.log('API Base URL:', API_BASE_URL);

// Global variables
let currentTaskId = null;
let progressInterval = null;
let ws = null;

// DOM Elements
const elements = {
    // Tabs
    tabButtons: document.querySelectorAll('.tab-button'),
    downloadTab: document.getElementById('download-tab'),
    historyTab: document.getElementById('history-tab'),
    settingsTab: document.getElementById('settings-tab'),

    // Input Section
    videoUrl: document.getElementById('video-url'),
    fetchBtn: document.getElementById('fetch-btn'),
    fetchLoading: document.getElementById('fetch-loading'),

    // Video Info Section
    videoInfo: document.getElementById('video-info'),
    videoThumbnail: document.getElementById('video-thumbnail'),
    videoTitle: document.getElementById('video-title'),
    videoDescription: document.getElementById('video-description'),
    videoAuthor: document.getElementById('video-author'),
    videoDuration: document.getElementById('video-duration'),
    videoViews: document.getElementById('video-views'),
    videoLikes: document.getElementById('video-likes'),
    formatSelect: document.getElementById('format-select'),

    // Download Control Section
    downloadControl: document.getElementById('download-control'),
    downloadBtn: document.getElementById('download-btn'),
    downloadProgress: document.getElementById('download-progress'),
    progressStatus: document.getElementById('progress-status'),
    progressPercent: document.getElementById('progress-percent'),
    progressFill: document.getElementById('progress-fill'),
    downloadSpeed: document.getElementById('download-speed'),
    downloadSize: document.getElementById('download-size'),
    totalSize: document.getElementById('total-size'),
    downloadEta: document.getElementById('download-eta'),
    downloadComplete: document.getElementById('download-complete'),
    downloadFilename: document.getElementById('download-filename'),
    playVideoBtn: document.getElementById('play-video-btn'),
    saveFileBtn: document.getElementById('save-file-btn'),
    newDownloadBtn: document.getElementById('new-download-btn'),

    // History
    historyList: document.getElementById('history-list'),
    noHistory: document.getElementById('no-history'),

    // Settings
    cookiesStatus: document.getElementById('cookies-status'),
    cookiesInput: document.getElementById('cookies-input'),
    saveCookiesBtn: document.getElementById('save-cookies-btn'),
    proxyInput: document.getElementById('proxy-input'),
    userAgentInput: document.getElementById('user_agent'),
    saveSettingsBtn: document.getElementById('save-settings-btn'),
    resetSettingsBtn: document.getElementById('reset-settings-btn'),

    // Settings checkboxes
    nocheckcertificate: document.getElementById('nocheckcertificate'),
    geoBypass: document.getElementById('geo_bypass'),
    skipUnavailableFragments: document.getElementById('skip_unavailable_fragments'),

    // Settings numbers
    sleepInterval: document.getElementById('sleep_interval'),
    retries: document.getElementById('retries'),
    fragmentRetries: document.getElementById('fragment_retries'),

    // Custom parameters
    customParams: document.getElementById('custom-params'),

    // WeCom settings
    wecomCorpId: document.getElementById('wecom-corp-id'),
    wecomAgentId: document.getElementById('wecom-agent-id'),
    wecomAppSecret: document.getElementById('wecom-app-secret'),
    wecomToken: document.getElementById('wecom-token'),
    wecomEncodingKey: document.getElementById('wecom-encoding-key'),
    wecomPublicUrl: document.getElementById('wecom-public-url'),
    wecomDefaultFormat: document.getElementById('wecom-default-format'),
    wecomProxyDomain: document.getElementById('wecom-proxy-domain')
};

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    initTabs();
    initEventListeners();
    loadHistory();
    loadSettings();
    initWebSocket();
    loadVersionInfo();

    // Ensure input field is not disabled
    if (elements.videoUrl) {
        elements.videoUrl.disabled = false;
        elements.videoUrl.readOnly = false;
        elements.videoUrl.style.pointerEvents = 'auto';
        console.log('Video URL input field initialized:', elements.videoUrl);
    }

    // Start global progress monitoring for all downloading tasks
    startProgressPolling();
});

// Tab Management
function initTabs() {
    elements.tabButtons.forEach(button => {
        button.addEventListener('click', () => {
            const tabName = button.dataset.tab;
            switchTab(tabName);
        });
    });
}

function switchTab(tabName) {
    // Update tab buttons
    elements.tabButtons.forEach(btn => {
        if (btn.dataset.tab === tabName) {
            btn.classList.add('active');
        } else {
            btn.classList.remove('active');
        }
    });

    // Hide all tabs
    elements.downloadTab.classList.add('hidden');
    elements.historyTab.classList.add('hidden');
    elements.settingsTab.classList.add('hidden');

    // Show selected tab
    if (tabName === 'download') {
        elements.downloadTab.classList.remove('hidden');
    } else if (tabName === 'history') {
        elements.historyTab.classList.remove('hidden');
        loadHistory();
    } else if (tabName === 'settings') {
        elements.settingsTab.classList.remove('hidden');
    }
}

// Event Listeners
function initEventListeners() {
    elements.fetchBtn.addEventListener('click', fetchVideoInfo);
    elements.downloadBtn.addEventListener('click', startDownload);
    elements.playVideoBtn.addEventListener('click', playCurrentVideo);
    elements.saveFileBtn.addEventListener('click', saveFile);
    elements.newDownloadBtn.addEventListener('click', resetDownload);

    // Settings event listeners
    elements.saveCookiesBtn.addEventListener('click', saveCookies);
    elements.saveSettingsBtn.addEventListener('click', saveSettings);
    elements.resetSettingsBtn.addEventListener('click', resetSettings);

    // Enter key on URL input
    elements.videoUrl.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            fetchVideoInfo();
        }
    });
}

// Fetch Video Info
async function fetchVideoInfo() {
    const url = elements.videoUrl.value.trim();
    if (!url) {
        alert('请输入视频链接');
        return;
    }

    // Show loading
    elements.fetchBtn.disabled = true;
    elements.fetchLoading.classList.remove('hidden');
    hideVideoInfo();

    try {
        const response = await fetch(`${API_BASE_URL}/api/video-info`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ url })
        });

        if (!response.ok) {
            throw new Error('获取视频信息失败');
        }

        const videoData = await response.json();
        displayVideoInfo(videoData);
    } catch (error) {
        console.error('Error fetching video info:', error);
        alert('获取视频信息失败: ' + error.message);
    } finally {
        elements.fetchBtn.disabled = false;
        elements.fetchLoading.classList.add('hidden');
    }
}

// Display Video Info
function displayVideoInfo(videoData) {
    // Update video details
    // 使用代理端点获取缩略图
    if (videoData.thumbnail) {
        elements.videoThumbnail.src = `${API_BASE_URL}/api/proxy-thumbnail?url=${encodeURIComponent(videoData.thumbnail)}`;
    } else {
        elements.videoThumbnail.src = '';
    }
    elements.videoTitle.textContent = videoData.title || '未知标题';
    elements.videoDescription.textContent = videoData.description || '';
    elements.videoAuthor.textContent = videoData.uploader || '未知作者';
    elements.videoDuration.textContent = formatDuration(videoData.duration);
    elements.videoViews.textContent = formatNumber(videoData.view_count) + ' 次观看';
    elements.videoLikes.textContent = formatNumber(videoData.like_count) + ' 个赞';

    // Update format selection
    updateFormatSelect(videoData.formats);

    // Show sections
    elements.videoInfo.classList.remove('hidden');
    elements.downloadControl.classList.remove('hidden');
    elements.downloadBtn.classList.remove('hidden');
    elements.downloadProgress.classList.add('hidden');
    elements.downloadComplete.classList.add('hidden');
}

// Update Format Select
function updateFormatSelect(formats) {
    // Calculate best quality size estimate
    let bestQualitySize = 0;
    let bestQualityInfo = '';

    if (formats && formats.length > 0) {
        // Find the best video format, prioritizing MP4
        const videoFormats = formats.filter(f => f.vcodec && f.vcodec !== 'none');
        const audioFormats = formats.filter(f => f.acodec && f.acodec !== 'none' && (!f.vcodec || f.vcodec === 'none'));

        if (videoFormats.length > 0) {
            // Separate MP4 and non-MP4 formats
            const mp4VideoFormats = videoFormats.filter(f => f.ext === 'mp4');
            const nonMp4VideoFormats = videoFormats.filter(f => f.ext !== 'mp4');

            // Choose the best format, prioritizing MP4
            const formatsToConsider = mp4VideoFormats.length > 0 ? mp4VideoFormats : nonMp4VideoFormats;

            const bestVideo = formatsToConsider.reduce((a, b) => {
                const aSize = a.filesize || 0;
                const bSize = b.filesize || 0;
                const aRes = parseInt(a.resolution.split('x')[1] || 0);
                const bRes = parseInt(b.resolution.split('x')[1] || 0);
                // Prefer higher resolution or larger size
                if (aRes !== bRes) return aRes > bRes ? a : b;
                return aSize > bSize ? a : b;
            });

            // Find the best audio format, prioritizing M4A
            let bestAudio = null;
            if (audioFormats.length > 0) {
                // Separate M4A and other audio formats
                const m4aAudio = audioFormats.filter(f => f.ext === 'm4a');
                const nonM4aAudio = audioFormats.filter(f => f.ext !== 'm4a');

                // Choose the best format, prioritizing M4A
                const audioToConsider = m4aAudio.length > 0 ? m4aAudio : nonM4aAudio;

                bestAudio = audioToConsider.reduce((a, b) => {
                    const aSize = a.filesize || 0;
                    const bSize = b.filesize || 0;
                    const aBitrate = a.abr || 0;
                    const bBitrate = b.abr || 0;
                    // Prefer higher bitrate or larger size
                    if (aBitrate !== bBitrate) return aBitrate > bBitrate ? a : b;
                    return aSize > bSize ? a : b;
                });
            }

            // Calculate total size
            if (bestVideo.filesize) {
                bestQualitySize += bestVideo.filesize;
            }
            if (bestAudio && bestAudio.filesize) {
                bestQualitySize += bestAudio.filesize;
            }

            // Build quality info
            bestQualityInfo = bestVideo.resolution;
            if (bestQualitySize > 0) {
                bestQualityInfo += ` (~${formatFileSize(bestQualitySize)})`;
            }
        }
    }

    // Update the best quality option with size estimate
    if (bestQualityInfo) {
        elements.formatSelect.innerHTML = `<option value="best">最佳质量 - ${bestQualityInfo}</option>`;
    } else {
        elements.formatSelect.innerHTML = '<option value="best">最佳质量 (自动)</option>';
    }

    if (formats && formats.length > 0) {
        // Re-filter formats
        const videoFormats = formats.filter(f => f.vcodec && f.vcodec !== 'none');
        const audioFormats = formats.filter(f => f.acodec && f.acodec !== 'none' && (!f.vcodec || f.vcodec === 'none'));

        if (videoFormats.length > 0) {
            const optgroup = document.createElement('optgroup');
            optgroup.label = '视频格式';

            // Separate MP4 and WebM formats, then sort each group by quality
            const mp4Formats = videoFormats.filter(f => f.ext === 'mp4');
            const webmFormats = videoFormats.filter(f => f.ext === 'webm');
            const otherFormats = videoFormats.filter(f => f.ext !== 'mp4' && f.ext !== 'webm');

            // Function to sort formats by quality (larger size or higher resolution first)
            const sortByQuality = (formats) => {
                return formats.sort((a, b) => {
                    const aSize = a.filesize || 0;
                    const bSize = b.filesize || 0;
                    // If both have sizes, sort by size
                    if (aSize && bSize) {
                        return bSize - aSize;
                    }
                    // If only one has size, prioritize it
                    if (aSize && !bSize) return -1;
                    if (!aSize && bSize) return 1;
                    // If neither has size, sort by resolution
                    const aRes = parseInt(a.resolution.split('x')[1] || 0);
                    const bRes = parseInt(b.resolution.split('x')[1] || 0);
                    return bRes - aRes;
                });
            };

            // Sort each format group by quality
            const sortedMp4 = sortByQuality([...mp4Formats]);
            const sortedWebm = sortByQuality([...webmFormats]);
            const sortedOthers = sortByQuality([...otherFormats]);

            // Combine in desired order: MP4 first, then WebM, then others
            const sortedVideoFormats = [...sortedMp4, ...sortedWebm, ...sortedOthers];

            // Keep track of current format type for grouping
            let currentFormatType = '';

            sortedVideoFormats.forEach((format, index) => {
                // Add format type separator in the description
                const formatType = format.ext.toUpperCase();
                let isNewGroup = formatType !== currentFormatType;
                currentFormatType = formatType;

                const option = document.createElement('option');
                option.value = format.format_id;

                // Build format description parts
                let parts = [];

                // Add resolution
                if (format.resolution && format.resolution !== 'N/AxN/A') {
                    parts.push(format.resolution);
                }

                // Add format note (like 720p, 1080p) if it adds meaningful info
                if (format.format_note &&
                    !format.format_note.includes('N/A') &&
                    !format.resolution.includes(format.format_note)) {
                    parts.push(format.format_note);
                }

                // Add format note (file extension with emphasis for MP4/WebM)
                if (format.ext === 'mp4' || format.ext === 'webm') {
                    parts.push(format.ext.toUpperCase());
                } else {
                    parts.push(format.ext);
                }

                // Build size/bitrate info
                let sizeInfo = '';
                if (format.filesize && format.filesize > 0) {
                    sizeInfo = formatFileSize(format.filesize);
                } else if (format.tbr && format.tbr > 0) {
                    // Total bitrate
                    sizeInfo = `~${format.tbr.toFixed(0)}kbps`;
                } else if (format.vbr && format.vbr > 0) {
                    // Video bitrate only
                    sizeInfo = `video: ${format.vbr.toFixed(0)}kbps`;
                } else if (format.abr && format.abr > 0) {
                    // Audio bitrate only
                    sizeInfo = `audio: ${format.abr.toFixed(0)}kbps`;
                }

                // Add FPS if notable
                if (format.fps && format.fps > 30 && format.fps !== 60) {
                    sizeInfo += sizeInfo ? `, ${format.fps}fps` : `${format.fps}fps`;
                }

                // Combine all parts
                let description = parts.join(' - ');
                if (sizeInfo) {
                    description += ` (${sizeInfo})`;
                }

                option.textContent = description;
                optgroup.appendChild(option);
            });

            elements.formatSelect.appendChild(optgroup);
        }

        if (audioFormats.length > 0) {
            const optgroup = document.createElement('optgroup');
            optgroup.label = '仅音频';

            // Separate M4A and other audio formats, then sort each group by quality
            const m4aFormats = audioFormats.filter(f => f.ext === 'm4a');
            const webmAudioFormats = audioFormats.filter(f => f.ext === 'webm');
            const otherAudioFormats = audioFormats.filter(f => f.ext !== 'm4a' && f.ext !== 'webm');

            // Function to sort audio formats by quality (larger size or higher bitrate first)
            const sortAudioByQuality = (formats) => {
                return formats.sort((a, b) => {
                    const aSize = a.filesize || 0;
                    const bSize = b.filesize || 0;
                    // If both have sizes, sort by size
                    if (aSize && bSize) {
                        return bSize - aSize;
                    }
                    // If only one has size, prioritize it
                    if (aSize && !bSize) return -1;
                    if (!aSize && bSize) return 1;
                    // If neither has size, sort by bitrate
                    return (b.abr || 0) - (a.abr || 0);
                });
            };

            // Sort each audio format group by quality
            const sortedM4a = sortAudioByQuality([...m4aFormats]);
            const sortedWebmAudio = sortAudioByQuality([...webmAudioFormats]);
            const sortedOtherAudio = sortAudioByQuality([...otherAudioFormats]);

            // Combine in desired order: M4A first, then WebM, then others
            const sortedAudioFormats = [...sortedM4a, ...sortedWebmAudio, ...sortedOtherAudio];

            sortedAudioFormats.forEach(format => {
                const option = document.createElement('option');
                option.value = format.format_id;

                // Build audio format description
                let parts = [];

                // Add format note or quality description
                if (format.format_note && !format.format_note.includes('N/A')) {
                    parts.push(format.format_note);
                } else if (format.quality) {
                    parts.push(`quality: ${format.quality}`);
                }

                // Add codec info if available
                if (format.acodec && format.acodec !== 'none') {
                    const codec = format.acodec.split('.')[0]; // Simplify codec name
                    parts.push(codec);
                }

                // Add extension (with emphasis for M4A/WebM)
                if (format.ext === 'm4a' || format.ext === 'webm') {
                    parts.push(format.ext.toUpperCase());
                } else {
                    parts.push(format.ext);
                }

                // Build size/bitrate info
                let sizeInfo = '';
                if (format.filesize && format.filesize > 0) {
                    sizeInfo = formatFileSize(format.filesize);
                } else if (format.abr && format.abr > 0) {
                    sizeInfo = `${format.abr.toFixed(0)}kbps`;
                } else if (format.tbr && format.tbr > 0) {
                    sizeInfo = `~${format.tbr.toFixed(0)}kbps`;
                }

                // Combine all parts
                let description = parts.join(' - ');
                if (sizeInfo) {
                    description += ` (${sizeInfo})`;
                }

                option.textContent = description;
                optgroup.appendChild(option);
            });

            elements.formatSelect.appendChild(optgroup);
        }
    }
}

// Start Download
async function startDownload() {
    const url = elements.videoUrl.value.trim();
    const formatId = elements.formatSelect.value;

    if (!url) {
        alert('请输入视频链接');
        return;
    }

    // Update UI
    elements.downloadBtn.classList.add('hidden');
    elements.downloadProgress.classList.remove('hidden');
    elements.progressStatus.textContent = '开始下载...';
    elements.progressPercent.textContent = '0%';
    elements.progressFill.style.width = '0%';
    // Initialize stats display
    elements.downloadSpeed.textContent = '--';
    elements.downloadSize.textContent = '--';
    elements.totalSize.textContent = '--';
    elements.downloadEta.textContent = '--';

    try {
        const response = await fetch(`${API_BASE_URL}/api/download`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                url,
                format_id: formatId === 'best' ? null : formatId
            })
        });

        if (!response.ok) {
            throw new Error('开始下载失败');
        }

        const data = await response.json();
        currentTaskId = data.task_id;

        // Start polling for progress
        startProgressPolling();
    } catch (error) {
        console.error('Error starting download:', error);
        alert('开始下载失败: ' + error.message);
        resetDownloadUI();
    }
}

// Progress Polling
function startProgressPolling() {
    if (progressInterval) {
        clearInterval(progressInterval);
    }

    progressInterval = setInterval(async () => {
        try {
            // Check current task progress if exists
            if (currentTaskId) {
                const response = await fetch(`${API_BASE_URL}/api/download-status/${currentTaskId}`);
                if (response.ok) {
                    const status = await response.json();
                    updateProgress(status);

                    if (status.status === 'completed' || status.status === 'error') {
                        clearInterval(progressInterval);
                        progressInterval = null;
                        return;
                    }
                }
            }

            // Also check for any downloading tasks in history
            await updateAllDownloadingTasks();

        } catch (error) {
            console.error('Error fetching progress:', error);
        }
    }, 1000);
}

// Update All Downloading Tasks in History
async function updateAllDownloadingTasks() {
    // Get all downloading tasks from history
    const downloadingItems = document.querySelectorAll('.history-item[data-id]');

    for (const item of downloadingItems) {
        const taskId = item.dataset.id;
        const historyProgress = item.querySelector('.history-progress');

        // Only update items that have progress bars (downloading status)
        if (!historyProgress || historyProgress.style.display === 'none') continue;

        try {
            const response = await fetch(`${API_BASE_URL}/api/download-status/${taskId}`);
            if (response.ok) {
                const status = await response.json();
                updateHistoryProgress(taskId, status);

                // If this task just completed, we'll refresh history to show final state
                if (status.status === 'completed' || status.status === 'error') {
                    setTimeout(() => loadHistory(), 1000);
                }
            }
        } catch (error) {
            console.error(`Error updating progress for task ${taskId}:`, error);
        }
    }
}

// Update Progress
function updateProgress(status) {
    const progress = Math.round(status.progress || 0);

    elements.progressPercent.textContent = `${progress}%`;
    elements.progressFill.style.width = `${progress}%`;

    // Update status text based on phase
    if (status.phase) {
        switch (status.phase) {
            case 'downloading_video':
                elements.progressStatus.textContent = '正在下载视频...';
                break;
            case 'downloading_audio':
                elements.progressStatus.textContent = '正在下载音频...';
                break;
            case 'merging':
                elements.progressStatus.textContent = '正在合并音视频...';
                break;
            case 'completed':
                elements.progressStatus.textContent = '下载完成!';
                break;
            default:
                elements.progressStatus.textContent = '正在下载...';
        }
    }

    switch (status.status) {
        case 'downloading':
            // Update download statistics
            if (status.speed) {
                elements.downloadSpeed.textContent = status.speed;
            } else {
                elements.downloadSpeed.textContent = '--';
            }

            if (status.downloaded_size) {
                elements.downloadSize.textContent = status.downloaded_size;
            } else {
                elements.downloadSize.textContent = '--';
            }

            if (status.total_size) {
                elements.totalSize.textContent = status.total_size;
            } else {
                elements.totalSize.textContent = '--';
            }

            if (status.eta) {
                // Format ETA to readable format
                const eta = status.eta;
                if (eta > 3600) {
                    const hours = Math.floor(eta / 3600);
                    const minutes = Math.floor((eta % 3600) / 60);
                    elements.downloadEta.textContent = `${hours}小时${minutes}分钟`;
                } else if (eta > 60) {
                    const minutes = Math.floor(eta / 60);
                    const seconds = eta % 60;
                    elements.downloadEta.textContent = `${minutes}分${seconds}秒`;
                } else {
                    elements.downloadEta.textContent = `${eta}秒`;
                }
            } else {
                elements.downloadEta.textContent = '--';
            }
            break;

        case 'processing':
            // During merge, clear speed and ETA but keep sizes
            elements.downloadSpeed.textContent = '--';
            elements.downloadEta.textContent = '--';
            if (status.downloaded_size) {
                elements.downloadSize.textContent = status.downloaded_size;
            }
            if (status.total_size) {
                elements.totalSize.textContent = status.total_size;
            }
            break;

        case 'completed':
            elements.progressStatus.textContent = '下载完成!';
            showDownloadComplete(status.filename);
            // Refresh history to show completed status
            setTimeout(() => loadHistory(), 500);
            break;

        case 'error':
            elements.progressStatus.textContent = '下载失败';
            alert('下载失败: ' + (status.message || '未知错误'));
            resetDownloadUI();
            // Refresh history to show error status
            setTimeout(() => loadHistory(), 500);
            break;
    }

    // Also update history if this task is in history
    updateHistoryProgress(currentTaskId, status);
}

// Update History Progress
function updateHistoryProgress(taskId, status) {
    if (!taskId) return;

    const historyItem = document.querySelector(`.history-item[data-id="${taskId}"]`);
    if (!historyItem) return;

    const historyProgress = historyItem.querySelector('.history-progress');
    if (!historyProgress) return;

    // Hide progress bar for completed or error status and update main status
    if (status.status === 'completed' || status.status === 'error') {
        historyProgress.style.display = 'none';

        // Update the main status element in history item
        const statusElement = historyItem.querySelector('.history-status');
        if (statusElement) {
            if (status.status === 'completed') {
                statusElement.textContent = '已完成';
                statusElement.className = 'history-status status-completed';
            } else {
                statusElement.textContent = '失败';
                statusElement.className = 'history-status status-error';
            }
        }
        return;
    }

    const progress = Math.round(status.progress || 0);

    // Update progress bar and percentage
    const progressPercent = historyProgress.querySelector('.progress-percent');
    const progressFill = historyProgress.querySelector('.progress-fill');
    const progressStatus = historyProgress.querySelector('.progress-status');

    if (progressPercent) progressPercent.textContent = `${progress}%`;
    if (progressFill) progressFill.style.width = `${progress}%`;

    // Update status text based on phase
    if (progressStatus && status.phase) {
        switch (status.phase) {
            case 'downloading_video':
                progressStatus.textContent = '下载视频中...';
                break;
            case 'downloading_audio':
                progressStatus.textContent = '下载音频中...';
                break;
            case 'merging':
                progressStatus.textContent = '合并中...';
                break;
            case 'completed':
                progressStatus.textContent = '完成!';
                break;
            default:
                progressStatus.textContent = '下载中...';
        }
    }

    // Update download statistics
    const downloadSpeed = historyProgress.querySelector('.download-speed');
    const downloadSize = historyProgress.querySelector('.download-size');
    const totalSize = historyProgress.querySelector('.total-size');
    const downloadEta = historyProgress.querySelector('.download-eta');

    if (downloadSpeed) {
        downloadSpeed.textContent = status.speed || '--';
    }

    if (downloadSize) {
        downloadSize.textContent = status.downloaded_size || '--';
    }

    if (totalSize) {
        totalSize.textContent = status.total_size || '--';
    }

    if (downloadEta && status.eta) {
        const eta = status.eta;
        if (eta > 3600) {
            const hours = Math.floor(eta / 3600);
            const minutes = Math.floor((eta % 3600) / 60);
            downloadEta.textContent = `${hours}时${minutes}分`;
        } else if (eta > 60) {
            const minutes = Math.floor(eta / 60);
            const seconds = eta % 60;
            downloadEta.textContent = `${minutes}分${seconds}秒`;
        } else {
            downloadEta.textContent = `${eta}秒`;
        }
    } else if (downloadEta) {
        downloadEta.textContent = '--';
    }
}

// Show Download Complete
function showDownloadComplete(filename) {
    elements.downloadProgress.classList.add('hidden');
    elements.downloadComplete.classList.remove('hidden');
    elements.downloadFilename.textContent = filename || '下载完成';
}

// Play Current Video
async function playCurrentVideo() {
    if (!currentTaskId) return;

    try {
        const videoUrl = `${API_BASE_URL}/api/download-file/${currentTaskId}`;
        const filename = elements.downloadFilename.textContent || 'video.mp4';

        // Create video modal
        const modal = document.createElement('div');
        modal.className = 'video-modal';
        modal.innerHTML = `
            <div class="video-modal-content">
                <div class="video-modal-header">
                    <h3>${filename}</h3>
                    <button class="video-modal-close">&times;</button>
                </div>
                <video controls autoplay style="width: 100%; max-height: 70vh;">
                    <source src="${videoUrl}" type="video/mp4">
                    您的浏览器不支持视频播放
                </video>
            </div>
        `;

        document.body.appendChild(modal);

        // Close modal events
        const closeBtn = modal.querySelector('.video-modal-close');
        closeBtn.addEventListener('click', () => {
            document.body.removeChild(modal);
        });

        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                document.body.removeChild(modal);
            }
        });

    } catch (error) {
        console.error('Error playing video:', error);
        alert('播放视频失败: ' + error.message);
    }
}

// Save File
async function saveFile() {
    if (!currentTaskId) return;

    try {
        const link = document.createElement('a');
        link.href = `${API_BASE_URL}/api/download-file/${currentTaskId}`;
        link.download = elements.downloadFilename.textContent || 'video.mp4';
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
    } catch (error) {
        console.error('Error saving file:', error);
        alert('保存文件失败: ' + error.message);
    }
}

// Reset Download
function resetDownload() {
    elements.videoUrl.value = '';
    hideVideoInfo();
    resetDownloadUI();
    currentTaskId = null;
}

// Hide Video Info
function hideVideoInfo() {
    elements.videoInfo.classList.add('hidden');
    elements.downloadControl.classList.add('hidden');
}

// Reset Download UI
function resetDownloadUI() {
    elements.downloadBtn.classList.remove('hidden');
    elements.downloadProgress.classList.add('hidden');
    elements.downloadComplete.classList.add('hidden');
    if (progressInterval) {
        clearInterval(progressInterval);
        progressInterval = null;
    }
}

// Load History
async function loadHistory() {
    try {
        const response = await fetch(`${API_BASE_URL}/api/history`);
        if (!response.ok) {
            throw new Error('加载历史记录失败');
        }

        const history = await response.json();
        displayHistory(history);
    } catch (error) {
        console.error('Error loading history:', error);
    }
}

// Display History
function displayHistory(history) {
    if (history.length === 0) {
        elements.historyList.classList.add('hidden');
        elements.noHistory.classList.remove('hidden');
        return;
    }

    elements.historyList.classList.remove('hidden');
    elements.noHistory.classList.add('hidden');

    elements.historyList.innerHTML = history.map(item => `
        <div class="history-item" data-id="${item.id}">
            <img src="${item.thumbnail ? `${API_BASE_URL}/api/proxy-thumbnail?url=${encodeURIComponent(item.thumbnail)}` : ''}" alt="${item.title}" class="history-thumbnail">
            <div class="history-details">
                <div class="history-title">${item.title}</div>
                <div class="history-meta">
                    ${item.uploader || '未知作者'} · ${formatDate(item.downloaded_at)}
                </div>
                <span class="history-status status-${item.status}">
                    ${getStatusText(item.status)}
                </span>
                ${item.file_size ? `<span class="history-meta"> · ${formatFileSize(item.file_size)}</span>` : ''}
                ${item.error_message ? `<div class="history-error">错误: ${item.error_message}</div>` : ''}

                ${item.status === 'downloading' ? `
                    <div class="history-progress">
                        <div class="progress-info">
                            <span class="progress-status">下载中...</span>
                            <span class="progress-percent">0%</span>
                        </div>
                        <div class="progress-bar">
                            <div class="progress-fill" style="width: 0%"></div>
                        </div>
                        <div class="download-stats">
                            <div class="stat-item">
                                <span class="stat-label">速度:</span>
                                <span class="download-speed stat-value">--</span>
                            </div>
                            <div class="stat-item">
                                <span class="stat-label">已下载:</span>
                                <span class="download-size stat-value">--</span>
                            </div>
                            <div class="stat-item">
                                <span class="stat-label">总大小:</span>
                                <span class="total-size stat-value">--</span>
                            </div>
                            <div class="stat-item">
                                <span class="stat-label">剩余时间:</span>
                                <span class="download-eta stat-value">--</span>
                            </div>
                        </div>
                    </div>
                ` : ''}
            </div>
            <div class="history-actions">
                ${item.status === 'completed' ? `
                    <button class="btn-icon" onclick="playVideo('${item.id}')" title="播放">
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <polygon points="5 3 19 12 5 21 5 3"></polygon>
                        </svg>
                    </button>
                    <button class="btn-icon" onclick="downloadVideo('${item.id}')" title="下载">
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                            <polyline points="7 10 12 15 17 10"></polyline>
                            <line x1="12" y1="15" x2="12" y2="3"></line>
                        </svg>
                    </button>
                ` : item.status === 'error' ? `
                    <button class="btn-icon btn-retry" onclick="retryDownload('${item.url}')" title="重试下载">
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M1 4v6h6"></path>
                            <path d="M23 20v-6h-6"></path>
                            <path d="M20.49 9A9 9 0 0 0 5.64 5.64L1 10m22 4l-4.64 4.36A9 9 0 0 1 3.51 15"></path>
                        </svg>
                    </button>
                ` : ''}
                <button class="btn-icon btn-delete" onclick="deleteHistoryItem('${item.id}')" title="删除">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <polyline points="3 6 5 6 21 6"></polyline>
                        <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                    </svg>
                </button>
            </div>
        </div>
    `).join('');
}

// WebSocket for real-time updates
function initWebSocket() {
    // Optional: Implement WebSocket for real-time progress updates
    // This is more advanced and can be added later if needed
}

// History Actions
async function playVideo(taskId) {
    const modal = document.createElement('div');
    modal.className = 'video-modal';
    modal.innerHTML = `
        <div class="video-modal-content">
            <span class="video-modal-close" onclick="closeVideoModal()">&times;</span>
            <video controls autoplay>
                <source src="${API_BASE_URL}/api/stream/${taskId}" type="video/mp4">
                您的浏览器不支持视频播放。
            </video>
        </div>
    `;
    document.body.appendChild(modal);
}

function closeVideoModal() {
    const modal = document.querySelector('.video-modal');
    if (modal) {
        modal.remove();
    }
}

async function downloadVideo(taskId) {
    try {
        const link = document.createElement('a');
        link.href = `${API_BASE_URL}/api/download-file/${taskId}`;
        link.download = '';
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
    } catch (error) {
        console.error('Error downloading video:', error);
        alert('下载失败: ' + error.message);
    }
}

async function deleteHistoryItem(taskId) {
    if (!confirm('确定要删除这条记录吗？同时会删除已下载的文件。')) {
        return;
    }

    try {
        const response = await fetch(`${API_BASE_URL}/api/history/${taskId}`, {
            method: 'DELETE'
        });

        if (response.ok) {
            // 从页面移除该项
            const item = document.querySelector(`.history-item[data-id="${taskId}"]`);
            if (item) {
                item.remove();
            }

            // 重新加载历史
            loadHistory();
        } else {
            alert('删除失败');
        }
    } catch (error) {
        console.error('Error deleting history item:', error);
        alert('删除失败: ' + error.message);
    }
}

// Retry failed download
async function retryDownload(url) {
    if (!url) {
        alert('无法获取下载链接');
        return;
    }

    // Switch to download tab
    switchTab('download');

    // Set the URL in the input field
    elements.videoUrl.value = url;

    // Fetch video info and prepare for download
    await fetchVideoInfo();
}

// Close video modal when clicking outside
document.addEventListener('click', function(event) {
    if (event.target.classList.contains('video-modal')) {
        closeVideoModal();
    }
});

// Utility Functions
function formatDuration(seconds) {
    if (!seconds) return '未知';
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;

    if (hours > 0) {
        return `${hours}:${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
    }
    return `${minutes}:${String(secs).padStart(2, '0')}`;
}

function formatNumber(num) {
    if (!num) return '0';
    if (num >= 1000000) {
        return (num / 1000000).toFixed(1) + 'M';
    }
    if (num >= 1000) {
        return (num / 1000).toFixed(1) + 'K';
    }
    return num.toString();
}

function formatFileSize(bytes) {
    if (!bytes) return '0 B';
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(1024));
    return Math.round(bytes / Math.pow(1024, i) * 100) / 100 + ' ' + sizes[i];
}

function formatDate(dateString) {
    if (!dateString) return '';
    const date = new Date(dateString);
    return date.toLocaleDateString('zh-CN') + ' ' + date.toLocaleTimeString('zh-CN');
}

function getStatusText(status) {
    const statusMap = {
        'completed': '已完成',
        'downloading': '下载中',
        'processing': '处理中',
        'error': '失败'
    };
    return statusMap[status] || status;
}

// Update cookies status display
async function updateCookiesStatus() {
    try {
        const cookiesResponse = await fetch(`${API_BASE_URL}/api/config/cookies`);
        if (cookiesResponse.ok) {
            const cookiesData = await cookiesResponse.json();
            if (cookiesData.content) {
                // 分析cookies内容并显示状态
                const lines = cookiesData.content.split('\n').filter(line =>
                    line.trim() && !line.startsWith('#')
                );
                const cookiesCount = lines.length;

                if (cookiesCount > 0) {
                    elements.cookiesStatus.innerHTML = `
                        <span class="status-indicator status-success">✅ 已加载 ${cookiesCount} 个cookies</span>
                    `;
                } else {
                    elements.cookiesStatus.innerHTML = `
                        <span class="status-indicator status-warning">⚠️ cookies文件为空或无效</span>
                    `;
                }

                // 同时更新输入框内容
                elements.cookiesInput.value = cookiesData.content;
            } else {
                elements.cookiesStatus.innerHTML = `
                    <span class="status-indicator status-error">❌ 无cookies配置</span>
                `;
                elements.cookiesInput.value = '';
            }
        } else {
            elements.cookiesStatus.innerHTML = `
                <span class="status-indicator status-error">❌ 无cookies配置</span>
            `;
        }
    } catch (error) {
        console.error('Error updating cookies status:', error);
        elements.cookiesStatus.innerHTML = `
            <span class="status-indicator status-error">❌ 获取cookies状态失败</span>
        `;
    }
}

// Settings Functions
async function loadSettings() {
    try {
        // Load general config
        const response = await fetch(`${API_BASE_URL}/api/config`);
        if (!response.ok) return;

        const config = await response.json();

        // Load proxy
        if (config.proxy) {
            elements.proxyInput.value = config.proxy;
        }

        // Load user agent
        if (config.user_agent) {
            elements.userAgentInput.value = config.user_agent;
        }

        // Load extra params
        if (config.extra_params) {
            elements.nocheckcertificate.checked = config.extra_params.nocheckcertificate !== false;
            elements.geoBypass.checked = config.extra_params.geo_bypass !== false;
            elements.skipUnavailableFragments.checked = config.extra_params.skip_unavailable_fragments !== false;

            if (config.extra_params.sleep_interval !== undefined) {
                elements.sleepInterval.value = config.extra_params.sleep_interval;
            }
            if (config.extra_params.retries !== undefined) {
                elements.retries.value = config.extra_params.retries;
            }
            if (config.extra_params.fragment_retries !== undefined) {
                elements.fragmentRetries.value = config.extra_params.fragment_retries;
            }
        }

        // Load custom parameters
        if (config.custom_params && Array.isArray(config.custom_params)) {
            elements.customParams.value = config.custom_params.join('\n');
        }

        // Load cookies and update status
        await updateCookiesStatus();

        if (config.wecom) {
            elements.wecomCorpId.value = config.wecom.corp_id || '';
            elements.wecomAgentId.value = config.wecom.agent_id ?? '';
            elements.wecomAppSecret.value = config.wecom.app_secret || '';
            elements.wecomToken.value = config.wecom.token || '';
            elements.wecomEncodingKey.value = config.wecom.encoding_aes_key || '';
            elements.wecomPublicUrl.value = config.wecom.public_base_url || '';
            elements.wecomDefaultFormat.value = config.wecom.default_format_id || 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best';
            elements.wecomProxyDomain.value = config.wecom.proxy_domain || '';
        }
    } catch (error) {
        console.error('Error loading settings:', error);
    }
}

async function saveCookies() {
    const cookiesContent = elements.cookiesInput.value.trim();
    if (!cookiesContent) {
        alert('请输入cookies内容');
        return;
    }

    try {
        const response = await fetch(`${API_BASE_URL}/api/config/cookies`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ content: cookiesContent })
        });

        if (response.ok) {
            alert('Cookies保存成功！');
            // 立即更新cookie状态显示
            await updateCookiesStatus();
        } else {
            alert('Cookies保存失败');
        }
    } catch (error) {
        console.error('Error saving cookies:', error);
        alert('保存Cookies时出错');
    }
}

async function saveSettings() {
    // Parse custom parameters
    const customParamsText = elements.customParams.value.trim();
    const customParams = customParamsText ? customParamsText.split('\n').filter(line => line.trim()) : [];

    const corpId = elements.wecomCorpId.value.trim();
    const agentIdRaw = elements.wecomAgentId.value.trim();
    const appSecret = elements.wecomAppSecret.value.trim();
    const token = elements.wecomToken.value.trim();
    const encodingKey = elements.wecomEncodingKey.value.trim();
    const publicUrl = elements.wecomPublicUrl.value.trim();
    const defaultFormat = elements.wecomDefaultFormat.value.trim() || 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best';
    const proxyDomain = elements.wecomProxyDomain.value.trim();

    if (encodingKey && encodingKey.length !== 43) {
        alert('EncodingAESKey 必须为43位');
        return;
    }

    let agentId = null;
    if (agentIdRaw) {
        agentId = Number(agentIdRaw);
        if (Number.isNaN(agentId)) {
            alert('AgentID 必须是数字');
            return;
        }
    }

    const config = {
        proxy: elements.proxyInput.value.trim() || null,
        user_agent: elements.userAgentInput.value.trim(),
        extra_params: {
            nocheckcertificate: elements.nocheckcertificate.checked,
            geo_bypass: elements.geoBypass.checked,
            skip_unavailable_fragments: elements.skipUnavailableFragments.checked,
            sleep_interval: parseInt(elements.sleepInterval.value),
            max_sleep_interval: parseInt(elements.sleepInterval.value) + 2,
            retries: parseInt(elements.retries.value),
            fragment_retries: parseInt(elements.fragmentRetries.value)
        },
        custom_params: customParams,
        wecom: {
            corp_id: corpId,
            agent_id: agentId,
            app_secret: appSecret,
            token,
            encoding_aes_key: encodingKey,
            public_base_url: publicUrl,
            default_format_id: defaultFormat,
            proxy_domain: proxyDomain
        }
    };

    try {
        const response = await fetch(`${API_BASE_URL}/api/config`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(config)
        });

        if (response.ok) {
            alert('设置保存成功！');
        } else {
            alert('设置保存失败');
        }
    } catch (error) {
        console.error('Error saving settings:', error);
        alert('保存设置时出错');
    }
}

async function resetSettings() {
    if (!confirm('确定要重置所有设置为默认值吗？')) {
        return;
    }

    // Reset UI to defaults
    elements.proxyInput.value = '';
    elements.userAgentInput.value = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36';
    elements.nocheckcertificate.checked = true;
    elements.geoBypass.checked = true;
    elements.skipUnavailableFragments.checked = true;
    elements.sleepInterval.value = 1;
    elements.retries.value = 3;
    elements.fragmentRetries.value = 3;
    elements.cookiesInput.value = '';
    elements.customParams.value = '';
    elements.wecomCorpId.value = '';
    elements.wecomAgentId.value = '';
    elements.wecomAppSecret.value = '';
    elements.wecomToken.value = '';
    elements.wecomEncodingKey.value = '';
    elements.wecomPublicUrl.value = '';
    elements.wecomDefaultFormat.value = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best';

    // Save default settings
    await saveSettings();
}

// Load version information
async function loadVersionInfo() {
    try {
        const response = await fetch(`${API_BASE_URL}/api/version`);
        if (response.ok) {
            const versionData = await response.json();
            const versionDisplay = document.getElementById('version-display');
            if (versionDisplay) {
                versionDisplay.textContent = `v${versionData.app_version} | yt-dlp ${versionData.yt_dlp_version} | Python ${versionData.python_version}`;
            }
        } else {
            console.warn('Failed to load version info');
        }
    } catch (error) {
        console.error('Error loading version info:', error);
        const versionDisplay = document.getElementById('version-display');
        if (versionDisplay) {
            versionDisplay.textContent = 'Version info unavailable';
        }
    }
}
