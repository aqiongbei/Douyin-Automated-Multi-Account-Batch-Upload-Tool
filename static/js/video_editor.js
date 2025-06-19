// 视频编辑器 JavaScript 功能

// 全局变量
let selectedVideo = null;
let sourceType = 'upload'; // 'upload' 或 'folder'
let selectedFolder = null;
let selectedVideoName = null;
let currentSettings = {
    brightness: 0,
    contrast: 0,
    saturation: 0,
    sharpen: 0,
    denoise: 0,
    splitScreen: {
        enabled: false,
        direction: 'horizontal',
        blur: false
    },
    resolution: {
        width: 1280,
        height: 720,
        mode: 'crop'
    },
    transform: {
        rotation: 0,
        flipH: false,
        flipV: false,
        removeBlackBars: false
    },
    framerate: {
        target: 30,
        min: 24,
        max: 30
    },
    frameSkip: {
        enabled: false,
        start: 25,
        end: 30
    },
    zoom: {
        enabled: false,
        min: 0.01,
        max: 0.10,
        direction: 'in'
    },
    bitrate: {
        mode: 'multiplier',
        min: 1.05,
        max: 1.95,
        fixed: 3000
    }
};

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', function() {
    initializeEventListeners();
    updateSettingsSummary();
    setupBitrateMode();
    loadDownloadsFolders();
    updatePresetsList();
});

// 初始化事件监听器
function initializeEventListeners() {
    // 分辨率预设按钮
    document.querySelectorAll('.preset-btn:not(.custom)').forEach(btn => {
        btn.addEventListener('click', function() {
            const width = parseInt(this.dataset.width);
            const height = parseInt(this.dataset.height);
            setResolution(width, height);
            updatePresetButtons(this);
        });
    });

    // 变换按钮
    document.querySelectorAll('.transform-btn:not(.random)').forEach(btn => {
        btn.addEventListener('click', function() {
            const transform = this.dataset.transform;
            applyTransform(transform);
            this.classList.toggle('active');
        });
    });

    // 码率模式切换
    document.querySelectorAll('input[name="bitrate-mode"]').forEach(radio => {
        radio.addEventListener('change', function() {
            switchBitrateMode(this.value);
        });
    });

    // 抽帧和缩放范围输入更新
    setupRangeInputs();
}

// 处理视频文件选择
function handleVideoSelect(input) {
    const file = input.files[0];
    if (!file) return;

    selectedVideo = file;
    
    // 显示视频信息
    document.getElementById('video-name').textContent = file.name;
    document.getElementById('video-size').textContent = formatFileSize(file.size);
    
    // 创建视频预览
    const video = document.getElementById('video-preview');
    const url = URL.createObjectURL(file);
    video.src = url;
    
    video.onloadedmetadata = function() {
        document.getElementById('video-duration').textContent = formatDuration(video.duration);
        document.getElementById('video-resolution').textContent = `${video.videoWidth}×${video.videoHeight}`;
        
        // 显示视频信息和预览
        document.getElementById('selected-video').style.display = 'flex';
        document.getElementById('video-preview').style.display = 'block';
        document.getElementById('no-video-placeholder').style.display = 'none';
        
        // 启用处理按钮
        document.getElementById('process-btn').disabled = false;
        
        updateSettingsSummary();
    };
}

// 移除视频
function removeVideo() {
    selectedVideo = null;
    document.getElementById('selected-video').style.display = 'none';
    document.getElementById('video-preview').style.display = 'none';
    document.getElementById('no-video-placeholder').style.display = 'flex';
    document.getElementById('process-btn').disabled = true;
    document.getElementById('video-file').value = '';
    updateSettingsSummary();
}

