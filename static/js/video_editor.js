// 视频编辑器 JavaScript 功能

// 全局变量
let selectedVideo = null;
let sourceType = 'upload'; // 'upload' 或 'folder'
let selectedFolder = null;
let selectedVideoName = null;
let selectedVideoNames = []; // 多选模式下的视频名称数组
let currentSettings = {
    brightness: 0,
    contrast: 0,
    saturation: 0,
    sharpen: 0,
    denoise: 0,
    splitScreen: {
        enabled: false,
        direction: 'vertical',  // 'vertical'=上下分屏, 'horizontal'=左右分屏, 'auto'=自动
        ratio: 'equal',         // 'equal'=均等, 'center-large'=中间大, 'edges-large'=两端大
        blur: false             // 边界柔化
    },
    resolution: {
        width: 'original',
        height: 'original',
        mode: 'crop'
    },
    transform: {
        keep_original: true,
        rotation: 0,
        flipH: false,
        flipV: false,
        removeBlackBars: false
    },
    framerate: {
        keep_original: true,
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
        keep_original: true,
        mode: 'multiplier',
        min: 1.05,
        max: 1.95,
        fixed: 3000
    },
    abFusion: {
        enabled: false,
        method: 'transparency',
        bVideoPath: null,
        bVideoSource: 'upload',
        opacity: 0.35,
        adaptiveOpacity: false,
        region: 'corners',
        regionRatio: 0.25,
        cycle: 5,
        opacityMin: 0.2,
        opacityMax: 0.5,
        metadataDisguise: false,
        audioPhaseAdjust: false,
        keyframeModify: false,
        builtinMaterial: '',
        aiGenerateType: 'nature'
    }
};
let tasksList = []; // 任务队列
let processingTaskId = null; // 当前正在处理的任务ID

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', function() {
    initializeEventListeners();
    updateSettingsSummary();
    setupBitrateMode();
    loadDownloadsFolders();
    updatePresetsList();
    initializeSettings();
    setupRangeInputs();
    resetAdjustments();
});

