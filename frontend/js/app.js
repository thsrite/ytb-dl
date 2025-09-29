// API Base URL - dynamically determined based on current page location
const API_BASE_URL = window.location.origin || `${window.location.protocol}//${window.location.host}`;

// Log the API base URL for debugging
console.log('API Base URL:', API_BASE_URL);

// Global variables
let currentTaskId = null;
let progressInterval = null;
let ws = null;

// Store active download statuses for history display
window.activeDownloadStatuses = {};

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
    redownloadBtn: document.getElementById('redownload-btn'),
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

    // FFmpeg settings
    ffmpegTranscodeEnabled: document.getElementById('ffmpeg-transcode-enabled'),
    ffmpegAv1Only: document.getElementById('ffmpeg-av1-only'),
    ffmpegCommand: document.getElementById('ffmpeg-command'),
    ffmpegPresetSelect: document.getElementById('ffmpeg-preset-select'),
    ffmpegOutputFormat: document.getElementById('ffmpeg-output-format'),

    // WeCom settings
    wecomCorpId: document.getElementById('wecom-corp-id'),
    wecomAgentId: document.getElementById('wecom-agent-id'),
    wecomAppSecret: document.getElementById('wecom-app-secret'),
    wecomToken: document.getElementById('wecom-token'),
    wecomEncodingKey: document.getElementById('wecom-encoding-key'),
    wecomPublicUrl: document.getElementById('wecom-public-url'),
    wecomDefaultFormat: document.getElementById('wecom-default-format'),
    wecomProxyDomain: document.getElementById('wecom-proxy-domain'),
    wecomNotifyAdmin: document.getElementById('wecom-notify-admin'),
    wecomAdminUsers: document.getElementById('wecom-admin-users')
};

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    initTabs();
    initEventListeners();
    loadHistory();
    loadSettings();
    initWebSocket();
    loadVersionInfo();

    // Check for yt-dlp updates on page load
    setTimeout(() => {
        checkYtDlpUpdate();
    }, 2000);

    // Check browser cookie status on page load
    checkBrowserCookieStatus();

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
    elements.redownloadBtn.addEventListener('click', redownloadVideo);
    elements.newDownloadBtn.addEventListener('click', resetDownload);

    // Settings event listeners
    elements.saveCookiesBtn.addEventListener('click', saveCookies);
    elements.saveSettingsBtn.addEventListener('click', saveSettings);
    elements.resetSettingsBtn.addEventListener('click', resetSettings);

    // FFmpeg preset select
    if (elements.ffmpegPresetSelect) {
        elements.ffmpegPresetSelect.addEventListener('change', handleFfmpegPresetChange);
    }

    // Admin notification test button
    const testAdminNotifyBtn = document.getElementById('test-admin-notify-btn');
    if (testAdminNotifyBtn) {
        testAdminNotifyBtn.addEventListener('click', testAdminNotification);
    }

    // yt-dlp update event listeners
    const checkUpdateBtn = document.getElementById('check-ytdlp-update-btn');
    const updateBtn = document.getElementById('update-ytdlp-btn');
    if (checkUpdateBtn) {
        checkUpdateBtn.addEventListener('click', checkYtDlpUpdate);
    }
    if (updateBtn) {
        updateBtn.addEventListener('click', updateYtDlp);
    }

    // Browser cookie event listeners
    const importBrowserCookiesBtn = document.getElementById('import-browser-cookies-btn');
    const browserCookiesEnabled = document.getElementById('browser-cookies-enabled');
    const browserCookiesAutoRefresh = document.getElementById('browser-cookies-auto-refresh');

    if (importBrowserCookiesBtn) {
        importBrowserCookiesBtn.addEventListener('click', importBrowserCookies);
    }
    if (browserCookiesEnabled) {
        browserCookiesEnabled.addEventListener('change', updateBrowserCookieSettings);
    }
    if (browserCookiesAutoRefresh) {
        browserCookiesAutoRefresh.addEventListener('change', updateBrowserCookieSettings);
    }

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
        const statusElement = item.querySelector('.history-status');

        // Check if this item is actively downloading/processing/transcoding
        if (!statusElement) continue;
        const statusText = statusElement.textContent;
        const isActive = statusText === '下载中' || statusText === '处理中' || statusText === '正在转码';

        if (!isActive) continue;

        try {
            const response = await fetch(`${API_BASE_URL}/api/download-status/${taskId}`);
            if (response.ok) {
                const status = await response.json();

                // Store status for history rendering
                if (status.status === 'downloading' || status.status === 'processing' || status.status === 'transcoding') {
                    window.activeDownloadStatuses[taskId] = status;
                } else {
                    // Remove from active statuses when completed or error
                    delete window.activeDownloadStatuses[taskId];
                }

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
            case 'transcoding':
                elements.progressStatus.textContent = '正在转码视频...';
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
        case 'transcoding':
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

    if (status.status === 'downloading' || status.status === 'processing' || status.status === 'transcoding') {
        historyProgress.style.display = 'block';

        // Update main status text for transcoding
        const statusElement = historyItem.querySelector('.history-status');
        if (statusElement && status.status === 'transcoding') {
            statusElement.textContent = '正在转码';
            statusElement.className = 'history-status status-transcoding';
        }
    }

    const progress = Math.round(status.progress || 0);

    // Update progress bar and percentage
    const progressPercent = historyProgress.querySelector('.progress-percent');
    const progressFill = historyProgress.querySelector('.progress-fill');
    const progressStatus = historyProgress.querySelector('.progress-status');

    if (progressPercent) progressPercent.textContent = `${progress}%`;
    if (progressFill) progressFill.style.width = `${progress}%`;

    // Update status text based on phase
    if (progressStatus) {
        if (status.status === 'transcoding' || status.phase === 'transcoding') {
            progressStatus.textContent = '正在转码视频...';
        } else if (status.phase) {
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

// Redownload Video
async function redownloadVideo() {
    if (!currentTaskId) return;

    const confirmed = confirm('确定要重新下载吗？这将删除已下载的文件。');
    if (!confirmed) return;

    try {
        const response = await fetch(`${API_BASE_URL}/api/redownload/${currentTaskId}`, {
            method: 'POST'
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const result = await response.json();

        // Update current task ID to the new one
        const newTaskId = result.task_id;
        currentTaskId = newTaskId;

        // Reset UI to show download progress
        resetDownloadUI();
        elements.downloadBtn.classList.add('hidden');
        elements.downloadProgress.classList.remove('hidden');
        elements.progressStatus.textContent = '正在重新下载...';
        elements.progressPercent.textContent = '0%';
        elements.progressFill.style.width = '0%';

        // Start monitoring progress with new task ID
        startProgressMonitoring();

    } catch (error) {
        console.error('Error redownloading:', error);
        alert('重新下载失败: ' + error.message);
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
        document.getElementById('history-actions-bar').classList.add('hidden');
        return;
    }

    elements.historyList.classList.remove('hidden');
    elements.noHistory.classList.add('hidden');
    document.getElementById('history-actions-bar').classList.remove('hidden');

    const isMobile = window.innerWidth <= 768;

    const renderProgressSection = (item) => {
        const isActive = item && (item.status === 'downloading' || item.status === 'processing' || item.status === 'transcoding');

        // Try to get real-time progress from active downloads
        let progressData = null;
        if (isActive && window.activeDownloadStatuses && window.activeDownloadStatuses[item.id]) {
            progressData = window.activeDownloadStatuses[item.id];
        }

        const progressValue = Math.round(progressData?.progress?.percent || item?.progress || 0);
        const phase = progressData?.progress?.phase || item?.phase;

        const phaseMap = {
            downloading_video: '下载视频中...',
            downloading_audio: '下载音频中...',
            merging: '合并中...',
            transcoding: '正在转码视频...'
        };

        const progressLabel = phase ? (phaseMap[phase] || '下载中...')
            : item?.status === 'processing'
                ? '处理中...'
                : item?.status === 'transcoding'
                    ? '正在转码视频...'
                    : '下载中...';

        const etaText = progressData?.progress?.eta ? formatEtaValue(progressData.progress.eta) : '--';
        const speed = progressData?.progress?.speed || item?.speed || '--';

        return `
            <div class="history-progress" style="display: ${isActive ? 'block' : 'none'};">
                <div class="progress-info">
                    <span class="progress-status">${progressLabel}</span>
                    <span class="progress-percent">${progressValue}%</span>
                </div>
                <div class="progress-bar">
                    <div class="progress-fill" style="width: ${progressValue}%"></div>
                </div>
                <div class="download-stats">
                    <div class="stat-item">
                        <span class="stat-label">速度</span>
                        <span class="stat-value download-speed">${speed}</span>
                    </div>
                    <div class="stat-item">
                        <span class="stat-label">已下载</span>
                        <span class="stat-value download-size">${item?.downloaded_size || '--'}</span>
                    </div>
                    <div class="stat-item">
                        <span class="stat-label">总大小</span>
                        <span class="stat-value total-size">${item?.total_size || '--'}</span>
                    </div>
                    <div class="stat-item">
                        <span class="stat-label">剩余时间</span>
                        <span class="stat-value download-eta">${etaText}</span>
                    </div>
                </div>
            </div>
        `;
    };

    elements.historyList.innerHTML = history.map(item => {
        if (isMobile) {
            // Mobile layout with inline buttons
            return `
                <div class="history-item" data-id="${item.id}">
                    <div class="history-thumbnail-wrapper">
                        <input type="checkbox" class="history-checkbox" data-item-id="${item.id}">
                        <img src="${item.thumbnail ? `${API_BASE_URL}/api/proxy-thumbnail?url=${encodeURIComponent(item.thumbnail)}` : ''}" alt="${item.title}" class="history-thumbnail">
                    </div>
                    <div class="history-details">
                        <div class="history-title-row">
                            <div class="history-title">
                                <span class="history-status status-${item.status}">
                                    ${getStatusText(item.status)}
                                </span>
                                ${item.title}
                            </div>
                        </div>
                        <div class="history-meta">
                            ${item.uploader || '未知作者'} · ${item.file_size && item.status === 'completed' ? `${formatFileSize(item.file_size)} · ` : ''}${formatDate(item.downloaded_at)}
                        </div>
                        ${renderProgressSection(item)}
                        ${item.error_message ? `<div class="history-error-message">${item.error_message}</div>` : ''}
                    </div>
                    <div class="history-actions-mobile">
                        ${item.status === 'completed' ? `
                            <button class="btn-mobile btn-play" onclick="playVideo('${item.id}')" title="播放">
                                <svg viewBox="0 0 24 24" fill="currentColor">
                                    <path d="M8 5v14l11-7z"/>
                                </svg>
                            </button>
                            <button class="btn-mobile btn-download" onclick="downloadVideo('${item.id}')" title="下载">
                                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                                    <polyline points="7 10 12 15 17 10"/>
                                    <line x1="12" y1="15" x2="12" y2="3"/>
                                </svg>
                            </button>
                        ` : item.status === 'error' ? `
                            <button class="btn-mobile btn-retry" onclick="retryDownload('${item.url}')" title="重试">
                                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                                    <path d="M1 4v6h6"/>
                                    <path d="M23 20v-6h-6"/>
                                    <path d="M20.49 9A9 9 0 0 0 5.64 5.64L1 10m22 4l-4.64 4.36A9 9 0 0 1 3.51 15"/>
                                </svg>
                            </button>
                        ` : ''}
                        <button class="btn-mobile btn-delete" onclick="deleteHistoryItem('${item.id}')" title="删除">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                                <polyline points="3 6 5 6 21 6"/>
                                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                            </svg>
                        </button>
                    </div>
                </div>
            `;
        } else {
            // Desktop layout with separate actions section
            return `
                <div class="history-item" data-id="${item.id}">
                    <div class="history-thumbnail-wrapper">
                        <input type="checkbox" class="history-checkbox" data-item-id="${item.id}">
                        <img src="${item.thumbnail ? `${API_BASE_URL}/api/proxy-thumbnail?url=${encodeURIComponent(item.thumbnail)}` : ''}" alt="${item.title}" class="history-thumbnail">
                    </div>
                    <div class="history-details">
                        <div class="history-title">
                            <span class="history-status status-${item.status}">
                                ${getStatusText(item.status)}
                            </span>
                            ${item.title}
                        </div>
                        <div class="history-meta">
                            ${item.uploader || '未知作者'} · ${item.file_size && item.status === 'completed' ? `${formatFileSize(item.file_size)} · ` : ''}${formatDate(item.downloaded_at)}
                        </div>
                        ${renderProgressSection(item)}
                        ${item.error_message ? `<div class="history-error">${item.error_message}</div>` : ''}
                    </div>
                    <div class="history-actions">
                        ${item.status === 'completed' ? `
                            <button class="btn-icon" onclick="playVideo('${item.id}')" title="播放">
                                <svg viewBox="0 0 24 24" fill="currentColor">
                                    <path d="M8 5v14l11-7z"/>
                                </svg>
                            </button>
                            <button class="btn-icon" onclick="downloadVideo('${item.id}')" title="下载">
                                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                                    <polyline points="7 10 12 15 17 10"/>
                                    <line x1="12" y1="15" x2="12" y2="3"/>
                                </svg>
                            </button>
                        ` : item.status === 'error' ? `
                            <button class="btn-icon btn-retry" onclick="retryDownload('${item.url}')" title="重试">
                                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <path d="M1 4v6h6"/>
                                    <path d="M23 20v-6h-6"/>
                                    <path d="M20.49 9A9 9 0 0 0 5.64 5.64L1 10m22 4l-4.64 4.36A9 9 0 0 1 3.51 15"/>
                                </svg>
                            </button>
                        ` : ''}
                        <button class="btn-icon btn-delete" onclick="deleteHistoryItem('${item.id}')" title="删除">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <polyline points="3 6 5 6 21 6"/>
                                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                            </svg>
                        </button>
                    </div>
                </div>
            `;
        }
    }).join('');
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
        'transcoding': '正在转码',
        'error': '失败'
    };
    return statusMap[status] || status;
}

function formatEtaValue(eta) {
    if (eta == null) return '--';
    if (typeof eta !== 'number') return String(eta);
    const seconds = Math.max(0, Math.floor(eta));
    if (seconds >= 3600) {
        const hours = Math.floor(seconds / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        return `${hours}小时${minutes}分钟`;
    }
    if (seconds >= 60) {
        const minutes = Math.floor(seconds / 60);
        const secs = seconds % 60;
        return `${minutes}分${secs}秒`;
    }
    return `${seconds}秒`;
}

// Update cookies status display
async function updateCookiesStatus() {
    try {
        const cookiesResponse = await fetch(`${API_BASE_URL}/api/config/cookies`);
        if (cookiesResponse.ok) {
            const cookiesData = await cookiesResponse.json();
            const cookieCountText = document.getElementById('cookie-count-text');

            if (cookiesData.content) {
                // 分析cookies内容并显示状态
                const lines = cookiesData.content.split('\n').filter(line =>
                    line.trim() && !line.startsWith('#')
                );
                const cookiesCount = lines.length;

                // 更新新位置的Cookie状态显示
                if (cookieCountText) {
                    if (cookiesCount > 0) {
                        cookieCountText.textContent = `已加载 ${cookiesCount} 个cookies`;
                        cookieCountText.style.color = '#10b981';
                    } else {
                        cookieCountText.textContent = 'cookies文件为空或无效';
                        cookieCountText.style.color = '#fbbf24';
                    }
                }

                // 保持原有的状态栏显示（如果存在）
                if (elements.cookiesStatus) {
                    if (cookiesCount > 0) {
                        elements.cookiesStatus.innerHTML = `
                            <span class="status-indicator status-success">✅ 已加载 ${cookiesCount} 个cookies</span>
                        `;
                    } else {
                        elements.cookiesStatus.innerHTML = `
                            <span class="status-indicator status-warning">⚠️ cookies文件为空或无效</span>
                        `;
                    }
                }

                // 同时更新输入框内容
                elements.cookiesInput.value = cookiesData.content;
            } else {
                // 更新新位置的Cookie状态显示
                const cookieCountText = document.getElementById('cookie-count-text');
                if (cookieCountText) {
                    cookieCountText.textContent = '未配置cookies';
                    cookieCountText.style.color = '#ef4444';
                }

                if (elements.cookiesStatus) {
                    elements.cookiesStatus.innerHTML = `
                        <span class="status-indicator status-error">❌ 无cookies配置</span>
                    `;
                }
                elements.cookiesInput.value = '';
            }
        } else {
            // 更新新位置的Cookie状态显示
            const cookieCountText = document.getElementById('cookie-count-text');
            if (cookieCountText) {
                cookieCountText.textContent = '未配置cookies';
                cookieCountText.style.color = '#ef4444';
            }

            if (elements.cookiesStatus) {
                elements.cookiesStatus.innerHTML = `
                    <span class="status-indicator status-error">❌ 无cookies配置</span>
                `;
            }
        }
    } catch (error) {
        console.error('Error updating cookies status:', error);
        // 更新新位置的Cookie状态显示
        const cookieCountText = document.getElementById('cookie-count-text');
        if (cookieCountText) {
            cookieCountText.textContent = '获取cookie状态失败';
            cookieCountText.style.color = '#ef4444';
        }

        if (elements.cookiesStatus) {
            elements.cookiesStatus.innerHTML = `
                <span class="status-indicator status-error">❌ 获取cookies状态失败</span>
            `;
        }
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

        // Load FFmpeg settings
        if (config.ffmpeg) {
            if (elements.ffmpegTranscodeEnabled) {
                elements.ffmpegTranscodeEnabled.checked = config.ffmpeg.enabled || false;
            }
            if (elements.ffmpegAv1Only) {
                elements.ffmpegAv1Only.checked = config.ffmpeg.av1_only !== false;
            }
            if (elements.ffmpegPresetSelect) {
                elements.ffmpegPresetSelect.value = config.ffmpeg.hardware_preset || 'custom';
            }
            if (elements.ffmpegCommand) {
                elements.ffmpegCommand.value = config.ffmpeg.command || '-c:v libx264 -preset medium -crf 23 -c:a aac -b:a 192k';
            }
            if (elements.ffmpegOutputFormat) {
                elements.ffmpegOutputFormat.value = config.ffmpeg.output_format || 'mp4';
            }
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
            elements.wecomNotifyAdmin.checked = config.wecom.notify_admin || false;
            elements.wecomAdminUsers.value = (config.wecom.admin_users || []).join(',');
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

// Handle FFmpeg preset change
function handleFfmpegPresetChange() {
    const preset = elements.ffmpegPresetSelect.value;
    const presets = {
        'x264_high': '-c:v libx264 -preset slow -crf 18 -c:a aac -b:a 256k',
        'x264_medium': '-c:v libx264 -preset medium -crf 23 -c:a aac -b:a 192k',
        'x264_fast': '-c:v libx264 -preset fast -crf 28 -c:a aac -b:a 128k',
        'qsv_high': '-c:v h264_qsv -preset veryslow -global_quality 18 -look_ahead 1 -c:a aac -b:a 256k',
        'qsv_medium': '-c:v h264_qsv -preset medium -global_quality 23 -c:a aac -b:a 192k',
        'videotoolbox': '-c:v h264_videotoolbox -b:v 10M -c:a aac -b:a 256k',
        'nvenc_high': '-c:v h264_nvenc -preset p7 -rc vbr -cq 18 -b:v 0 -c:a aac -b:a 256k',
        'nvenc_medium': '-c:v h264_nvenc -preset p4 -rc vbr -cq 23 -b:v 0 -c:a aac -b:a 192k',
        'vaapi': '-vaapi_device /dev/dri/renderD128 -vf format=nv12,hwupload -c:v h264_vaapi -b:v 10M -c:a aac -b:a 192k'
    };

    if (preset !== 'custom' && presets[preset]) {
        elements.ffmpegCommand.value = presets[preset];
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
    const notifyAdmin = elements.wecomNotifyAdmin.checked;
    const adminUsersRaw = elements.wecomAdminUsers.value.trim();
    const adminUsers = adminUsersRaw ? adminUsersRaw.split(',').map(u => u.trim()).filter(u => u) : [];

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

    // Debug FFmpeg elements
    console.log('FFmpeg elements:', {
        enabled: elements.ffmpegTranscodeEnabled,
        av1Only: elements.ffmpegAv1Only,
        command: elements.ffmpegCommand,
        outputFormat: elements.ffmpegOutputFormat
    });

    const ffmpegConfig = {
        enabled: elements.ffmpegTranscodeEnabled ? elements.ffmpegTranscodeEnabled.checked : false,
        av1_only: elements.ffmpegAv1Only ? elements.ffmpegAv1Only.checked : true,
        hardware_preset: elements.ffmpegPresetSelect ? elements.ffmpegPresetSelect.value : 'custom',
        command: elements.ffmpegCommand ? elements.ffmpegCommand.value.trim() : '-c:v libx264 -preset medium -crf 23 -c:a aac -b:a 192k',
        output_format: elements.ffmpegOutputFormat ? elements.ffmpegOutputFormat.value : 'mp4'
    };

    console.log('FFmpeg config to save:', ffmpegConfig);

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
        ffmpeg: ffmpegConfig,
        wecom: {
            corp_id: corpId,
            agent_id: agentId,
            app_secret: appSecret,
            token,
            encoding_aes_key: encodingKey,
            public_base_url: publicUrl,
            default_format_id: defaultFormat,
            proxy_domain: proxyDomain,
            notify_admin: notifyAdmin,
            admin_users: adminUsers
        }
    };

    console.log('Full config to send:', config);
    console.log('Config stringified:', JSON.stringify(config, null, 2));

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
            // Also update yt-dlp version in settings
            const ytdlpCurrentVersion = document.getElementById('ytdlp-current-version');
            if (ytdlpCurrentVersion) {
                ytdlpCurrentVersion.textContent = versionData.yt_dlp_version;
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

// yt-dlp Update Management
async function checkYtDlpUpdate() {
    const checkBtn = document.getElementById('check-ytdlp-update-btn');
    const updateBtn = document.getElementById('update-ytdlp-btn');
    const currentVersionEl = document.getElementById('ytdlp-current-version');
    const latestVersionEl = document.getElementById('ytdlp-latest-version');
    const updateStatus = document.getElementById('ytdlp-update-status');
    const updateResult = document.getElementById('ytdlp-update-result');

    // Hide previous results
    updateResult.classList.add('hidden');
    updateStatus.classList.add('hidden');
    updateBtn.classList.add('hidden');

    // Disable check button
    checkBtn.disabled = true;
    checkBtn.textContent = '🔄 检查中...';

    try {
        const response = await fetch(`${API_BASE_URL}/api/yt-dlp/check-update`);
        if (response.ok) {
            const data = await response.json();

            // Update version displays
            currentVersionEl.textContent = data.current_version;
            latestVersionEl.textContent = data.latest_version || '未知';

            if (data.update_available) {
                updateStatus.classList.remove('hidden');
                updateBtn.classList.remove('hidden');

                // Show release notes if available
                if (data.release_notes) {
                    let cleanNotes = data.release_notes;

                    // Try to extract the important changes or changelog section
                    let importantSection = '';

                    // Look for "Important changes" section
                    const importantMatch = cleanNotes.match(/#{1,3}\s*Important changes[\s\S]*?(?=\n#{1,3}\s|$)/i);
                    if (importantMatch) {
                        importantSection = importantMatch[0];
                    }

                    // If no important changes, look for Changelog section
                    if (!importantSection) {
                        const changelogMatch = cleanNotes.match(/#{1,3}\s*Changelog[\s\S]*?(?=\n#{1,3}\s|$)/i);
                        if (changelogMatch) {
                            importantSection = changelogMatch[0];
                        }
                    }

                    // If we found a section, use it; otherwise use the beginning of the notes
                    if (importantSection) {
                        cleanNotes = importantSection;
                    }

                    // Clean up the content
                    cleanNotes = cleanNotes
                        // Remove markdown headers but keep their text
                        .replace(/^#{1,6}\s*/gm, '')
                        // Remove markdown links but keep the text
                        .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
                        // Remove markdown bold/italic markers
                        .replace(/(\*{1,2}|_{1,2})(.*?)\1/g, '$2')
                        // Remove code blocks markers
                        .replace(/```[\s\S]*?```/g, '')
                        .replace(/`([^`]+)`/g, '$1')
                        // Clean up bullet points
                        .replace(/^\s*[\*\-]\s+/gm, '• ')
                        // Remove extra whitespace
                        .replace(/\n{3,}/g, '\n\n')
                        .trim();

                    // Limit length
                    if (cleanNotes.length > 800) {
                        cleanNotes = cleanNotes.substring(0, 800) + '...';
                    }

                    // Default message if empty
                    cleanNotes = cleanNotes || '暂无更新说明';

                    updateResult.innerHTML = `
                        <div style="margin-bottom: 8px;">
                            <strong style="color: #a78bfa; font-size: 0.95rem;">更新说明:</strong>
                        </div>
                        <div style="background: rgba(30, 30, 50, 0.6); padding: 12px; border-radius: 8px; border: 1px solid rgba(167, 139, 250, 0.2);">
                            <pre style="white-space: pre-wrap; font-size: 0.85rem; margin: 0; line-height: 1.5; color: #f0f0f0; font-family: 'SF Mono', Monaco, 'Cascadia Code', monospace;">${cleanNotes}</pre>
                        </div>
                    `;
                    updateResult.classList.remove('hidden', 'error', 'success');
                }
            } else if (data.error) {
                updateResult.textContent = `检查失败: ${data.error}`;
                updateResult.classList.add('error');
                updateResult.classList.remove('hidden', 'success');
            } else {
                updateResult.textContent = '✅ 已是最新版本';
                updateResult.classList.add('success');
                updateResult.classList.remove('hidden', 'error');
            }
        } else {
            throw new Error('Failed to check for updates');
        }
    } catch (error) {
        console.error('Error checking yt-dlp update:', error);
        updateResult.textContent = `检查失败: ${error.message}`;
        updateResult.classList.add('error');
        updateResult.classList.remove('hidden', 'success');
    } finally {
        checkBtn.disabled = false;
        checkBtn.textContent = '🔍 检查更新';
    }
}

async function updateYtDlp() {
    const updateBtn = document.getElementById('update-ytdlp-btn');
    const updateProgress = document.getElementById('ytdlp-update-progress');
    const updateMessage = document.getElementById('ytdlp-update-message');
    const updateResult = document.getElementById('ytdlp-update-result');

    // Show progress
    updateProgress.classList.remove('hidden');
    updateBtn.disabled = true;
    updateResult.classList.add('hidden');

    try {
        updateMessage.textContent = '正在更新 yt-dlp...';

        const response = await fetch(`${API_BASE_URL}/api/yt-dlp/update`, {
            method: 'POST'
        });

        if (response.ok) {
            const data = await response.json();

            if (data.success) {
                updateResult.innerHTML = `
                    ✅ 更新成功!<br>
                    旧版本: ${data.old_version}<br>
                    新版本: ${data.new_version}
                `;
                updateResult.classList.add('success');
                updateResult.classList.remove('error', 'hidden');

                // Update version displays
                document.getElementById('ytdlp-current-version').textContent = data.new_version;
                document.getElementById('ytdlp-latest-version').textContent = data.new_version;

                // Hide update button and status
                updateBtn.classList.add('hidden');
                document.getElementById('ytdlp-update-status').classList.add('hidden');

                // Reload version info
                await loadVersionInfo();
            } else {
                throw new Error(data.message || 'Update failed');
            }
        } else {
            throw new Error('Failed to update yt-dlp');
        }
    } catch (error) {
        console.error('Error updating yt-dlp:', error);
        updateResult.textContent = `更新失败: ${error.message}`;
        updateResult.classList.add('error');
        updateResult.classList.remove('success', 'hidden');
    } finally {
        updateProgress.classList.add('hidden');
        updateBtn.disabled = false;
    }
}

// Browser Cookie Management Functions
async function importBrowserCookies() {
    const browserSelect = document.getElementById('browser-select');
    const importBtn = document.getElementById('import-browser-cookies-btn');
    const statusEl = document.getElementById('browser-cookie-status');
    const statusText = statusEl.querySelector('.status-text');

    const browser = browserSelect.value;

    // Disable button and show loading
    importBtn.disabled = true;
    importBtn.textContent = '🔄 导入中...';
    statusEl.classList.remove('hidden', 'success', 'error');
    statusText.textContent = `正在从 ${browser} 导入cookies...`;

    try {
        const response = await fetch(`${API_BASE_URL}/api/browser-cookies/import`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                browser: browser,
                domain: 'youtube.com'
            })
        });

        const data = await response.json();

        if (data.success) {
            statusEl.classList.add('success');
            statusText.textContent = `✅ 成功从 ${browser} 导入cookies (${data.data.cookie_count} 个)`;

            // Update cookies status
            await updateCookiesStatus();

            // Enable auto-extraction
            const enabledCheckbox = document.getElementById('browser-cookies-enabled');
            if (enabledCheckbox) {
                enabledCheckbox.checked = true;
            }
        } else {
            statusEl.classList.add('error');
            statusText.textContent = `❌ ${data.message}`;
        }
    } catch (error) {
        console.error('Error importing cookies:', error);
        statusEl.classList.add('error');
        statusText.textContent = `❌ 导入失败: ${error.message}`;
    } finally {
        importBtn.disabled = false;
        importBtn.textContent = '🔄 从浏览器导入';
    }
}

async function updateBrowserCookieSettings() {
    const enabled = document.getElementById('browser-cookies-enabled').checked;
    const autoRefresh = document.getElementById('browser-cookies-auto-refresh').checked;
    const browser = document.getElementById('browser-select').value;

    try {
        const response = await fetch(`${API_BASE_URL}/api/config`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                browser_cookies: {
                    enabled: enabled,
                    browser: browser,
                    auto_refresh: autoRefresh,
                    refresh_interval_minutes: 25
                }
            })
        });

        if (response.ok) {
            console.log('Browser cookie settings updated');
            await checkBrowserCookieStatus();
        }
    } catch (error) {
        console.error('Error updating browser cookie settings:', error);
    }
}

async function checkBrowserCookieStatus() {
    try {
        const response = await fetch(`${API_BASE_URL}/api/browser-cookies/status`);
        if (response.ok) {
            const status = await response.json();

            // Update UI based on status
            const statusEl = document.getElementById('browser-cookie-status');
            const statusText = statusEl.querySelector('.status-text');

            if (status.cookies_exist) {
                statusEl.classList.remove('hidden', 'error');

                if (status.cookies_fresh) {
                    statusEl.classList.add('success');
                    statusText.textContent = `✅ Cookies有效 (${status.browser})`;
                } else {
                    statusEl.classList.remove('success');
                    statusText.textContent = `⚠️ Cookies需要刷新 (年龄: ${status.cookies_age})`;
                }
            }

            // Update checkboxes
            const enabledCheckbox = document.getElementById('browser-cookies-enabled');
            const autoRefreshCheckbox = document.getElementById('browser-cookies-auto-refresh');

            if (enabledCheckbox) {
                enabledCheckbox.checked = status.enabled;
            }
            if (autoRefreshCheckbox) {
                autoRefreshCheckbox.checked = status.auto_refresh;
            }
        }
    } catch (error) {
        console.error('Error checking browser cookie status:', error);
    }
}

// Auto-refresh browser cookies if enabled
setInterval(async () => {
    const enabledCheckbox = document.getElementById('browser-cookies-enabled');
    const autoRefreshCheckbox = document.getElementById('browser-cookies-auto-refresh');

    if (enabledCheckbox && autoRefreshCheckbox &&
        enabledCheckbox.checked && autoRefreshCheckbox.checked) {
        // Check if refresh is needed
        const response = await fetch(`${API_BASE_URL}/api/browser-cookies/status`);
        if (response.ok) {
            const status = await response.json();
            if (!status.cookies_fresh) {
                console.log('Auto-refreshing browser cookies...');
                await fetch(`${API_BASE_URL}/api/browser-cookies/refresh`, {
                    method: 'POST'
                });
                await checkBrowserCookieStatus();
            }
        }
    }
}, 60000); // Check every minute

// CookieCloud functionality
function initCookieCloud() {
    const enabledCheckbox = document.getElementById('cookiecloud-enabled');
    const configDiv = document.getElementById('cookiecloud-config');
    const testBtn = document.getElementById('test-cookiecloud-btn');
    const syncBtn = document.getElementById('sync-cookiecloud-btn');

    // Toggle config visibility
    if (enabledCheckbox) {
        enabledCheckbox.addEventListener('change', function() {
            if (this.checked) {
                configDiv.classList.remove('hidden');
                loadCookieCloudConfig();
            } else {
                configDiv.classList.add('hidden');
            }
        });
    }

    // Test connection
    if (testBtn) {
        testBtn.addEventListener('click', async function() {
            const serverUrl = document.getElementById('cookiecloud-server').value;
            const uuidKey = document.getElementById('cookiecloud-uuid').value;
            const password = document.getElementById('cookiecloud-password').value;

            if (!serverUrl || !uuidKey || !password) {
                showCookieCloudStatus('请填写所有必填字段', 'error');
                return;
            }

            // Save config before testing
            await saveCookieCloudConfig();

            testBtn.disabled = true;
            testBtn.textContent = '测试中...';

            try {
                const response = await fetch(`${API_BASE_URL}/api/cookiecloud/test`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        server_url: serverUrl,
                        uuid_key: uuidKey,
                        password: password
                    })
                });

                const result = await response.json();

                if (result.success) {
                    showCookieCloudStatus(result.message, 'success');
                } else {
                    showCookieCloudStatus(result.message, 'error');
                }
            } catch (error) {
                showCookieCloudStatus('测试失败: ' + error.message, 'error');
            } finally {
                testBtn.disabled = false;
                testBtn.textContent = '🔍 测试连接';
            }
        });
    }

    // Sync now
    if (syncBtn) {
        syncBtn.addEventListener('click', async function() {
            // Save config before syncing
            await saveCookieCloudConfig();

            syncBtn.disabled = true;
            syncBtn.textContent = '同步中...';

            try {
                const response = await fetch(`${API_BASE_URL}/api/cookiecloud/sync`, {
                    method: 'POST'
                });

                if (response.ok) {
                    const result = await response.json();
                    // Show the sync result message directly
                    showCookieCloudStatus(result.message, 'success');
                    // Update cookies status immediately after sync
                    await updateCookiesStatus();
                    // Don't reload status immediately as it will overwrite the sync message
                    // Refresh settings
                    await loadSettings();
                } else {
                    const error = await response.json();
                    showCookieCloudStatus('同步失败: ' + error.detail, 'error');
                }
            } catch (error) {
                showCookieCloudStatus('同步失败: ' + error.message, 'error');
            } finally {
                syncBtn.disabled = false;
                syncBtn.textContent = '🔄 立即同步';
            }
        });
    }

    // Load initial config and status
    loadCookieCloudConfig();
    loadCookieCloudStatus();
}

async function loadCookieCloudStatus(showMessage = true) {
    try {
        const response = await fetch(`${API_BASE_URL}/api/cookiecloud/status`);
        if (response.ok) {
            const status = await response.json();

            const enabledCheckbox = document.getElementById('cookiecloud-enabled');
            const configDiv = document.getElementById('cookiecloud-config');

            if (enabledCheckbox) {
                enabledCheckbox.checked = status.enabled;
                if (status.enabled) {
                    configDiv.classList.remove('hidden');
                }
            }

            if (status.configured) {
                document.getElementById('cookiecloud-server').value = status.server_url || '';
                document.getElementById('cookiecloud-auto-sync').checked = status.auto_sync;

                // Only show connection status message if requested and not just after a sync
                if (showMessage && status.connection_status) {
                    showCookieCloudStatus(status.connection_message, 'success');
                }
            }
        }
    } catch (error) {
        console.error('Error loading CookieCloud status:', error);
    }
}

async function loadCookieCloudConfig() {
    try {
        const response = await fetch(`${API_BASE_URL}/api/config`);
        if (response.ok) {
            const config = await response.json();
            const cookiecloud = config.cookiecloud || {};

            // Load all fields from saved config
            if (cookiecloud.server_url) {
                document.getElementById('cookiecloud-server').value = cookiecloud.server_url;
            }
            if (cookiecloud.uuid_key) {
                document.getElementById('cookiecloud-uuid').value = cookiecloud.uuid_key;
            }
            if (cookiecloud.password) {
                document.getElementById('cookiecloud-password').value = cookiecloud.password;
            }
            document.getElementById('cookiecloud-auto-sync').checked = cookiecloud.auto_sync !== false;

            // If CookieCloud is enabled, show the config section
            if (cookiecloud.enabled) {
                document.getElementById('cookiecloud-enabled').checked = true;
                document.getElementById('cookiecloud-config').classList.remove('hidden');
            }
        }
    } catch (error) {
        console.error('Error loading CookieCloud config:', error);
    }
}

async function saveCookieCloudConfig() {
    const enabled = document.getElementById('cookiecloud-enabled').checked;
    const serverUrl = document.getElementById('cookiecloud-server').value;
    const uuidKey = document.getElementById('cookiecloud-uuid').value;
    const password = document.getElementById('cookiecloud-password').value;
    const autoSync = document.getElementById('cookiecloud-auto-sync').checked;

    try {
        const response = await fetch(`${API_BASE_URL}/api/cookiecloud/config`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                enabled: enabled,
                server_url: serverUrl,
                uuid_key: uuidKey,
                password: password,
                auto_sync: autoSync,
                sync_interval_minutes: 30
            })
        });

        if (response.ok) {
            const result = await response.json();
            console.log('CookieCloud config saved:', result);
            return true;
        }
    } catch (error) {
        console.error('Error saving CookieCloud config:', error);
    }
    return false;
}

function showCookieCloudStatus(message, type) {
    const statusEl = document.getElementById('cookiecloud-status');
    const statusText = statusEl.querySelector('.status-text');

    statusEl.classList.remove('hidden', 'success', 'error');

    if (type === 'success') {
        statusEl.classList.add('success');
        statusText.textContent = '✅ ' + message;
    } else if (type === 'error') {
        statusEl.classList.add('error');
        statusText.textContent = '❌ ' + message;
    } else {
        statusText.textContent = message;
    }
}

// Auto-save CookieCloud config on change
document.getElementById('cookiecloud-enabled')?.addEventListener('change', saveCookieCloudConfig);
document.getElementById('cookiecloud-auto-sync')?.addEventListener('change', saveCookieCloudConfig);

// Test admin notification
async function testAdminNotification() {
    try {
        const response = await fetch(`${API_BASE_URL}/api/wecom/test-admin`, {
            method: 'POST'
        });

        if (response.ok) {
            const result = await response.json();
            alert(result.message || '测试通知已发送给管理员');
        } else {
            const error = await response.json();
            alert('发送测试通知失败: ' + (error.detail || '未知错误'));
        }
    } catch (error) {
        console.error('Error testing admin notification:', error);
        alert('测试通知失败: ' + error.message);
    }
}

// Track if batch delete is already initialized
let batchDeleteInitialized = false;

// Batch delete functionality
function setupBatchDelete() {
    // Prevent multiple initializations
    if (batchDeleteInitialized) {
        return;
    }
    batchDeleteInitialized = true;

    const selectAllCheckbox = document.getElementById('select-all-checkbox');
    const batchDeleteBtn = document.getElementById('batch-delete-btn');
    const selectedCount = document.getElementById('selected-count');

    // Update selected count
    function updateSelectedCount() {
        const checkboxes = document.querySelectorAll('.history-checkbox:checked');
        if (selectedCount) {
            selectedCount.textContent = `已选择 ${checkboxes.length} 项`;
        }
        if (batchDeleteBtn) {
            batchDeleteBtn.disabled = checkboxes.length === 0;
        }
    }

    // Select all functionality - use event delegation
    if (selectAllCheckbox) {
        selectAllCheckbox.addEventListener('change', function() {
            const checkboxes = document.querySelectorAll('.history-checkbox');
            checkboxes.forEach(checkbox => {
                checkbox.checked = selectAllCheckbox.checked;
            });
            updateSelectedCount();
        });
    }

    // Individual checkbox change - use event delegation
    document.addEventListener('change', function(e) {
        if (e.target.classList.contains('history-checkbox')) {
            const allCheckboxes = document.querySelectorAll('.history-checkbox');
            const checkedCheckboxes = document.querySelectorAll('.history-checkbox:checked');
            if (selectAllCheckbox) {
                selectAllCheckbox.checked = allCheckboxes.length === checkedCheckboxes.length && allCheckboxes.length > 0;
                selectAllCheckbox.indeterminate = checkedCheckboxes.length > 0 && checkedCheckboxes.length < allCheckboxes.length;
            }
            updateSelectedCount();
        }
    });

    // Batch delete button
    if (batchDeleteBtn) {
        batchDeleteBtn.addEventListener('click', async function() {
            const checkedItems = document.querySelectorAll('.history-checkbox:checked');
            const itemIds = Array.from(checkedItems).map(checkbox => checkbox.dataset.itemId);

            if (itemIds.length === 0) return;

            if (!confirm(`确定要删除选中的 ${itemIds.length} 个项目吗？`)) {
                return;
            }

            try {
                batchDeleteBtn.disabled = true;
                batchDeleteBtn.textContent = '删除中...';

                // Delete items one by one (can be optimized with batch API later)
                const promises = itemIds.map(id =>
                    fetch(`${API_BASE_URL}/api/history/${id}`, {
                        method: 'DELETE'
                    })
                );

                await Promise.all(promises);

                // Reset selection
                if (selectAllCheckbox) {
                    selectAllCheckbox.checked = false;
                }
                updateSelectedCount();

                // Reload history
                await loadHistory();

                // Success message (optional, can be removed if you prefer no alert)
                // alert(`成功删除 ${itemIds.length} 个项目`);
            } catch (error) {
                console.error('Batch delete error:', error);
                alert('批量删除失败: ' + error.message);
            } finally {
                batchDeleteBtn.disabled = false;
                batchDeleteBtn.textContent = '批量删除';
            }
        });
    }
}

// Initialize CookieCloud when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        initCookieCloud();
        setupBatchDelete();
    });
} else {
    initCookieCloud();
    setupBatchDelete();
}