// 更新画面调整
function updateAdjustment() {
    currentSettings.brightness = parseInt(document.getElementById('brightness').value);
    currentSettings.contrast = parseInt(document.getElementById('contrast').value);
    currentSettings.saturation = parseInt(document.getElementById('saturation').value);
    currentSettings.sharpen = parseInt(document.getElementById('sharpen').value);
    currentSettings.denoise = parseInt(document.getElementById('denoise').value);
    
    // 更新显示值
    document.getElementById('brightness-value').textContent = currentSettings.brightness;
    document.getElementById('contrast-value').textContent = currentSettings.contrast;
    document.getElementById('saturation-value').textContent = currentSettings.saturation;
    document.getElementById('sharpen-value').textContent = currentSettings.sharpen;
    document.getElementById('denoise-value').textContent = currentSettings.denoise;
    
    updateSettingsSummary();
}

// 随机调整
function randomAdjust(type, min, max) {
    const value = Math.floor(Math.random() * (max - min + 1)) + min;
    const element = document.getElementById(type);
    element.value = value;
    updateAdjustment();
    
    // 添加动画效果
    element.style.transform = 'scale(1.05)';
    setTimeout(() => {
        element.style.transform = 'scale(1)';
    }, 200);
}

// 重置所有调整
function resetAdjustments() {
    const adjustments = ['brightness', 'contrast', 'saturation', 'sharpen', 'denoise'];
    adjustments.forEach(type => {
        document.getElementById(type).value = 0;
        document.getElementById(type + '-value').textContent = '0';
        currentSettings[type] = 0;
    });
    updateSettingsSummary();
}

// 切换分屏效果
function toggleSplitScreen() {
    const enabled = document.getElementById('enable-split').checked;
    currentSettings.splitScreen.enabled = enabled;
    document.getElementById('split-options').style.display = enabled ? 'block' : 'none';
    updateSettingsSummary();
}

// 更新分屏效果
function updateSplitScreen() {
    currentSettings.splitScreen.direction = document.getElementById('split-direction').value;
    currentSettings.splitScreen.blur = document.getElementById('enable-blur').checked;
    updateSettingsSummary();
}

// 设置分辨率
function setResolution(width, height) {
    currentSettings.resolution.width = width;
    currentSettings.resolution.height = height;
    document.getElementById('custom-resolution').style.display = 'none';
    updateSettingsSummary();
}

// 切换自定义分辨率
function toggleCustomResolution() {
    const customDiv = document.getElementById('custom-resolution');
    const isVisible = customDiv.style.display !== 'none';
    customDiv.style.display = isVisible ? 'none' : 'block';
    
    if (!isVisible) {
        updatePresetButtons(document.querySelector('.preset-btn.custom'));
    }
}