// 初始化事件监听器
function initializeEventListeners() {
    // 分辨率预设按钮
    document.querySelectorAll('.preset-btn:not(.custom)').forEach(btn => {
        btn.addEventListener('click', function() {
            const width = this.dataset.width === 'original' ? 'original' : parseInt(this.dataset.width);
            const height = this.dataset.height === 'original' ? 'original' : parseInt(this.dataset.height);
            setResolution(width, height);
            updatePresetButtons(this);
        });
    });

    // 变换按钮
    document.querySelectorAll('.transform-btn:not(.random)').forEach(btn => {
        btn.addEventListener('click', function() {
            // 只在不保持原始变换时才应用变换
            if (!currentSettings.transform.keep_original) {
                const transform = this.dataset.transform;
                applyTransform(transform);
                this.classList.toggle('active');
            }
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
    const video = document.getElementById('preview-video');
    const url = URL.createObjectURL(file);
    video.src = url;
    
    video.onloadedmetadata = function() {
        document.getElementById('video-duration').textContent = formatDuration(video.duration);
        document.getElementById('video-resolution').textContent = `${video.videoWidth}×${video.videoHeight}`;
        
        // 显示视频信息和预览
        document.getElementById('selected-video').style.display = 'flex';
        document.getElementById('preview-video').style.display = 'block';
        document.getElementById('no-video-placeholder').style.display = 'none';
        
        // 启用处理按钮
        document.getElementById('process-btn').disabled = false;
        
        // 默认选择保持原分辨率
        setResolution('original', 'original');
        updatePresetButtons(document.querySelector('.preset-btn.original'));
        
        updateSettingsSummary();
    };
}

// 移除视频
function removeVideo() {
    selectedVideo = null;
    document.getElementById('selected-video').style.display = 'none';
    document.getElementById('preview-video').style.display = 'none';
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
    currentSettings.splitScreen.ratio = document.getElementById('split-ratio').value;
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
    
    // 只在不保持原码率时显示设置
    if (!currentSettings.bitrate.keep_original) {
        if (mode === 'multiplier') {
            document.getElementById('bitrate-multiplier').style.display = 'block';
            document.getElementById('bitrate-fixed').style.display = 'none';
        } else {
            document.getElementById('bitrate-multiplier').style.display = 'none';
            document.getElementById('bitrate-fixed').style.display = 'block';
        }
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
    
    // 检查是否有视频被选择（上传模式或文件夹模式）
    const hasVideo = (sourceType === 'upload' && selectedVideo) || 
                     (sourceType === 'folder' && selectedVideoNames.length > 0 && selectedFolder);
    
    if (!hasVideo) {
        settings.push('请先选择视频文件');
    } else {
        // 根据不同模式显示不同的文件名
        if (sourceType === 'upload') {
            settings.push(`视频文件: ${selectedVideo.name}`);
        } else {
            if (selectedVideoNames.length === 1) {
                settings.push(`视频文件: ${selectedVideoNames[0]}`);
            } else {
                settings.push(`批量处理: ${selectedVideoNames.length} 个视频文件`);
            }
        }
        
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
        const directionText = getSplitDirectionText(currentSettings.splitScreen.direction);
        const ratioText = getSplitRatioText(currentSettings.splitScreen.ratio);
        settings.push(`分屏: ${directionText} ${ratioText}${currentSettings.splitScreen.blur ? ' 柔化' : ''}`);
    }
    
    // AB帧融合
    if (currentSettings.abFusion.enabled) {
        let fusionText = 'AB融合: ';
        
        switch(currentSettings.abFusion.method) {
            case 'transparency':
                fusionText += `透明度混合 ${Math.round(currentSettings.abFusion.opacity * 100)}%`;
                if (currentSettings.abFusion.adaptiveOpacity) fusionText += ' 自适应';
                break;
            case 'region':
                const regionMap = {
                    'corners': '四角',
                    'edges': '边缘', 
                    'center': '中心'
                };
                fusionText += `区域替换 ${regionMap[currentSettings.abFusion.region]} ${Math.round(currentSettings.abFusion.regionRatio * 100)}%`;
                break;
            case 'dynamic':
                fusionText += `动态混合 ${currentSettings.abFusion.cycle}秒周期`;
                break;
        }
        
        if (currentSettings.abFusion.bVideoPath) {
            fusionText += ' ✓B视频';
        }
        
        settings.push(fusionText);
    }
        
        // 分辨率
        if (currentSettings.resolution.width === 'original' && currentSettings.resolution.height === 'original') {
            settings.push(`分辨率: 保持原分辨率 (${getScaleModeText()})`);
        } else {
            settings.push(`分辨率: ${currentSettings.resolution.width}×${currentSettings.resolution.height} (${getScaleModeText()})`);
        }
        
        // 变换
        if (currentSettings.transform.keep_original) {
            settings.push(`变换: 保持原始方向`);
        } else {
            const transforms = [];
            if (currentSettings.transform.rotation !== 0) transforms.push(`旋转${currentSettings.transform.rotation}°`);
            if (currentSettings.transform.flipH) transforms.push('水平翻转');
            if (currentSettings.transform.flipV) transforms.push('垂直翻转');
            if (currentSettings.transform.removeBlackBars) transforms.push('去除黑边');
            
            if (transforms.length > 0) {
                settings.push(`变换: ${transforms.join(', ')}`);
            } else {
                settings.push(`变换: 无变换`);
            }
        }
        
        // 帧率
        if (currentSettings.framerate.keep_original) {
            settings.push(`帧率: 保持原帧率`);
        } else {
            settings.push(`帧率: ${currentSettings.framerate.target} FPS`);
        }
        
        // 抽帧
        if (currentSettings.frameSkip.enabled) {
            settings.push(`抽帧: 每${currentSettings.frameSkip.start}-${currentSettings.frameSkip.end}帧抽一帧`);
        }
        
        // 动态缩放
        if (currentSettings.zoom.enabled) {
            settings.push(`动态缩放: ${currentSettings.zoom.min}-${currentSettings.zoom.max} (${getZoomDirectionText()})`);
        }
        
        // 码率
        if (currentSettings.bitrate.keep_original) {
            settings.push(`码率: 保持原码率`);
        } else if (currentSettings.bitrate.mode === 'multiplier') {
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

// 获取分屏方向文本
function getSplitDirectionText(direction) {
    const directions = {
        'vertical': '上下分屏',
        'horizontal': '左右分屏', 
        'auto': '自动分屏'
    };
    return directions[direction] || '上下分屏';
}

// 获取分屏比例文本
function getSplitRatioText(ratio) {
    const ratios = {
        'equal': '均等分割',
        'center-large': '中间放大',
        'edges-large': '两端放大'
    };
    return ratios[ratio] || '均等分割';
}

// 处理视频
async function processVideo() {
    if (sourceType === 'upload' && !selectedVideo) {
        alert('请先选择视频文件');
        return;
    }
    
    if (sourceType === 'folder' && (!selectedFolder || selectedVideoNames.length === 0)) {
        alert('请先选择文件夹和视频文件');
        return;
    }
    
    // 创建处理任务
    if (sourceType === 'upload') {
        // 文件上传模式 - 创建单个任务
        const videoName = selectedVideo.name || '上传视频';
        createBatchVideoTasks([selectedVideo], {
            sourceType: 'upload',
            settings: JSON.parse(JSON.stringify(currentSettings))
        });
    } else {
        // 文件夹选择模式
        if (selectedFolder === '__all__') {
            // 全选所有文件夹模式 - 创建多个任务
            createBatchVideoTasks(selectedVideoNames, {
                sourceType: 'folder',
                folder: '__all__',
                settings: JSON.parse(JSON.stringify(currentSettings))
            });
        } else {
            // 单个文件夹模式 - 创建多个任务
            createBatchVideoTasks(selectedVideoNames, {
                sourceType: 'folder',
                folder: selectedFolder,
                settings: JSON.parse(JSON.stringify(currentSettings))
            });
        }
    }
    
    // 显示简短的处理提示
    const statusDiv = document.getElementById('progress-section');
    statusDiv.style.display = 'block';
    statusDiv.querySelector('.status-message').innerHTML = 
        `<div style="text-align: center;">
            <div style="margin-bottom: 12px;">
                <i class="ri-checkbox-circle-line" style="color: var(--success-color);"></i>
                <span>视频处理任务已添加至队列</span>
            </div>
            <button onclick="hideProcessStatus()" 
                    style="background: var(--border-color); color: var(--text-color); border: none; padding: 8px 16px; border-radius: 6px; cursor: pointer;">
                关闭
            </button>
        </div>`;
    
    // 隐藏进度条
    const progressBar = statusDiv.querySelector('.progress-bar');
    const progressText = statusDiv.querySelector('.progress-text');
    if (progressBar) {
        progressBar.style.display = 'none';
    }
    if (progressText) {
        progressText.style.display = 'none';
    }
    
    // 3秒后自动隐藏状态提示
    setTimeout(() => {
        hideProcessStatus();
    }, 3000);
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
    document.getElementById('split-ratio').value = currentSettings.splitScreen.ratio;
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
        document.getElementById('folder-select-section').style.display = 'none';
        // 清除文件夹选择状态
        selectedFolder = null;
        selectedVideoName = null;
        document.getElementById('folder-select').value = '';
        document.getElementById('video-select-section').style.display = 'none';
    } else if (folderRadio.checked) {
        sourceType = 'folder';
        document.getElementById('upload-section').style.display = 'none';
        document.getElementById('folder-select-section').style.display = 'block';
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
            
            // 添加全选所有文件夹选项
            const allFoldersOption = document.createElement('option');
            allFoldersOption.value = '__all__';
            allFoldersOption.textContent = '全选所有文件夹';
            folderSelect.appendChild(allFoldersOption);
            
            // 添加各个文件夹选项
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
        let response, data;
        
        // 处理全选所有文件夹的特殊情况
        if (selectedFolderName === '__all__') {
            response = await fetch('/api/downloads/all_videos');
            data = await response.json();
            
            if (data.success) {
                const videoSelect = document.getElementById('video-select');
                videoSelect.innerHTML = ''; // 清空选项
                
                // 添加所有视频
                data.videos.forEach(video => {
                    const option = document.createElement('option');
                    option.value = JSON.stringify(video); // 将视频信息存为JSON字符串
                    option.textContent = `${video.folder}/${video.name}`; // 显示为"文件夹/文件名"格式
                    videoSelect.appendChild(option);
                });
                
                selectedFolder = '__all__';
                selectedVideoNames = []; // 重置选中的视频
                updateSelectedCount();
                document.getElementById('video-select-section').style.display = 'block';
                
                // 选中所有视频
                selectAllVideos();
                return;
            }
        } else {
            // 原有逻辑，加载单个文件夹的视频
            response = await fetch(`/api/downloads/videos/${encodeURIComponent(selectedFolderName)}`);
            data = await response.json();
            
            if (data.success) {
                const videoSelect = document.getElementById('video-select');
                videoSelect.innerHTML = ''; // 清空选项，不添加"请选择视频文件"
                
                data.videos.forEach(video => {
                    const option = document.createElement('option');
                    option.value = video;
                    option.textContent = video;
                    videoSelect.appendChild(option);
                });
                
                selectedFolder = selectedFolderName;
                selectedVideoNames = []; // 重置选中的视频
                updateSelectedCount();
                document.getElementById('video-select-section').style.display = 'block';
                return;
            }
        }
        
        console.error('加载视频列表失败:', data.error);
        alert('加载视频列表失败: ' + data.error);
    } catch (error) {
        console.error('加载视频列表时发生错误:', error);
        alert('加载视频列表时发生错误: ' + error.message);
    }
}

// 处理文件夹视频选择
function handleFolderVideoSelect() {
    const videoSelect = document.getElementById('video-select');
    
    // 获取选中的视频
    if (selectedFolder === '__all__') {
        // 处理全选所有文件夹的情况
        selectedVideoNames = Array.from(videoSelect.selectedOptions).map(option => option.value);
    } else {
        // 原有逻辑
        selectedVideoNames = Array.from(videoSelect.selectedOptions).map(option => option.value);
    }
    
    if (selectedVideoNames.length === 0 || !selectedFolder) {
        removeVideo();
        return;
    }
    
    // 更新选择计数
    updateSelectedCount();
    
    // 显示第一个视频的信息作为预览
    let firstVideo, videoPath;
    
    if (selectedFolder === '__all__') {
        // 处理全选所有文件夹情况下的视频预览
        const firstVideoData = JSON.parse(selectedVideoNames[0]);
        firstVideo = firstVideoData.name;
        videoPath = `/videos/downloads/${firstVideoData.folder}/${firstVideoData.name}`;
        selectedVideoName = firstVideo; // 保持兼容性
    } else {
        // 原有逻辑
        firstVideo = selectedVideoNames[0];
        videoPath = `/videos/downloads/${selectedFolder}/${firstVideo}`;
        selectedVideoName = firstVideo; // 保持兼容性
    }
    
    if (selectedVideoNames.length === 1) {
        // 单选模式：显示具体视频信息
        document.getElementById('video-name').textContent = firstVideo;
    } else {
        // 多选模式：显示选择数量
        document.getElementById('video-name').textContent = `已选择 ${selectedVideoNames.length} 个视频`;
    }
    
    document.getElementById('video-size').textContent = '--';
    document.getElementById('video-duration').textContent = '--:--';
    document.getElementById('video-resolution').textContent = '--×--';
    
    // 设置预览（使用第一个视频）
    const video = document.getElementById('preview-video');
    video.src = videoPath;
    
    video.onloadedmetadata = function() {
        if (selectedVideoNames.length === 1) {
            // 单选时显示具体信息
            document.getElementById('video-duration').textContent = formatDuration(video.duration);
            document.getElementById('video-resolution').textContent = `${video.videoWidth}×${video.videoHeight}`;
        } else {
            // 多选时显示通用信息
            document.getElementById('video-duration').textContent = `${selectedVideoNames.length} 个视频`;
            document.getElementById('video-resolution').textContent = '批量处理';
        }
    };
    
    video.onerror = function() {
        // 如果无法加载预览，仍然允许处理
        console.warn('无法加载视频预览');
    };
    
    // 显示视频信息和预览
    document.getElementById('selected-video').style.display = 'flex';
    document.getElementById('preview-video').style.display = 'block';
    document.getElementById('no-video-placeholder').style.display = 'none';
    
    // 启用处理按钮
    document.getElementById('process-btn').disabled = false;
    
    // 默认选择保持原分辨率
    setResolution('original', 'original');
    updatePresetButtons(document.querySelector('.preset-btn.original'));
    
    updateSettingsSummary();
}

// 预览视频效果
function previewVideo() {
    const video = document.getElementById('preview-video');
    if (video && video.src) {
        if (video.paused) {
            video.play();
            document.getElementById('preview-btn').innerHTML = '<i class="ri-pause-line"></i> 暂停预览';
        } else {
            video.pause();
            document.getElementById('preview-btn').innerHTML = '<i class="ri-play-line"></i> 预览效果';
        }
    }
}

// 切换是否保持原帧率
function toggleOriginalFps() {
    const keepOriginal = document.getElementById('keep-original-fps').checked;
    const fpsSettings = document.getElementById('fps-settings');
    
    currentSettings.framerate.keep_original = keepOriginal;
    fpsSettings.style.display = keepOriginal ? 'none' : 'block';
    
    updateSettingsSummary();
}

// 切换是否保持原码率
function toggleOriginalBitrate() {
    const keepOriginal = document.getElementById('keep-original-bitrate').checked;
    const bitrateSettings = document.getElementById('bitrate-mode-settings');
    const multiplierDiv = document.getElementById('bitrate-multiplier');
    const fixedDiv = document.getElementById('bitrate-fixed');
    
    currentSettings.bitrate.keep_original = keepOriginal;
    
    if (keepOriginal) {
        bitrateSettings.style.display = 'none';
        multiplierDiv.style.display = 'none';
        fixedDiv.style.display = 'none';
    } else {
        bitrateSettings.style.display = 'block';
        // 根据当前模式显示对应设置
        if (currentSettings.bitrate.mode === 'multiplier') {
            multiplierDiv.style.display = 'block';
            fixedDiv.style.display = 'none';
        } else {
            multiplierDiv.style.display = 'none';
            fixedDiv.style.display = 'block';
        }
    }
    
    updateSettingsSummary();
}

// 切换是否保持原始变换
function toggleOriginalTransform() {
    const keepOriginal = document.getElementById('keep-original-transform').checked;
    const transformButtons = document.getElementById('transform-buttons');
    const blackBarsOption = document.getElementById('black-bars-option');
    
    currentSettings.transform.keep_original = keepOriginal;
    
    if (keepOriginal) {
        transformButtons.style.display = 'none';
        blackBarsOption.style.display = 'none';
        // 重置变换状态
        currentSettings.transform.rotation = 0;
        currentSettings.transform.flipH = false;
        currentSettings.transform.flipV = false;
        currentSettings.transform.removeBlackBars = false;
        // 清除所有变换按钮的active状态
        document.querySelectorAll('.transform-btn').forEach(btn => {
            btn.classList.remove('active');
        });
    } else {
        transformButtons.style.display = 'grid';
        blackBarsOption.style.display = 'block';
    }
    
    updateSettingsSummary();
}

// 重置变换
function resetTransform() {
    currentSettings.transform.rotation = 0;
    currentSettings.transform.flipH = false;
    currentSettings.transform.flipV = false;
    currentSettings.transform.removeBlackBars = false;
    
    // 清除所有按钮的active状态
    document.querySelectorAll('.transform-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    
    // 重置复选框
    document.getElementById('remove-black-bars').checked = false;
    
    updateSettingsSummary();
}

// 下载处理后的视频
function downloadProcessedVideo(outputFile, filename) {
    const downloadLink = document.createElement('a');
    downloadLink.href = `/videos/${outputFile}`;
    downloadLink.download = filename;
    downloadLink.style.display = 'none';
    document.body.appendChild(downloadLink);
    downloadLink.click();
    document.body.removeChild(downloadLink);
}

// 隐藏处理状态
function hideProcessStatus() {
    const statusDiv = document.getElementById('progress-section');
    const progressFill = document.getElementById('progress-fill');
    const progressText = document.getElementById('progress-text');
    const progressBar = statusDiv.querySelector('.progress-bar');
    
    statusDiv.style.display = 'none';
    progressFill.style.width = '0%';
    progressText.textContent = '0%';
    
    // 重新显示进度条和百分比文本（为下次使用做准备）
    if (progressBar) {
        progressBar.style.display = 'block';
    }
    if (progressText) {
        progressText.style.display = 'block';
    }
}

// 全选视频文件
function selectAllVideos() {
    const videoSelect = document.getElementById('video-select');
    for (let i = 0; i < videoSelect.options.length; i++) {
        videoSelect.options[i].selected = true;
    }
    handleFolderVideoSelect();
}

// 清空所有选择
function clearAllVideos() {
    const videoSelect = document.getElementById('video-select');
    for (let i = 0; i < videoSelect.options.length; i++) {
        videoSelect.options[i].selected = false;
    }
    selectedVideoNames = [];
    updateSelectedCount();
    removeVideo();
}

// 更新选择计数显示
function updateSelectedCount() {
    const countDiv = document.getElementById('selected-count');
    const countNumber = document.getElementById('count-number');
    const selectAllBtn = document.getElementById('select-all-btn');
    const clearAllBtn = document.getElementById('clear-all-btn');
    
    if (selectedVideoNames.length > 0) {
        countDiv.style.display = 'block';
        countNumber.textContent = selectedVideoNames.length;
        clearAllBtn.style.display = 'block';
        
        // 检查是否全选
        const videoSelect = document.getElementById('video-select');
        if (selectedVideoNames.length === videoSelect.options.length) {
            selectAllBtn.innerHTML = '<i class="ri-checkbox-line"></i> 已全选';
            selectAllBtn.style.background = 'var(--success-color)';
            selectAllBtn.style.color = 'white';
            selectAllBtn.style.borderColor = 'var(--success-color)';
        } else {
            selectAllBtn.innerHTML = '<i class="ri-checkbox-multiple-line"></i> 全选';
            selectAllBtn.style.background = 'var(--background-color)';
            selectAllBtn.style.color = 'var(--text-primary)';
            selectAllBtn.style.borderColor = 'var(--border-color)';
        }
    } else {
        countDiv.style.display = 'none';
        clearAllBtn.style.display = 'none';
        selectAllBtn.innerHTML = '<i class="ri-checkbox-multiple-line"></i> 全选';
        selectAllBtn.style.background = 'var(--background-color)';
        selectAllBtn.style.color = 'var(--text-primary)';
        selectAllBtn.style.borderColor = 'var(--border-color)';
    }
}

// ======================
// AB帧融合相关功能
// ======================

// 切换AB帧融合
function toggleABFusion() {
    const enabled = document.getElementById('enable-ab-fusion').checked;
    currentSettings.abFusion.enabled = enabled;
    document.getElementById('ab-fusion-options').style.display = enabled ? 'block' : 'none';
    updateSettingsSummary();
}

// 切换B视频源类型
function toggleBVideoSource() {
    const source = document.getElementById('b-video-source').value;
    currentSettings.abFusion.bVideoSource = source;
    
    // 重置B视频路径（因为切换了源类型）
    currentSettings.abFusion.bVideoPath = null;
    
    // 隐藏所有选项
    document.getElementById('b-video-upload-section').style.display = 'none';
    document.getElementById('builtin-materials-section').style.display = 'none';
    document.getElementById('ai-generate-section').style.display = 'none';
    
    // 显示选中的选项
    if (source === 'upload') {
        document.getElementById('b-video-upload-section').style.display = 'block';
    } else if (source === 'builtin') {
        document.getElementById('builtin-materials-section').style.display = 'block';
        loadBuiltinMaterials();
    } else if (source === 'generate') {
        document.getElementById('ai-generate-section').style.display = 'block';
    }
    
    updateABFusion();
}

// 处理B视频文件选择
function handleBVideoSelect(input) {
    const file = input.files[0];
    if (!file) return;
    
    // 创建FormData上传文件
    const formData = new FormData();
    formData.append('file', file);
    
    // 显示上传状态
    const statusDiv = document.getElementById('selected-b-video');
    statusDiv.style.display = 'block';
    document.getElementById('b-video-name').textContent = '上传中...';
    
    fetch('/api/video/upload_b_video', {
        method: 'POST',
        body: formData
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            currentSettings.abFusion.bVideoPath = data.file_path;
            document.getElementById('b-video-name').textContent = data.filename;
            updateABFusion();
        } else {
            alert('B视频上传失败: ' + data.error);
            removeBVideo();
        }
    })
    .catch(error => {
        alert('B视频上传失败: ' + error.message);
        removeBVideo();
    });
}

// 移除B视频
function removeBVideo() {
    currentSettings.abFusion.bVideoPath = null;
    document.getElementById('selected-b-video').style.display = 'none';
    document.getElementById('b-video-file').value = '';
    updateABFusion();
}

// 加载内置素材库
function loadBuiltinMaterials() {
    fetch('/api/video/builtin_materials')
    .then(response => response.json())
    .then(data => {
        const select = document.getElementById('builtin-material');
        select.innerHTML = '<option value="">选择内置素材</option>';
        
        if (data.materials) {
            data.materials.forEach(material => {
                const option = document.createElement('option');
                option.value = material.path;
                option.textContent = material.name;
                select.appendChild(option);
            });
        }
    })
    .catch(error => {
        console.error('加载内置素材失败:', error);
    });
}

// 生成B视频
function generateBVideo() {
    const type = document.getElementById('ai-generate-type').value;
    const duration = 10; // 默认10秒
    
    // 显示生成状态
    const button = document.querySelector('.generate-btn');
    const originalText = button.innerHTML;
    button.innerHTML = '<i class="ri-loader-4-line"></i> 生成中...';
    button.disabled = true;
    
    fetch('/api/video/generate_b_video', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            type: type,
            duration: duration
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            currentSettings.abFusion.bVideoPath = data.file_path;
            alert('B视频生成成功: ' + data.filename);
            updateABFusion();
        } else {
            alert('B视频生成失败: ' + data.error);
        }
    })
    .catch(error => {
        alert('B视频生成失败: ' + error.message);
    })
    .finally(() => {
        button.innerHTML = originalText;
        button.disabled = false;
    });
}

// 更新AB帧融合设置
function updateABFusion() {
    if (!currentSettings.abFusion.enabled) return;
    
    // 根据不同的B视频源类型设置路径
    if (currentSettings.abFusion.bVideoSource === 'builtin') {
        // 内置素材
        const builtinMaterial = document.getElementById('builtin-material').value;
        console.log('内置素材选择值:', builtinMaterial); // 调试日志
        if (builtinMaterial) {
            currentSettings.abFusion.bVideoPath = builtinMaterial;
            currentSettings.abFusion.builtinMaterial = builtinMaterial;
            console.log('设置内置素材路径:', builtinMaterial); // 调试日志
        } else {
            currentSettings.abFusion.bVideoPath = null;
            currentSettings.abFusion.builtinMaterial = '';
            console.log('内置素材未选择'); // 调试日志
        }
    } else if (currentSettings.abFusion.bVideoSource === 'generate') {
        // AI生成的视频路径已经在generateBVideo函数中设置
        currentSettings.abFusion.builtinMaterial = '';
    } else if (currentSettings.abFusion.bVideoSource === 'upload') {
        // 上传的视频路径已经在handleBVideoSelect函数中设置
        currentSettings.abFusion.builtinMaterial = '';
    }
    
    // 更新融合方案
    const method = document.getElementById('fusion-method').value;
    currentSettings.abFusion.method = method;
    
    // 隐藏所有设置
    document.getElementById('transparency-settings').style.display = 'none';
    document.getElementById('region-settings').style.display = 'none';
    document.getElementById('dynamic-settings').style.display = 'none';
    
    // 显示对应的设置
    if (method === 'transparency') {
        document.getElementById('transparency-settings').style.display = 'block';
        updateTransparencySettings();
    } else if (method === 'region') {
        document.getElementById('region-settings').style.display = 'block';
        updateRegionSettings();
    } else if (method === 'dynamic') {
        document.getElementById('dynamic-settings').style.display = 'block';
        updateDynamicSettings();
    }
    
    // 更新其他设置
    updateAdvancedOptions();
    updateSettingsSummary();
}

// 更新透明度混合设置
function updateTransparencySettings() {
    const opacity = parseFloat(document.getElementById('b-video-opacity').value);
    const adaptive = document.getElementById('adaptive-opacity').checked;
    
    currentSettings.abFusion.opacity = opacity;
    currentSettings.abFusion.adaptiveOpacity = adaptive;
    
    document.getElementById('opacity-value').textContent = Math.round(opacity * 100) + '%';
}

// 更新区域替换设置
function updateRegionSettings() {
    const region = document.querySelector('input[name="region"]:checked').value;
    const ratio = parseFloat(document.getElementById('region-ratio').value);
    
    currentSettings.abFusion.region = region;
    currentSettings.abFusion.regionRatio = ratio;
    
    document.getElementById('region-ratio-value').textContent = Math.round(ratio * 100) + '%';
}

// 更新动态混合设置
function updateDynamicSettings() {
    const cycle = parseInt(document.getElementById('dynamic-cycle').value);
    const opacityMin = parseFloat(document.getElementById('opacity-min').value);
    const opacityMax = parseFloat(document.getElementById('opacity-max').value);
    
    currentSettings.abFusion.cycle = cycle;
    currentSettings.abFusion.opacityMin = opacityMin;
    currentSettings.abFusion.opacityMax = opacityMax;
}

// 更新高级选项
function updateAdvancedOptions() {
    currentSettings.abFusion.metadataDisguise = document.getElementById('metadata-disguise').checked;
    currentSettings.abFusion.audioPhaseAdjust = document.getElementById('audio-phase-adjust').checked;
    currentSettings.abFusion.keyframeModify = document.getElementById('keyframe-modify').checked;
}

// 应用平台预设
function applyPreset(platform) {
    switch(platform) {
        case 'douyin':
            // 抖音优化预设
            currentSettings.abFusion.method = 'dynamic';
            currentSettings.abFusion.cycle = 4;
            currentSettings.abFusion.audioPhaseAdjust = true;
            currentSettings.abFusion.keyframeModify = true;
            document.getElementById('fusion-method').value = 'dynamic';
            break;
            
        case 'youtube':
            // YouTube优化预设
            currentSettings.abFusion.method = 'region';
            currentSettings.abFusion.region = 'edges';
            currentSettings.abFusion.regionRatio = 0.15;
            currentSettings.abFusion.metadataDisguise = true;
            document.getElementById('fusion-method').value = 'region';
            break;
            
        case 'kuaishou':
            // 快手优化预设
            currentSettings.abFusion.method = 'transparency';
            currentSettings.abFusion.opacity = 0.3;
            currentSettings.abFusion.adaptiveOpacity = true;
            document.getElementById('fusion-method').value = 'transparency';
            break;
    }
    
    updateABFusion();
    alert(`已应用${platform}优化预设`);
}

// 初始化设置
function initializeSettings() {
    // 初始化设置
}

// 创建新任务并加入任务列表
function createVideoTask(videoName, taskParams) {
    const taskId = 'task_' + Date.now() + '_' + Math.floor(Math.random() * 1000);
    const newTask = {
        id: taskId,
        name: videoName,
        status: 'pending', // pending, processing, completed, failed
        progress: 0,
        params: taskParams,
        created: new Date(),
        result: null,
        error: null
    };
    
    tasksList.push(newTask);
    renderTasksList();
    return taskId;
}

// 批量创建任务
function createBatchVideoTasks(videos, commonParams) {
    // 清除任务列表中已完成或失败的任务
    cleanCompletedTasks();
    
    const taskIds = [];
    videos.forEach(video => {
        const videoName = typeof video === 'string' ? video : video.name || video.filename || '未命名视频';
        const taskId = createVideoTask(videoName, {
            ...commonParams,
            video: video
        });
        taskIds.push(taskId);
    });
    
    // 如果没有正在处理的任务，开始处理队列中第一个任务
    if (!processingTaskId && taskIds.length > 0) {
        processNextTask();
    }
    
    return taskIds;
}

// 渲染任务列表
function renderTasksList() {
    const taskListContainer = document.getElementById('task-list-container');
    const taskList = document.getElementById('task-list');
    const emptyTaskList = document.getElementById('empty-task-list');
    
    if (tasksList.length === 0) {
        emptyTaskList.style.display = 'flex';
        taskList.innerHTML = '';
        return;
    }
    
    emptyTaskList.style.display = 'none';
    taskList.innerHTML = '';
    
    tasksList.forEach(task => {
        const taskItem = document.createElement('div');
        taskItem.className = `task-item ${task.status}`;
        taskItem.id = `task-${task.id}`;
        
        // 获取人类可读的状态文本
        const statusText = getStatusText(task.status);
        
        // 构建任务项HTML
        let taskHTML = `
            <div class="task-header">
                <div class="task-name">${task.name}</div>
                <span class="task-status ${task.status}">${statusText}</span>
            </div>
        `;
        
        // 如果正在处理或等待处理，添加进度条
        if (task.status === 'processing' || task.status === 'pending') {
            taskHTML += `
                <div class="task-progress">
                    <div class="task-progress-bar">
                        <div class="task-progress-fill" style="width: ${task.progress}%"></div>
                    </div>
                    <div class="task-progress-text">${task.progress}%</div>
                </div>
            `;
        }
        
        // 添加创建时间信息
        taskHTML += `
            <div class="task-info">
                创建时间: ${formatTaskTime(task.created)}
            </div>
        `;
        
        // 如果有错误信息，显示错误
        if (task.error) {
            taskHTML += `
                <div class="task-error">
                    错误: ${task.error}
                </div>
            `;
        }
        
        // 添加任务操作按钮
        taskHTML += `<div class="task-actions">`;
        
        // 如果处理完成，显示下载按钮
        if (task.status === 'completed' && task.result && task.result.output_file) {
            const filename = task.result.output_file.split('/').pop();
            taskHTML += `
                <button class="task-action-btn download" onclick="downloadProcessedVideo('${task.result.output_file}', '${filename}')">
                    <i class="ri-download-line"></i> 下载
                </button>
            `;
        }
        
        // 如果正在处理，显示取消按钮
        if (task.status === 'processing') {
            taskHTML += `
                <button class="task-action-btn cancel" onclick="cancelTask('${task.id}')">
                    <i class="ri-close-circle-line"></i> 取消
                </button>
            `;
        }
        
        // 如果已完成或失败，显示删除按钮
        if (task.status === 'completed' || task.status === 'failed') {
            taskHTML += `
                <button class="task-action-btn" onclick="removeTask('${task.id}')">
                    <i class="ri-delete-bin-line"></i> 删除
                </button>
            `;
        }
        
        taskHTML += `</div>`;
        
        taskItem.innerHTML = taskHTML;
        taskList.appendChild(taskItem);
    });
    
    // 不再自动滚动到最新任务，保持用户当前的滚动位置
}

// 获取任务状态文本
function getStatusText(status) {
    const statusMap = {
        'pending': '等待处理',
        'processing': '处理中',
        'completed': '已完成',
        'failed': '处理失败'
    };
    return statusMap[status] || '未知状态';
}

// 格式化任务时间
function formatTaskTime(date) {
    if (!date) return '-';
    const d = new Date(date);
    return d.toLocaleString('zh-CN', {
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    });
}

// 更新任务状态
function updateTaskStatus(taskId, status, progress = null, result = null, error = null) {
    const taskIndex = tasksList.findIndex(t => t.id === taskId);
    if (taskIndex === -1) return false;
    
    const task = tasksList[taskIndex];
    
    // 更新任务状态
    task.status = status;
    
    // 如果提供了进度，更新进度
    if (progress !== null) {
        task.progress = progress;
    }
    
    // 如果提供了结果，更新结果
    if (result !== null) {
        task.result = result;
    }
    
    // 如果提供了错误，更新错误
    if (error !== null) {
        task.error = error;
    }
    
    // 如果任务完成或失败，重置当前处理的任务ID
    if (status === 'completed' || status === 'failed') {
        if (processingTaskId === taskId) {
            processingTaskId = null;
            // 处理下一个任务
            setTimeout(() => {
                processNextTask();
            }, 500);
        }
    }
    
    // 重新渲染任务列表
    renderTasksList();
    return true;
}

// 处理下一个待处理的任务
function processNextTask() {
    // 如果已有正在处理的任务，不处理新任务
    if (processingTaskId) return;
    
    // 查找第一个待处理的任务
    const pendingTask = tasksList.find(task => task.status === 'pending');
    if (!pendingTask) return;
    
    // 设置当前处理的任务ID
    processingTaskId = pendingTask.id;
    
    // 更新任务状态为处理中
    updateTaskStatus(pendingTask.id, 'processing', 0);
    
    // 根据任务参数处理视频
    processTaskVideo(pendingTask);
}

// 处理任务视频
async function processTaskVideo(task) {
    const params = task.params;
    if (!params) {
        updateTaskStatus(task.id, 'failed', 100, null, '任务参数无效');
        return;
    }
    
    try {
        // 模拟进度更新
        const progressInterval = setInterval(() => {
            const currentProgress = task.progress;
            if (currentProgress < 90) {
                const newProgress = Math.min(currentProgress + Math.random() * 10, 90);
                updateTaskStatus(task.id, 'processing', Math.round(newProgress));
            }
        }, 500);
        
        // 发送请求到后端
        let response;
        let requestData;
        
        if (params.sourceType === 'upload') {
            // 文件上传模式
            const formData = new FormData();
            formData.append('video', params.video);
            formData.append('settings', JSON.stringify(params.settings));
            
            response = await fetch('/api/video/process', {
                method: 'POST',
                body: formData
            });
        } else {
            // 文件夹选择模式
            if (params.folder === '__all__') {
                // 处理全选所有文件夹的情况
                const videoData = JSON.parse(params.video);
                requestData = {
                    all_folders: true,
                    videos: [{
                        folder: videoData.folder,
                        filename: videoData.name
                    }],
                    settings: params.settings
                };
            } else {
                // 原有逻辑 - 单个文件夹
                requestData = {
                    folder_name: params.folder,
                    video_filenames: [params.video],
                    settings: params.settings
                };
            }
            
            response = await fetch('/api/video/process', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(requestData)
            });
        }
        
        clearInterval(progressInterval);
        
        const result = await response.json();
        
        if (response.ok && result.success) {
            // 更新任务状态为完成
            updateTaskStatus(task.id, 'completed', 100, result);
        } else {
            // 更新任务状态为失败
            const errorMsg = result.error || '处理失败';
            updateTaskStatus(task.id, 'failed', 100, null, errorMsg);
        }
    } catch (error) {
        console.error('处理视频任务失败:', error);
        updateTaskStatus(task.id, 'failed', 100, null, error.message);
    }
}

// 取消任务
function cancelTask(taskId) {
    const taskIndex = tasksList.findIndex(t => t.id === taskId);
    if (taskIndex === -1) return;
    
    const task = tasksList[taskIndex];
    
    // 如果任务正在处理中，尝试取消处理
    if (task.status === 'processing') {
        // TODO: 添加向后端发送取消请求的代码
        
        // 更新任务状态为失败
        updateTaskStatus(taskId, 'failed', 100, null, '任务已取消');
        
        // 如果是当前正在处理的任务，重置处理任务ID
        if (processingTaskId === taskId) {
            processingTaskId = null;
            
            // 处理下一个任务
            processNextTask();
        }
    }
}

// 从列表中删除任务
function removeTask(taskId) {
    const taskIndex = tasksList.findIndex(t => t.id === taskId);
    if (taskIndex === -1) return;
    
    // 如果是当前正在处理的任务，不允许删除
    if (processingTaskId === taskId) {
        alert('正在处理的任务不能删除');
        return;
    }
    
    // 从列表中删除任务
    tasksList.splice(taskIndex, 1);
    
    // 重新渲染任务列表
    renderTasksList();
}

// 清除已完成和失败的任务
function cleanCompletedTasks() {
    // 过滤保留待处理和处理中的任务
    tasksList = tasksList.filter(task => 
        task.status === 'pending' || 
        task.status === 'processing'
    );
    
    // 重新渲染任务列表
    renderTasksList();
}

// 批量取消所有待处理任务
function cancelAllPendingTasks() {
    // 找出所有待处理状态的任务
    const pendingTasks = tasksList.filter(task => task.status === 'pending');
    
    if (pendingTasks.length === 0) {
        // 如果没有待处理任务，显示提示
        alert('没有待处理的任务可取消');
        return;
    }
    
    // 确认是否取消
    if (!confirm(`确定要取消 ${pendingTasks.length} 个待处理任务吗？`)) {
        return;
    }
    
    let canceledCount = 0;
    
    // 遍历待处理任务并取消
    pendingTasks.forEach(task => {
        // 更新任务状态为已取消
        updateTaskStatus(task.id, 'failed', 0, null, '任务已批量取消');
        canceledCount++;
    });
    
    // 显示成功提示
    alert(`已成功取消 ${canceledCount} 个待处理任务`);
    
    // 如果当前没有正在处理的任务但队列中可能还有待处理任务，尝试开始处理下一个任务
    if (!processingTaskId) {
        setTimeout(() => {
            processNextTask();
        }, 500);
    }
}