// 更新分辨率预设按钮状态
function updatePresetButtons(activeBtn) {
    document.querySelectorAll('.preset-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    activeBtn.classList.add('active');
}

// 应用变换
function applyTransform(transform) {
    switch(transform) {
        case 'rotate-left':
            currentSettings.transform.rotation = (currentSettings.transform.rotation - 90) % 360;
            break;
        case 'rotate-right':
            currentSettings.transform.rotation = (currentSettings.transform.rotation + 90) % 360;
            break;
        case 'flip-h':
            currentSettings.transform.flipH = !currentSettings.transform.flipH;
            break;
        case 'flip-v':
            currentSettings.transform.flipV = !currentSettings.transform.flipV;
            break;
    }
    updateSettingsSummary();
}

// 随机变换
function randomTransform() {
    const transforms = ['rotate-left', 'rotate-right', 'flip-h', 'flip-v'];
    const randomTransform = transforms[Math.floor(Math.random() * transforms.length)];
    applyTransform(randomTransform);
    
    // 高亮对应按钮
    const btn = document.querySelector(`[data-transform="${randomTransform}"]`);
    btn.classList.add('active');
    setTimeout(() => {
        btn.classList.remove('active');
    }, 1000);
}

// 更新变换设置
function updateTransform() {
    currentSettings.transform.removeBlackBars = document.getElementById('remove-black-bars').checked;
    updateSettingsSummary();
}

// 随机帧率
function randomFramerate() {
    const min = parseFloat(document.getElementById('fps-min').value) || 24;
    const max = parseFloat(document.getElementById('fps-max').value) || 30;
    const fps = (Math.random() * (max - min) + min).toFixed(1);
    document.getElementById('target-fps').value = fps;
    currentSettings.framerate.target = parseFloat(fps);
    updateSettingsSummary();
}

// 切换抽帧
function toggleFrameSkip() {
    const enabled = document.getElementById('enable-frame-skip').checked;
    currentSettings.frameSkip.enabled = enabled;
    document.getElementById('frame-skip-options').style.display = enabled ? 'block' : 'none';
    updateSettingsSummary();
}

// 切换缩放
function toggleZoom() {
    const enabled = document.getElementById('enable-zoom').checked;
    currentSettings.zoom.enabled = enabled;
    document.getElementById('zoom-options').style.display = enabled ? 'block' : 'none';
    updateSettingsSummary();
}

// 设置范围输入监听器
function setupRangeInputs() {
    // 抽帧范围
    document.getElementById('skip-start').addEventListener('input', updateFrameSkipDisplay);
    document.getElementById('skip-end').addEventListener('input', updateFrameSkipDisplay);
    
    // 缩放范围
    document.getElementById('zoom-min').addEventListener('input', updateZoomSettings);
    document.getElementById('zoom-max').addEventListener('input', updateZoomSettings);
    document.getElementById('zoom-direction').addEventListener('change', updateZoomSettings);
    
    // 码率范围
    document.getElementById('bitrate-min').addEventListener('input', updateBitrateSettings);
    document.getElementById('bitrate-max').addEventListener('input', updateBitrateSettings);
    document.getElementById('fixed-bitrate').addEventListener('input', updateBitrateSettings);
}

// 更新抽帧显示
function updateFrameSkipDisplay() {
    const start = document.getElementById('skip-start').value;
    const end = document.getElementById('skip-end').value;
    document.getElementById('skip-display').textContent = `${start}-${end}`;
    currentSettings.frameSkip.start = parseInt(start);
    currentSettings.frameSkip.end = parseInt(end);
    updateSettingsSummary();
}

// 更新缩放设置
function updateZoomSettings() {
    currentSettings.zoom.min = parseFloat(document.getElementById('zoom-min').value);
    currentSettings.zoom.max = parseFloat(document.getElementById('zoom-max').value);
    currentSettings.zoom.direction = document.getElementById('zoom-direction').value;
    updateSettingsSummary();
}

// 设置码率模式
function setupBitrateMode() {
    switchBitrateMode('multiplier');
}

// 切换码率模式
function switchBitrateMode(mode) {
    currentSettings.bitrate.mode = mode;
    
    if (mode === 'multiplier') {
        document.getElementById('bitrate-multiplier').style.display = 'block';
        document.getElementById('bitrate-fixed').style.display = 'none';
    } else {
        document.getElementById('bitrate-multiplier').style.display = 'none';
        document.getElementById('bitrate-fixed').style.display = 'block';
    }
    updateSettingsSummary();
}

// 更新码率设置
function updateBitrateSettings() {
    if (currentSettings.bitrate.mode === 'multiplier') {
        currentSettings.bitrate.min = parseFloat(document.getElementById('bitrate-min').value);
        currentSettings.bitrate.max = parseFloat(document.getElementById('bitrate-max').value);
    } else {
        currentSettings.bitrate.fixed = parseInt(document.getElementById('fixed-bitrate').value);
    }
    updateSettingsSummary();
}

// 重置码率设置
function resetBitrate() {
    if (currentSettings.bitrate.mode === 'multiplier') {
        document.getElementById('bitrate-min').value = 1.05;
        document.getElementById('bitrate-max').value = 1.95;
        currentSettings.bitrate.min = 1.05;
        currentSettings.bitrate.max = 1.95;
    } else {
        document.getElementById('fixed-bitrate').value = 3000;
        currentSettings.bitrate.fixed = 3000;
    }
    updateSettingsSummary();
}

// 更新设置摘要
function updateSettingsSummary() {
    const list = document.getElementById('settings-list');
    const settings = [];
    
    if (!selectedVideo) {
        settings.push('请先选择视频文件');
    } else {
        settings.push(`视频文件: ${selectedVideo.name}`);
        
        // 画面调整
        const adjustments = [];
        if (currentSettings.brightness !== 0) adjustments.push(`亮度${currentSettings.brightness > 0 ? '+' : ''}${currentSettings.brightness}`);
        if (currentSettings.contrast !== 0) adjustments.push(`对比度${currentSettings.contrast > 0 ? '+' : ''}${currentSettings.contrast}`);
        if (currentSettings.saturation !== 0) adjustments.push(`饱和度${currentSettings.saturation > 0 ? '+' : ''}${currentSettings.saturation}`);
        if (currentSettings.sharpen > 0) adjustments.push(`锐化+${currentSettings.sharpen}`);
        if (currentSettings.denoise > 0) adjustments.push(`降噪+${currentSettings.denoise}`);
        
        if (adjustments.length > 0) {
            settings.push(`画面调整: ${adjustments.join(', ')}`);
        }
        
        // 分屏效果
        if (currentSettings.splitScreen.enabled) {
            settings.push(`分屏: 3×3宫格 ${currentSettings.splitScreen.direction}滚动${currentSettings.splitScreen.blur ? ' 虚化' : ''}`);
        }
        
        // 分辨率
        settings.push(`分辨率: ${currentSettings.resolution.width}×${currentSettings.resolution.height} (${getScaleModeText()})`);
        
        // 变换
        const transforms = [];
        if (currentSettings.transform.rotation !== 0) transforms.push(`旋转${currentSettings.transform.rotation}°`);
        if (currentSettings.transform.flipH) transforms.push('水平翻转');
        if (currentSettings.transform.flipV) transforms.push('垂直翻转');
        if (currentSettings.transform.removeBlackBars) transforms.push('去除黑边');
        
        if (transforms.length > 0) {
            settings.push(`变换: ${transforms.join(', ')}`);
        }
        
        // 帧率
        settings.push(`帧率: ${currentSettings.framerate.target} FPS`);
        
        // 抽帧
        if (currentSettings.frameSkip.enabled) {
            settings.push(`抽帧: 每${currentSettings.frameSkip.start}-${currentSettings.frameSkip.end}帧抽一帧`);
        }
        
        // 动态缩放
        if (currentSettings.zoom.enabled) {
            settings.push(`动态缩放: ${currentSettings.zoom.min}-${currentSettings.zoom.max} (${getZoomDirectionText()})`);
        }
        
        // 码率
        if (currentSettings.bitrate.mode === 'multiplier') {
            settings.push(`码率: ${currentSettings.bitrate.min}×-${currentSettings.bitrate.max}× 倍率`);
        } else {
            settings.push(`码率: ${currentSettings.bitrate.fixed}kb/s 固定`);
        }
    }
    
    list.innerHTML = settings.map(setting => `<li>${setting}</li>`).join('');
}

// 获取缩放模式文本
function getScaleModeText() {
    const mode = document.getElementById('scale-mode').value;
    const modes = {
        'stretch': '拉伸适应',
        'crop': '裁切适应',
        'letterbox': '添加黑边',
        'pad': '填充模糊'
    };
    return modes[mode] || '未知';
}

// 获取缩放方向文本
function getZoomDirectionText() {
    const direction = currentSettings.zoom.direction;
    const directions = {
        'in': '放大',
        'out': '缩小',
        'random': '随机'
    };
    return directions[direction] || '未知';
}

// 处理视频
async function processVideo() {
    if (sourceType === 'upload' && !selectedVideo) {
        alert('请先选择视频文件');
        return;
    }
    
    if (sourceType === 'folder' && (!selectedFolder || !selectedVideoName)) {
        alert('请先选择文件夹和视频文件');
        return;
    }
    
    // 显示处理状态
    const statusDiv = document.getElementById('process-status');
    const progressFill = document.getElementById('progress-fill');
    const progressText = document.getElementById('progress-text');
    
    statusDiv.style.display = 'block';
    document.getElementById('process-btn').disabled = true;
    
    try {
        // 模拟进度更新
        const progressInterval = setInterval(() => {
            const currentWidth = parseFloat(progressFill.style.width) || 0;
            if (currentWidth < 90) {
                const newWidth = Math.min(currentWidth + Math.random() * 10, 90);
                progressFill.style.width = newWidth + '%';
                progressText.textContent = Math.round(newWidth) + '%';
            }
        }, 500);
        
        // 发送请求到后端
        let response;
        
        if (sourceType === 'upload') {
            // 文件上传模式
            const formData = new FormData();
            formData.append('video', selectedVideo);
            formData.append('settings', JSON.stringify(currentSettings));
            
            response = await fetch('/api/video/process', {
                method: 'POST',
                body: formData
            });
        } else {
            // 文件夹选择模式
            response = await fetch('/api/video/process', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    folder_name: selectedFolder,
                    video_filename: selectedVideoName,
                    settings: currentSettings
                })
            });
        }
        
        clearInterval(progressInterval);
        progressFill.style.width = '100%';
        progressText.textContent = '100%';
        
        const result = await response.json();
        
        if (response.ok && result.success) {
            // 显示成功消息
            statusDiv.querySelector('.status-message').innerHTML = 
                '<i class="ri-check-circle-line" style="color: var(--success-color);"></i><span>视频处理完成！正在准备下载...</span>';
            
            // 创建下载链接
            setTimeout(() => {
                const downloadLink = document.createElement('a');
                downloadLink.href = `/videos/${result.output_file}`;
                // 获取文件名（去掉路径）
                const filename = result.output_file.split('/').pop();
                downloadLink.download = filename;
                downloadLink.style.display = 'none';
                document.body.appendChild(downloadLink);
                downloadLink.click();
                document.body.removeChild(downloadLink);
                
                // 重置状态
                statusDiv.style.display = 'none';
                document.getElementById('process-btn').disabled = false;
                progressFill.style.width = '0%';
                progressText.textContent = '0%';
            }, 1000);
            
        } else {
            throw new Error(result.error || '处理失败');
        }
        
    } catch (error) {
        console.error('处理失败:', error);
        statusDiv.querySelector('.status-message').innerHTML = 
            '<i class="ri-error-warning-line" style="color: var(--error-color);"></i><span>处理失败：' + error.message + '</span>';
        
        setTimeout(() => {
            statusDiv.style.display = 'none';
            document.getElementById('process-btn').disabled = false;
            progressFill.style.width = '0%';
            progressText.textContent = '0%';
        }, 5000);
    }
}

// 保存预设
function savePreset() {
    document.getElementById('preset-modal').classList.remove('hidden');
}

// 加载预设
function loadPreset() {
    document.getElementById('preset-modal').classList.remove('hidden');
}

// 关闭预设模态框
function closePresetModal() {
    document.getElementById('preset-modal').classList.add('hidden');
}

// 保存新预设
function saveNewPreset() {
    const name = document.getElementById('preset-name').value.trim();
    if (!name) {
        alert('请输入预设名称');
        return;
    }
    
    // 保存到localStorage
    const presets = JSON.parse(localStorage.getItem('videoEditorPresets') || '{}');
    presets[name] = JSON.parse(JSON.stringify(currentSettings));
    localStorage.setItem('videoEditorPresets', JSON.stringify(presets));
    
    // 更新预设列表
    updatePresetsList();
    
    document.getElementById('preset-name').value = '';
    alert('预设保存成功！');
}

// 更新预设列表
function updatePresetsList() {
    const presets = JSON.parse(localStorage.getItem('videoEditorPresets') || '{}');
    const container = document.getElementById('preset-items');
    
    if (Object.keys(presets).length === 0) {
        container.innerHTML = `
            <div class="empty-preset">
                <i class="ri-folder-open-line"></i>
                <p>暂无保存的预设</p>
            </div>
        `;
        return;
    }
    
    container.innerHTML = Object.keys(presets).map(name => `
        <div class="preset-item">
            <span>${name}</span>
            <div class="preset-actions">
                <button onclick="loadPresetByName('${name}')">加载</button>
                <button onclick="deletePreset('${name}')" class="danger-button">删除</button>
            </div>
        </div>
    `).join('');
}

// 按名称加载预设
function loadPresetByName(name) {
    const presets = JSON.parse(localStorage.getItem('videoEditorPresets') || '{}');
    if (presets[name]) {
        currentSettings = JSON.parse(JSON.stringify(presets[name]));
        applySettingsToUI();
        updateSettingsSummary();
        closePresetModal();
        alert('预设加载成功！');
    }
}

// 删除预设
function deletePreset(name) {
    if (confirm(`确定要删除预设"${name}"吗？`)) {
        const presets = JSON.parse(localStorage.getItem('videoEditorPresets') || '{}');
        delete presets[name];
        localStorage.setItem('videoEditorPresets', JSON.stringify(presets));
        updatePresetsList();
    }
}

// 将设置应用到UI
function applySettingsToUI() {
    // 画面调整
    document.getElementById('brightness').value = currentSettings.brightness;
    document.getElementById('contrast').value = currentSettings.contrast;
    document.getElementById('saturation').value = currentSettings.saturation;
    document.getElementById('sharpen').value = currentSettings.sharpen;
    document.getElementById('denoise').value = currentSettings.denoise;
    updateAdjustment();
    
    // 分屏效果
    document.getElementById('enable-split').checked = currentSettings.splitScreen.enabled;
    document.getElementById('split-direction').value = currentSettings.splitScreen.direction;
    document.getElementById('enable-blur').checked = currentSettings.splitScreen.blur;
    toggleSplitScreen();
    
    // 分辨率
    document.getElementById('custom-width').value = currentSettings.resolution.width;
    document.getElementById('custom-height').value = currentSettings.resolution.height;
    document.getElementById('scale-mode').value = currentSettings.resolution.mode;
    
    // 帧率
    document.getElementById('target-fps').value = currentSettings.framerate.target;
    document.getElementById('fps-min').value = currentSettings.framerate.min;
    document.getElementById('fps-max').value = currentSettings.framerate.max;
    
    // 抽帧
    document.getElementById('enable-frame-skip').checked = currentSettings.frameSkip.enabled;
    document.getElementById('skip-start').value = currentSettings.frameSkip.start;
    document.getElementById('skip-end').value = currentSettings.frameSkip.end;
    toggleFrameSkip();
    
    // 缩放
    document.getElementById('enable-zoom').checked = currentSettings.zoom.enabled;
    document.getElementById('zoom-min').value = currentSettings.zoom.min;
    document.getElementById('zoom-max').value = currentSettings.zoom.max;
    document.getElementById('zoom-direction').value = currentSettings.zoom.direction;
    toggleZoom();
    
    // 码率
    document.querySelector(`input[name="bitrate-mode"][value="${currentSettings.bitrate.mode}"]`).checked = true;
    document.getElementById('bitrate-min').value = currentSettings.bitrate.min;
    document.getElementById('bitrate-max').value = currentSettings.bitrate.max;
    document.getElementById('fixed-bitrate').value = currentSettings.bitrate.fixed;
    switchBitrateMode(currentSettings.bitrate.mode);
}

// 工具函数
function formatFileSize(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

function formatDuration(seconds) {
    const hrs = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);
    
    if (hrs > 0) {
        return `${hrs}:${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    }
    return `${mins}:${secs.toString().padStart(2, '0')}`;
}

// 切换视频源类型
function toggleSourceType() {
    const uploadRadio = document.querySelector('input[name="sourceType"][value="upload"]');
    const folderRadio = document.querySelector('input[name="sourceType"][value="folder"]');
    
    if (uploadRadio.checked) {
        sourceType = 'upload';
        document.getElementById('upload-section').style.display = 'block';
        document.getElementById('folder-section').style.display = 'none';
        // 清除文件夹选择状态
        selectedFolder = null;
        selectedVideoName = null;
        document.getElementById('folder-select').value = '';
        document.getElementById('video-select-section').style.display = 'none';
    } else if (folderRadio.checked) {
        sourceType = 'folder';
        document.getElementById('upload-section').style.display = 'none';
        document.getElementById('folder-section').style.display = 'block';
        // 清除上传文件状态
        selectedVideo = null;
        document.getElementById('video-file').value = '';
        removeVideo();
    }
}

// 加载downloads文件夹列表
async function loadDownloadsFolders() {
    try {
        const response = await fetch('/api/downloads/folders');
        const data = await response.json();
        
        if (data.success) {
            const folderSelect = document.getElementById('folder-select');
            folderSelect.innerHTML = '<option value="">请选择下载文件夹</option>';
            
            data.folders.forEach(folder => {
                const option = document.createElement('option');
                option.value = folder;
                option.textContent = folder;
                folderSelect.appendChild(option);
            });
        } else {
            console.error('加载文件夹列表失败:', data.error);
        }
    } catch (error) {
        console.error('加载文件夹列表时发生错误:', error);
    }
}

// 加载指定文件夹的视频列表
async function loadFolderVideos() {
    const folderSelect = document.getElementById('folder-select');
    const selectedFolderName = folderSelect.value;
    
    if (!selectedFolderName) {
        document.getElementById('video-select-section').style.display = 'none';
        return;
    }
    
    try {
        const response = await fetch(`/api/downloads/videos/${encodeURIComponent(selectedFolderName)}`);
        const data = await response.json();
        
        if (data.success) {
            const videoSelect = document.getElementById('video-select');
            videoSelect.innerHTML = '<option value="">请选择视频文件</option>';
            
            data.videos.forEach(video => {
                const option = document.createElement('option');
                option.value = video;
                option.textContent = video;
                videoSelect.appendChild(option);
            });
            
            selectedFolder = selectedFolderName;
            document.getElementById('video-select-section').style.display = 'block';
        } else {
            console.error('加载视频列表失败:', data.error);
            alert('加载视频列表失败: ' + data.error);
        }
    } catch (error) {
        console.error('加载视频列表时发生错误:', error);
        alert('加载视频列表时发生错误: ' + error.message);
    }
}

// 处理文件夹视频选择
function handleFolderVideoSelect() {
    const videoSelect = document.getElementById('video-select');
    selectedVideoName = videoSelect.value;
    
    if (!selectedVideoName || !selectedFolder) {
        removeVideo();
        return;
    }
    
    // 显示视频信息
    document.getElementById('video-name').textContent = selectedVideoName;
    document.getElementById('video-size').textContent = '--';
    document.getElementById('video-duration').textContent = '--:--';
    document.getElementById('video-resolution').textContent = '--×--';
    
    // 设置预览
    const video = document.getElementById('video-preview');
    const videoPath = `/videos/downloads/${selectedFolder}/${selectedVideoName}`;
    video.src = videoPath;
    
    video.onloadedmetadata = function() {
        document.getElementById('video-duration').textContent = formatDuration(video.duration);
        document.getElementById('video-resolution').textContent = `${video.videoWidth}×${video.videoHeight}`;
    };
    
    video.onerror = function() {
        // 如果无法加载预览，仍然允许处理
        console.warn('无法加载视频预览');
    };
    
    // 显示视频信息和预览
    document.getElementById('selected-video').style.display = 'flex';
    document.getElementById('video-preview').style.display = 'block';
    document.getElementById('no-video-placeholder').style.display = 'none';
    
    // 启用处理按钮
    document.getElementById('process-btn').disabled = false;
    
    updateSettingsSummary();
} 