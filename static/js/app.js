document.addEventListener('DOMContentLoaded', function() {
    // 初始化变量
    const selectedVideos = [];
    
    // 失效cookie跟踪
    const expiredCookies = new Set();
    
    // Cookie手动选择保护机制
    let lastCookieManualSelection = 0;
    const COOKIE_SELECTION_PROTECTION_TIME = 30000; // 30秒内不自动刷新
    
    // 路径格式化函数 - 将路径统一为正斜杠格式
    function normalizePath(path) {
        if (typeof path !== 'string') return path;
        return path.replace(/\\/g, '/');
    }
    
    // 获取DOM元素
    const cookieNameInput = document.getElementById('cookie-name');
    const generateCookieBtn = document.getElementById('generate-cookie');
    const cookieSelect = document.getElementById('cookie-select');
    const videoTreeDiv = document.getElementById('video-tree');
    const selectedVideosList = document.getElementById('selected-videos-list');
    const locationInput = document.getElementById('location');
    const uploadIntervalInput = document.getElementById('upload-interval');
    const publishNowRadio = document.getElementById('publish-now');
    const publishScheduleRadio = document.getElementById('publish-schedule');
    const scheduleContainer = document.getElementById('schedule-container');
    const publishDateInput = document.getElementById('publish-date');
    const publishHourSelect = document.getElementById('publish-hour');
    const publishMinuteSelect = document.getElementById('publish-minute');
    const startUploadBtn = document.getElementById('start-upload');
    const uploadStatus = document.getElementById('upload-status');
    const uploadTasks = document.getElementById('upload-tasks');
    const countdownContainer = document.getElementById('countdown-container');
    const countdownTimer = document.getElementById('countdown-timer');
    const deleteCookieBtn = document.getElementById('delete-cookie');
    const selectedCookieIndicator = document.getElementById('selected-cookie-indicator');
    const selectedCookieName = document.getElementById('selected-cookie-name');
    
    // 浏览器视图模态框元素
    const browserViewModal = document.getElementById('browser-view-modal');
    const closeBrowserViewBtn = document.getElementById('close-browser-view');
    const browserStatus = document.getElementById('browser-status');
    const browserScreenshot = document.getElementById('browser-screenshot');
    const screenshotOverlay = document.getElementById('screenshot-overlay');
    const refreshScreenshotBtn = document.getElementById('refresh-screenshot');
    const screenshotTimestamp = document.getElementById('screenshot-timestamp');
    
    // 缩放和平移控制元素
    const zoomInBtn = document.getElementById('zoom-in');
    const zoomOutBtn = document.getElementById('zoom-out');
    const zoomResetBtn = document.getElementById('zoom-reset');
    const panResetBtn = document.getElementById('pan-reset');
    const zoomLevelSpan = document.getElementById('zoom-level');
    const screenshotViewport = document.getElementById('screenshot-viewport');
    
    // 键盘输入控制元素
    const textInput = document.getElementById('text-input');
    const sendTextBtn = document.getElementById('send-text');
    const clearInputBtn = document.getElementById('clear-input');
    const keyButtons = document.querySelectorAll('.key-btn');
    
    // 代理管理元素
    const addProxyBtn = document.getElementById('add-proxy-btn');
    
    // WebSocket和浏览器视图相关变量
    let socket = null;
    let currentBrowserSession = null;
    
    // 缩放和平移相关变量
    let currentZoom = 1.0;
    let isDragging = false;
    let dragStart = { x: 0, y: 0 };
    let scrollStart = { x: 0, y: 0 };
    
    // 暴露变量到全局作用域以便调试
    window.currentBrowserSession = () => currentBrowserSession;
    window.setCurrentBrowserSession = (sessionId) => {
        currentBrowserSession = sessionId;
        console.log("✅ 设置浏览器会话ID:", sessionId);
    };
    
    // 倒计时相关变量
    let countdownInterval = null;
    let countdownEndTime = null;
    
    // 初始化WebSocket连接
    initWebSocket();
    
    // 初始化小时和分钟下拉选择器
    initTimeSelectors();
    
    // 初始化日期选择器为今天
    const today = new Date();
    const formattedDate = today.toISOString().split('T')[0];
    publishDateInput.value = formattedDate;
    
    // 加载Cookie列表
    loadCookies();
    
    // 加载视频列表
    loadVideos();
    
    // 初始化选择指示器
    updateSelectedCookieIndicator();
    
    // 加载代理管理数据
    loadProxies();
    loadProxyAssignments();
    
    // 加载浏览器指纹数据
    loadFingerprints();
    
    // 检查是否有下载任务在进行中(刷新页面后恢复状态)
    checkDownloadStatus();
    
    // 设置事件监听器
    generateCookieBtn.addEventListener('click', generateCookie);
    deleteCookieBtn.addEventListener('click', deleteCookie);
    // cookieSelect事件监听器已在文件后面添加，带有手动选择保护机制
    publishNowRadio.addEventListener('change', toggleScheduleOptions);
    publishScheduleRadio.addEventListener('change', toggleScheduleOptions);
    startUploadBtn.addEventListener('click', startUpload);
    
    // 浏览器视图事件
    closeBrowserViewBtn.addEventListener('click', closeBrowserView);
    refreshScreenshotBtn.addEventListener('click', requestBrowserView);
    
    // 代理管理事件
    addProxyBtn.addEventListener('click', addProxy);
    
    // 定期刷新上传状态
    setInterval(refreshUploadStatus, 3000);
    
    // 初始化时间选择器
    function initTimeSelectors() {
        // 填充小时选择器 (00-23)
        for (let i = 0; i < 24; i++) {
            const option = document.createElement('option');
            option.value = i.toString().padStart(2, '0');
            option.textContent = i.toString().padStart(2, '0');
            publishHourSelect.appendChild(option);
        }
        
        // 填充分钟选择器 (00-59)
        for (let i = 0; i < 60; i++) {
            const option = document.createElement('option');
            option.value = i.toString().padStart(2, '0');
            option.textContent = i.toString().padStart(2, '0');
            publishMinuteSelect.appendChild(option);
        }
    }
    
    // 切换定时发布选项
    function toggleScheduleOptions() {
        if (publishScheduleRadio.checked) {
            scheduleContainer.classList.remove('hidden');
        } else {
            scheduleContainer.classList.add('hidden');
        }
    }
    
    // 加载Cookie列表
    function loadCookies() {
        // 保存当前选中的cookie和选中索引
        const currentSelected = cookieSelect.value;
        const currentSelectedIndex = cookieSelect.selectedIndex;
        
        // 如果用户正在操作下拉框，延迟刷新
        if (document.querySelector('#cookie-select:focus')) {
            console.log('用户正在操作Cookie选择器，跳过刷新');
            return;
        }
        
        // 如果用户刚刚手动选择了Cookie，在保护时间内不自动刷新
        const now = Date.now();
        if (now - lastCookieManualSelection < COOKIE_SELECTION_PROTECTION_TIME) {
            console.log('Cookie手动选择保护期内，跳过刷新');
            return;
        }
        
        fetch('/api/cookies')
            .then(response => response.json())
            .then(data => {
                const cookies = data.cookies || [];
                // 如果Cookie列表没有变化，则不需要重新构建DOM
                const currentOptions = Array.from(cookieSelect.options).map(opt => opt.value).filter(val => val);
                const cookieFilenames = cookies.map(c => c.filename);
                const cookiesChanged = JSON.stringify(currentOptions.sort()) !== JSON.stringify(cookieFilenames.sort());
                
                if (!cookiesChanged && currentSelected) {
                    console.log('Cookie列表未变化，保持当前选择');
                    return;
                }
                
                cookieSelect.innerHTML = '';
                
                if (cookies.length === 0) {
                    const option = document.createElement('option');
                    option.textContent = '无可用Cookie';
                    option.disabled = true;
                    cookieSelect.appendChild(option);
                } else {
                    cookies.forEach(cookie => {
                        const option = document.createElement('option');
                        option.value = cookie.filename;
                        
                        // 如果cookie失效，添加失效标记
                        if (expiredCookies.has(cookie.filename) || cookie.expired) {
                            option.textContent = `${cookie.name} (失效)`;
                            option.style.color = '#ff4444';
                            option.style.fontStyle = 'italic';
                        } else {
                            option.textContent = cookie.name;
                        }
                        
                        cookieSelect.appendChild(option);
                    });
                    
                    // 优先恢复之前选中的cookie
                    const cookieFilenames = cookies.map(c => c.filename);
                    if (currentSelected && cookieFilenames.includes(currentSelected)) {
                        cookieSelect.value = currentSelected;
                        console.log('恢复之前选中的Cookie:', currentSelected);
                    } else if (currentSelectedIndex >= 0 && currentSelectedIndex < cookies.length) {
                        // 如果之前的Cookie不存在，尝试保持相同的索引位置
                        cookieSelect.selectedIndex = currentSelectedIndex;
                        console.log('按索引恢复Cookie选择:', currentSelectedIndex);
                    } else if (cookies.length > 0) {
                        // 最后选择第一个
                        cookieSelect.selectedIndex = 0;
                        console.log('默认选择第一个Cookie');
                    }
                    
                    // 更新选择指示器
                    updateSelectedCookieIndicator();
                }
            })
            .catch(error => {
                console.error('加载Cookie列表失败:', error);
                // 静默失败，不要弹窗打断用户操作
                console.log('Cookie列表加载失败，将在下次定时刷新时重试');
            });
    }
    
    // 更新选中Cookie指示器
    function updateSelectedCookieIndicator() {
        const selectedValue = cookieSelect.value;
        
        if (selectedValue && selectedValue !== '无可用Cookie') {
            selectedCookieIndicator.classList.remove('hidden');
            
            // 如果cookie失效，添加失效标记
            if (expiredCookies.has(selectedValue)) {
                selectedCookieName.textContent = `${selectedValue} (失效)`;
                selectedCookieName.style.color = '#ff4444';
                selectedCookieName.style.fontStyle = 'italic';
            } else {
            selectedCookieName.textContent = selectedValue;
                selectedCookieName.style.color = '';
                selectedCookieName.style.fontStyle = '';
            }
        } else {
            selectedCookieIndicator.classList.add('hidden');
            selectedCookieName.textContent = '未选择';
            selectedCookieName.style.color = '';
            selectedCookieName.style.fontStyle = '';
        }
    }
    
    // 生成新的Cookie
    function generateCookie() {
        const cookieName = cookieNameInput.value.trim();
        
        if (!cookieName) {
            alert('请输入Cookie名称');
            return;
        }
        
        // 获取选中的代理
        const cookieProxySelect = document.getElementById('cookie-proxy-select');
        const selectedProxy = cookieProxySelect.value;
        
        generateCookieBtn.disabled = true;
        generateCookieBtn.textContent = '生成中...';
        
        const requestData = { name: cookieName };
        if (selectedProxy) {
            requestData.proxy_id = parseInt(selectedProxy);
            console.log('使用代理生成Cookie:', selectedProxy);
        }
        
        fetch('/api/generate_cookie', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(requestData)
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                // 获取会话ID并显示浏览器视图
                currentBrowserSession = data.session_id;
                console.log("📋 生成Cookie成功，会话ID:", currentBrowserSession);
                showBrowserView();
                
                // 清除对应cookie的失效状态（如果存在）
                const cookieFilename = cookieName + '.json';
                if (expiredCookies.has(cookieFilename)) {
                    expiredCookies.delete(cookieFilename);
                }
                
                // 延迟刷新Cookie列表和相关数据
                setTimeout(() => {
                    loadCookies();
                    loadTaskCookieOptions(); // 刷新任务Cookie选项
                    loadFingerprints(); // 刷新指纹数据
                }, 5000);
                
                alert('Cookie生成已开始，请在浏览器视图中完成登录');
            } else {
                alert('生成Cookie失败: ' + data.message);
            }
        })
        .catch(error => {
            console.error('生成Cookie请求失败:', error);
            alert('生成Cookie请求失败，请重试');
        })
        .finally(() => {
            generateCookieBtn.disabled = false;
            generateCookieBtn.textContent = '生成新Cookie';
            cookieNameInput.value = '';
        });
    }
    
    // 删除选中的Cookie
    function deleteCookie() {
        const selectedCookie = cookieSelect.value;
        
        if (!selectedCookie) {
            alert('请先选择要删除的Cookie文件');
            return;
        }
        
        // 确认删除
        if (!confirm(`确定要删除Cookie文件 "${selectedCookie}" 吗？此操作不可撤销。`)) {
            return;
        }
        
        deleteCookieBtn.disabled = true;
        deleteCookieBtn.textContent = '删除中...';
        
        fetch('/api/delete_cookie', {
            method: 'DELETE',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ cookie_file: selectedCookie })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                alert('Cookie文件删除成功');
                loadCookies(); // 刷新Cookie列表
                loadTaskCookieOptions(); // 刷新任务Cookie选项
                loadProxyAssignments(); // 刷新代理分配列表
                loadFingerprints(); // 刷新指纹数据
                // 同时刷新历史记录中的cookie列表
                if (typeof loadHistoryCookies === 'function') {
                    loadHistoryCookies();
                }
            } else {
                alert('删除Cookie失败: ' + data.message);
            }
        })
        .catch(error => {
            console.error('删除Cookie请求失败:', error);
            alert('删除Cookie请求失败，请重试');
        })
        .finally(() => {
            deleteCookieBtn.disabled = false;
            deleteCookieBtn.innerHTML = '<i class="ri-delete-bin-line"></i> 删除选中Cookie';
        });
    }
    
    // 加载视频列表
    function loadVideos() {
        fetch('/api/videos')
            .then(response => response.json())
            .then(videos => {
                videoTreeDiv.innerHTML = '';
                
                if (videos.length === 0) {
                    videoTreeDiv.textContent = '视频文件夹为空';
                } else {
                    renderVideoTree(videos, videoTreeDiv, '');
                }
            })
            .catch(error => {
                console.error('加载视频列表失败:', error);
                videoTreeDiv.textContent = '加载视频列表失败，请刷新页面重试';
            });
    }
    
    // 渲染视频树
    function renderVideoTree(items, container, parentPath) {
        items.forEach(item => {
            const itemElement = document.createElement('div');
            const fullPath = normalizePath(item.path);
            
            if (item.type === 'folder') {
                itemElement.className = 'folder-item';
                itemElement.innerHTML = `<i class="ri-folder-line"></i> ${item.name}`;
                
                const childrenContainer = document.createElement('div');
                childrenContainer.style.paddingLeft = '20px';
                childrenContainer.style.display = 'none';
                
                // 添加右键菜单支持
                itemElement.addEventListener('contextmenu', function(event) {
                    event.preventDefault();
                    event.stopPropagation();
                    showFolderContextMenu(event, fullPath, item.name);
                });
                
                itemElement.addEventListener('click', function(event) {
                    event.stopPropagation();
                    // 切换文件夹图标
                    if (childrenContainer.style.display === 'none') {
                        itemElement.innerHTML = `<i class="ri-folder-open-line"></i> ${item.name}`;
                    } else {
                        itemElement.innerHTML = `<i class="ri-folder-line"></i> ${item.name}`;
                    }
                    childrenContainer.style.display = childrenContainer.style.display === 'none' ? 'block' : 'none';
                });
                
                renderVideoTree(item.children, childrenContainer, fullPath);
                
                container.appendChild(itemElement);
                container.appendChild(childrenContainer);
            } else {
                itemElement.className = 'file-item';
                itemElement.innerHTML = `<i class="ri-film-line"></i> ${item.name}`;
                itemElement.addEventListener('click', function() {
                    toggleSelectVideo(fullPath, item.name);
                });
                
                // 添加文件右键菜单支持
                itemElement.addEventListener('contextmenu', function(event) {
                    event.preventDefault();
                    event.stopPropagation();
                    showFileContextMenu(event, fullPath, item.name);
                });
                
                // 如果视频已选中，添加选中标记
                if (selectedVideos.find(v => normalizePath(v.path) === fullPath)) {
                    itemElement.style.color = '#ff0050';
                    itemElement.innerHTML = `<i class="ri-checkbox-circle-line"></i> ${item.name}`;
                }
                
                container.appendChild(itemElement);
            }
        });
    }
    
    // 切换选择视频
    function toggleSelectVideo(path, name) {
        const normalizedPath = normalizePath(path);  // 修复路径格式
        const index = selectedVideos.findIndex(v => normalizePath(v.path) === normalizedPath);
        
        if (index === -1) {
            // 添加到选中列表
            selectedVideos.push({ path: normalizedPath, name });
        } else {
            // 从选中列表移除
            selectedVideos.splice(index, 1);
        }
        
        // 刷新选中视频列表
        updateSelectedVideosList();
        // 刷新视频树
        loadVideos();
    }
    
    // 更新选中视频列表
    function updateSelectedVideosList() {
        selectedVideosList.innerHTML = '';
        
        if (selectedVideos.length === 0) {
            const li = document.createElement('li');
            li.innerHTML = '<i class="ri-information-line"></i> 未选择视频';
            selectedVideosList.appendChild(li);
            return;
        }
        
        selectedVideos.forEach((video, index) => {
            const li = document.createElement('li');
            li.innerHTML = `<i class="ri-film-line"></i> <span>${video.name}</span>`;
            
            const removeBtn = document.createElement('button');
            removeBtn.innerHTML = '<i class="ri-delete-bin-line"></i> 移除';
            removeBtn.style.padding = '4px 8px';
            removeBtn.style.fontSize = '12px';
            
            removeBtn.addEventListener('click', function() {
                selectedVideos.splice(index, 1);
                updateSelectedVideosList();
                loadVideos();
            });
            
            li.appendChild(removeBtn);
            selectedVideosList.appendChild(li);
        });
    }
    
    // 开始上传
    function startUpload() {
        if (selectedVideos.length === 0) {
            alert('请至少选择一个视频');
            return;
        }
        
        if (!cookieSelect.value) {
            alert('请选择一个Cookie');
            return;
        }
        
        const uploadData = {
            videos: selectedVideos.map(v => v.path),
            cookie: cookieSelect.value,
            location: locationInput.value.trim() || '杭州市',
            upload_interval: parseInt(uploadIntervalInput.value) || 5,
            publish_type: publishNowRadio.checked ? 'now' : 'schedule'
        };
        
        if (publishScheduleRadio.checked) {
            uploadData.date = publishDateInput.value;
            uploadData.hour = publishHourSelect.value;
            uploadData.minute = publishMinuteSelect.value;
        }
        
        startUploadBtn.disabled = true;
        startUploadBtn.textContent = '上传中...';
        
        fetch('/api/upload', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(uploadData)
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                alert('上传任务已开始');
                // 刷新上传状态
                refreshUploadStatus();
            } else {
                // 检查是否是cookie失效且需要跳过上传
                if (data.cookie_expired && data.skip_upload) {
                    // 将cookie标记为失效
                    expiredCookies.add(data.cookie_file);
                    
                    // 刷新cookie列表显示失效状态
                    loadCookies();
                    
                    alert(`Cookie ${data.cookie_file} 已失效，已跳过上传任务。请重新生成Cookie后再试。`);
                    
                    startUploadBtn.disabled = false;
                    startUploadBtn.textContent = '开始上传';
                } else if (data.cookie_expired && data.session_id) {
                    // 原有的cookie失效处理逻辑（如果后端返回session_id）
                    currentBrowserSession = data.session_id;
                    showBrowserView();
                    updateBrowserStatus('Cookie已失效，请重新登录', 'warning', 'ri-error-warning-line');
                } else {
                    alert('上传任务启动失败: ' + data.message);
                    startUploadBtn.disabled = false;
                    startUploadBtn.textContent = '开始上传';
                }
            }
        })
        .catch(error => {
            console.error('上传请求失败:', error);
            alert('上传请求失败，请重试');
            startUploadBtn.disabled = false;
            startUploadBtn.textContent = '开始上传';
        });
    }
    
    // 刷新上传状态
    function refreshUploadStatus() {
        fetch('/api/upload_status')
            .then(response => response.json())
            .then(data => {
                if (data.is_uploading) {
                    uploadStatus.innerHTML = '<i class="ri-loader-4-line"></i> 上传任务进行中...';
                    uploadTasks.classList.remove('hidden');
                    startUploadBtn.disabled = true;
                    startUploadBtn.innerHTML = '<i class="ri-loader-4-line"></i> 上传中...';
                    
                    // 检查是否有等待中的任务，用于显示倒计时
                    let waitingTask = null;
                    for (const task of data.tasks) {
                        if (task.status.includes('等待中')) {
                            waitingTask = task;
                            break;
                        }
                    }
                    
                    if (waitingTask) {
                        console.log("发现等待中的任务:", waitingTask.status);
                        // 解析剩余时间，处理两种可能的格式
                        // 格式1: "等待中 (剩余X分Y秒)"
                        // 格式2: "等待中 (将在X分钟后上传)"
                        let minutes = 0;
                        let seconds = 0;
                        
                        const remainingMatch = waitingTask.status.match(/剩余(\d+)分(\d+)秒/);
                        const initialMatch = waitingTask.status.match(/将在(\d+)分钟后上传/);
                        
                        if (remainingMatch) {
                            // 如果找到剩余格式
                            minutes = parseInt(remainingMatch[1]);
                            seconds = parseInt(remainingMatch[2]);
                            console.log(`解析剩余时间: ${minutes}分${seconds}秒`);
                        } else if (initialMatch) {
                            // 如果找到初始格式
                            minutes = parseInt(initialMatch[1]);
                            seconds = 0;
                            console.log(`解析初始时间: ${minutes}分钟`);
                        }
                        
                        if (minutes > 0 || seconds > 0) {
                            const totalSeconds = minutes * 60 + seconds;
                            
                            // 设置倒计时结束时间，如果倒计时时间有更新，则刷新倒计时
                            const newEndTime = new Date(new Date().getTime() + totalSeconds * 1000);
                            
                            if (!countdownEndTime || Math.abs(newEndTime - countdownEndTime) > 5000) {
                                console.log("更新倒计时时间:", totalSeconds, "秒");
                                countdownEndTime = newEndTime;
                                startCountdown();
                            }
                            
                            // 显示倒计时容器
                            countdownContainer.classList.remove('hidden');
                        }
                    } else {
                        // 没有等待中的任务，隐藏倒计时
                        countdownContainer.classList.add('hidden');
                        stopCountdown();
                    }
                    
                    // 更新任务列表
                    const tbody = uploadTasks.querySelector('tbody');
                    tbody.innerHTML = '';
                    
                    data.tasks.forEach(task => {
                        const tr = document.createElement('tr');
                        
                        const nameTd = document.createElement('td');
                        nameTd.innerHTML = `<i class="ri-file-video-line"></i> ${task.name}`;
                        
                        const statusTd = document.createElement('td');
                        statusTd.textContent = task.status;
                        
                        // 根据状态设置不同的样式
                        if (task.status.includes('上传中') || task.status.includes('处理中') || task.status.includes('进度')) {
                            statusTd.className = 'status-processing';
                            statusTd.innerHTML = `<i class="ri-loader-4-line"></i> ${task.status}`;
                        } else if (task.status.includes('完成') || task.status.includes('成功') || task.status === '上传成功') {
                            statusTd.className = 'status-success';
                            statusTd.innerHTML = `<i class="ri-check-line"></i> ${task.status}`;
                        } else if (task.status.includes('失败') || task.status.includes('错误')) {
                            statusTd.className = 'status-error';
                            statusTd.innerHTML = `<i class="ri-error-warning-line"></i> ${task.status}`;
                        } else if (task.status.includes('等待')) {
                            statusTd.className = 'status-waiting';
                            statusTd.innerHTML = `<i class="ri-time-line"></i> ${task.status}`;
                        }
                        
                        tr.appendChild(nameTd);
                        tr.appendChild(statusTd);
                        tbody.appendChild(tr);
                    });
                } else {
                    // 上传已结束，恢复按钮
                    startUploadBtn.disabled = false;
                    startUploadBtn.innerHTML = '<i class="ri-upload-cloud-line"></i> 开始上传';
                    
                    if (data.tasks.length === 0) {
                        uploadStatus.innerHTML = '<i class="ri-information-line"></i> 未开始上传';
                        uploadTasks.classList.add('hidden');
                        countdownContainer.classList.add('hidden');
                        stopCountdown();
                    } else {
                        uploadStatus.innerHTML = '<i class="ri-check-double-line"></i> 上传任务已完成';
                        
                        // 隐藏倒计时
                        countdownContainer.classList.add('hidden');
                        stopCountdown();
                        
                        // 保持任务表格可见，即使上传已完成
                        uploadTasks.classList.remove('hidden');
                        
                        // 检查是否所有任务都成功，只有全部成功才清空选择列表
                        const allTasksSuccessful = data.tasks.every(task => 
                            task.status.includes('完成') || task.status.includes('成功') || task.status === '上传成功'
                        );
                        
                        if (allTasksSuccessful && data.tasks.length > 0) {
                            // 只有在所有任务都成功时才清空选中的视频列表
                            selectedVideos.length = 0; // 清空数组但保持引用
                            updateSelectedVideosList();
                            loadVideos(); // 刷新视频树显示
                        } else {
                            // 如果有失败的任务，保持选择状态，只刷新视频树以更新显示状态
                            loadVideos(); // 刷新视频树显示但保持选择状态
                        }
                        
                        // 更新任务列表，显示最终状态
                        const tbody = uploadTasks.querySelector('tbody');
                        tbody.innerHTML = '';
                        
                        data.tasks.forEach(task => {
                            const tr = document.createElement('tr');
                            
                            const nameTd = document.createElement('td');
                            nameTd.innerHTML = `<i class="ri-file-video-line"></i> ${task.name}`;
                            
                            const statusTd = document.createElement('td');
                            statusTd.textContent = task.status;
                            
                            // 根据状态设置不同的样式
                            if (task.status.includes('完成') || task.status.includes('成功') || task.status === '上传成功') {
                                statusTd.className = 'status-success';
                                statusTd.innerHTML = `<i class="ri-check-line"></i> ${task.status}`;
                            } else if (task.status.includes('失败') || task.status.includes('错误')) {
                                statusTd.className = 'status-error';
                                statusTd.innerHTML = `<i class="ri-error-warning-line"></i> ${task.status}`;
                            }
                            
                            tr.appendChild(nameTd);
                            tr.appendChild(statusTd);
                            tbody.appendChild(tr);
                        });
                    }
                }
            })
            .catch(error => {
                console.error('获取上传状态失败:', error);
                uploadStatus.innerHTML = '<i class="ri-error-warning-line"></i> 获取状态失败，请刷新页面';
            });
    }
    
    // 初始化调用
    updateSelectedVideosList();
    
    // 开始倒计时
    function startCountdown() {
        // 清除之前的倒计时
        stopCountdown();
        
        // 开始新的倒计时
        updateCountdown(); // 立即更新一次
        countdownInterval = setInterval(updateCountdown, 1000);
        console.log("倒计时开始，目标时间:", countdownEndTime);
    }
    
    // 停止倒计时
    function stopCountdown() {
        if (countdownInterval) {
            clearInterval(countdownInterval);
            countdownInterval = null;
            console.log("停止倒计时");
        }
        // 不清除countdownEndTime，因为它被用来检测时间变化
    }
    
    // 更新倒计时显示
    function updateCountdown() {
        if (!countdownEndTime) return;
        
        const now = new Date().getTime();
        const timeLeft = countdownEndTime - now;
        
        if (timeLeft <= 0) {
            // 倒计时结束
            countdownTimer.textContent = '00:00:00';
            console.log("倒计时结束");
            
            // 不马上停止倒计时，让下一次刷新状态来决定是否停止
            return;
        }
        
        // 计算时、分、秒
        const hours = Math.floor(timeLeft / (1000 * 60 * 60));
        const minutes = Math.floor((timeLeft % (1000 * 60 * 60)) / (1000 * 60));
        const seconds = Math.floor((timeLeft % (1000 * 60)) / 1000);
        
        // 格式化显示
        countdownTimer.textContent = 
            `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
    }
    
    // ==================== 代理管理功能 ====================
    
    // 加载代理列表
    function loadProxies() {
        fetch('/api/proxies')
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    updateProxyTable(data.proxies);
                    updateProxySelectOptions(data.proxies);
                } else {
                    console.error('加载代理列表失败:', data.message);
                }
            })
            .catch(error => {
                console.error('加载代理列表失败:', error);
            });
    }
    
    // 更新代理表格
    function updateProxyTable(proxies) {
        const tbody = document.querySelector('#proxy-table tbody');
        tbody.innerHTML = '';
        
        proxies.forEach(proxy => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td>${proxy.name}</td>
                <td>${proxy.host}:${proxy.port}</td>
                <td><span class="proxy-status ${proxy.status}">${proxy.status === 'active' ? '活跃' : '不活跃'}</span></td>
                <td>${proxy.speed_ms > 0 ? proxy.speed_ms + 'ms' : '-'}</td>
                <td class="proxy-actions">
                    <button class="test-btn" onclick="testProxy(${proxy.id})">
                        <i class="ri-pulse-line"></i> 测试
                    </button>
                    <button class="small-danger-btn" onclick="deleteProxy(${proxy.id})">
                        <i class="ri-delete-bin-line"></i> 删除
                    </button>
                </td>
            `;
            tbody.appendChild(tr);
        });
    }
    
    // 更新代理选择下拉框
    function updateProxySelectOptions(proxies) {
        // 只更新Cookie生成的代理选择框
        updateCookieProxyOptions(proxies);
    }
    
    // 更新Cookie生成时的代理选择框
    function updateCookieProxyOptions(proxies) {
        const cookieProxySelect = document.getElementById('cookie-proxy-select');
        if (!cookieProxySelect) return; // 如果元素不存在则跳过
        
        const currentValue = cookieProxySelect.value;
        
        // 清空现有选项，但保留"不使用代理"选项
        cookieProxySelect.innerHTML = '<option value="">不使用代理</option>';
        
        // 添加代理选项（只显示活跃的代理）
        proxies.filter(p => p.status === 'active').forEach(proxy => {
            const option = document.createElement('option');
            option.value = proxy.id;
            option.textContent = `${proxy.name} (${proxy.host}:${proxy.port})`;
            cookieProxySelect.appendChild(option);
        });
        
        // 恢复之前选中的值
        if (currentValue) {
            cookieProxySelect.value = currentValue;
        }
    }
    
    // 添加代理
    function addProxy() {
        const name = document.getElementById('proxy-name').value.trim();
        const host = document.getElementById('proxy-host').value.trim();
        const port = document.getElementById('proxy-port').value.trim();
        const protocol = document.getElementById('proxy-protocol').value;
        const username = document.getElementById('proxy-username').value.trim();
        const password = document.getElementById('proxy-password').value.trim();
        
        if (!name || !host || !port) {
            alert('请填写代理名称、主机地址和端口');
            return;
        }
        
        addProxyBtn.disabled = true;
        addProxyBtn.textContent = '添加中...';
        
        fetch('/api/proxies', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                name: name,
                host: host,
                port: parseInt(port),
                protocol: protocol,
                username: username || null,
                password: password || null
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                alert('代理添加成功');
                // 清空表单
                document.getElementById('proxy-name').value = '';
                document.getElementById('proxy-host').value = '';
                document.getElementById('proxy-port').value = '';
                document.getElementById('proxy-username').value = '';
                document.getElementById('proxy-password').value = '';
                // 重新加载代理列表和相关数据
                loadProxies();
                loadProxyAssignments();
            } else {
                alert('添加代理失败: ' + data.message);
            }
        })
        .catch(error => {
            console.error('添加代理失败:', error);
            alert('添加代理失败，请重试');
        })
        .finally(() => {
            addProxyBtn.disabled = false;
            addProxyBtn.innerHTML = '<i class="ri-add-line"></i> 添加代理';
        });
    }
    
    // 测试代理
    window.testProxy = function(proxyId) {
        const testBtn = event.target.closest('button');
        const originalText = testBtn.innerHTML;
        
        testBtn.disabled = true;
        testBtn.innerHTML = '<i class="ri-loader-4-line"></i> 测试中...';
        
        fetch(`/api/proxies/${proxyId}/test`, {
            method: 'POST'
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                alert(`代理测试成功\\n${data.message}\\nIP: ${data.ip_info}`);
            } else {
                alert('代理测试失败: ' + data.message);
            }
            // 重新加载代理列表以更新状态
            loadProxies();
        })
        .catch(error => {
            console.error('测试代理失败:', error);
            alert('测试代理失败，请重试');
        })
        .finally(() => {
            testBtn.disabled = false;
            testBtn.innerHTML = originalText;
        });
    };
    
    // 删除代理
    window.deleteProxy = function(proxyId) {
        if (!confirm('确定要删除这个代理吗？这将同时移除所有相关的分配关系。')) {
            return;
        }
        
        fetch(`/api/proxies/${proxyId}`, {
            method: 'DELETE'
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                alert('代理删除成功');
                loadProxies();
                loadProxyAssignments();
            } else {
                alert('删除代理失败: ' + data.message);
            }
        })
        .catch(error => {
            console.error('删除代理失败:', error);
            alert('删除代理失败，请重试');
        });
    };
    
    // 加载代理分配
    function loadProxyAssignments() {
        // 只加载分配表格，不更新选择框
        fetch('/api/proxy_mappings')
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    updateAssignmentTable(data.mappings);
                }
            })
            .catch(error => {
                console.error('加载代理分配失败:', error);
            });
    }
    
    // 更新分配表格
    function updateAssignmentTable(mappings) {
        const tbody = document.querySelector('#assignment-table tbody');
        tbody.innerHTML = '';
        
        mappings.forEach(mapping => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td>${mapping.cookie_name}</td>
                <td>${mapping.proxy_name || '未分配'}</td>
                <td><span class="proxy-status ${mapping.proxy_status || 'inactive'}">${mapping.proxy_status === 'active' ? '活跃' : '不活跃'}</span></td>
                <td>${mapping.assigned_time || '-'}</td>
            `;
            tbody.appendChild(tr);
        });
    }
    

    
    // ============ WebSocket 和浏览器视图功能 ============
    
    // 初始化WebSocket连接
    function initWebSocket() {
        if (typeof io === 'undefined') {
            console.error('Socket.IO库未加载');
            return;
        }
        
        // 配置Socket.IO连接选项
        socket = io({
            autoConnect: true,
            reconnection: true,
            reconnectionDelay: 1000,
            reconnectionDelayMax: 5000,
            maxReconnectionAttempts: 5,
            timeout: 20000,
            forceNew: false,
            transports: ['websocket', 'polling']  // 优先使用websocket，fallback到polling
        });
        
        socket.on('connect', function() {
            console.log('WebSocket连接成功');
        });
        
        socket.on('disconnect', function() {
            console.log('WebSocket连接断开');
        });
        
        socket.on('browser_status', function(data) {
            handleBrowserStatus(data);
        });
        
        socket.on('browser_screenshot', function(data) {
            handleBrowserScreenshot(data);
        });
        
        socket.on('click_received', function(data) {
            handleClickReceived(data);
        });
        
        socket.on('click_executed', function(data) {
            handleClickExecuted(data);
        });
        
        socket.on('input_received', function(data) {
            handleInputReceived(data);
        });
        
        socket.on('input_executed', function(data) {
            handleInputExecuted(data);
        });
        
        socket.on('cookie_expired', function(data) {
            console.log('收到cookie_expired事件:', data);
            handleCookieExpired(data);
        });
        
        // 视频列表加载进度事件
        socket.on('video_list_progress', function(data) {
            handleVideoListProgress(data);
        });
        
        // 权限视频列表加载进度事件
        socket.on('permission_video_list_progress', function(data) {
            handlePermissionVideoListProgress(data);
        });
        
        // 下载进度事件
        socket.on('download_progress', function(data) {
            handleDownloadProgress(data);
        });
        
        // 通用错误事件处理
        socket.on('error', function(data) {
            console.error('WebSocket错误:', data);
            if (data.message) {
                // 如果是浏览器视图相关的错误，更新状态
                if (currentBrowserSession && browserViewModal && !browserViewModal.classList.contains('hidden')) {
                    updateBrowserStatus(data.message, 'error', 'ri-error-warning-line');
                    // 显示覆盖层，提示用户重新开始
                    screenshotOverlay.classList.remove('hidden');
                } else {
                    // 其他错误显示alert
                    alert('错误: ' + data.message);
                }
            }
        });
    }
    
    // 显示浏览器视图模态框
    function showBrowserView() {
        browserViewModal.classList.remove('hidden');
        updateBrowserStatus('正在启动浏览器...', 'info');
        
        // 重置截图显示
        browserScreenshot.src = '';
        screenshotOverlay.classList.remove('hidden');
        screenshotTimestamp.textContent = '最后更新: --';
        
        // 添加点击事件监听器
        setupBrowserScreenshotClick();
    }
    
    // 关闭浏览器视图
    function closeBrowserView() {
        // 如果有活跃的浏览器会话，先通知后端关闭浏览器
        if (currentBrowserSession && socket) {
            socket.emit('close_browser', {
                session_id: currentBrowserSession
            });
            
            updateBrowserStatus('正在关闭浏览器并保存Cookie...', 'warning', 'ri-close-line');
            
            // 设置超时，防止长时间等待
            setTimeout(() => {
                if (browserViewModal && !browserViewModal.classList.contains('hidden')) {
                    browserViewModal.classList.add('hidden');
                    currentBrowserSession = null;
                    // 清理状态
                    browserScreenshot.src = '';
                    screenshotOverlay.classList.remove('hidden');
                }
            }, 5000); // 5秒后强制关闭UI
        } else {
            // 如果没有活跃会话，直接关闭UI
            browserViewModal.classList.add('hidden');
            currentBrowserSession = null;
            
            // 清理状态
            browserScreenshot.src = '';
            screenshotOverlay.classList.remove('hidden');
        }
    }
    
    // 请求浏览器视图
    function requestBrowserView() {
        if (socket && currentBrowserSession) {
            console.log('请求刷新截图:', currentBrowserSession);
            updateBrowserStatus('正在刷新画面...', 'info', 'ri-refresh-line spinning');
            
            socket.emit('request_browser_view', {
                session_id: currentBrowserSession
            });
        } else {
            console.warn('无法刷新截图: 没有活跃的浏览器会话');
            updateBrowserStatus('没有活跃的浏览器会话，请重新生成Cookie', 'error', 'ri-error-warning-line');
            screenshotOverlay.classList.remove('hidden');
        }
    }
    
    // 处理浏览器状态更新
    function handleBrowserStatus(data) {
        if (data.session_id !== currentBrowserSession) {
            return;
        }
        
        let statusClass = 'info';
        let icon = 'ri-loader-line spinning';
        
        switch (data.status) {
            case 'browser_opened':
                statusClass = 'success';
                icon = 'ri-checkbox-circle-line';
                break;
            case 'closing':
                statusClass = 'warning';
                icon = 'ri-close-circle-line';
                break;
            case 'cookie_saved':
                statusClass = 'success';
                icon = 'ri-check-line';
                // Cookie保存成功后，延迟关闭模态框并刷新所有相关数据
                setTimeout(() => {
                    closeBrowserView();
                    alert('Cookie生成成功！');
                    loadCookies();
                    loadTaskCookieOptions();
                    loadFingerprints();
                    loadProxyAssignments();
                }, 2000);
                break;
            case 'error':
                statusClass = 'error';
                icon = 'ri-error-warning-line';
                break;
        }
        
        updateBrowserStatus(data.message, statusClass, icon);
    }
    
    // 处理浏览器截图
    function handleBrowserScreenshot(data) {
        if (data.session_id !== currentBrowserSession) {
            return;
        }
        
        // 更新截图
        browserScreenshot.src = data.screenshot;
        
        // 确保图片完整显示，不被裁切
        browserScreenshot.onload = function() {
            // 强制移除所有尺寸限制，确保完整显示
            browserScreenshot.style.width = 'auto';
            browserScreenshot.style.height = 'auto';
            browserScreenshot.style.maxWidth = 'none';
            browserScreenshot.style.maxHeight = 'none';
            browserScreenshot.style.minWidth = 'none';
            browserScreenshot.style.minHeight = 'none';
            browserScreenshot.style.objectFit = 'none';
            
            // 重新应用当前缩放设置
            applyZoom();
            // 设置点击功能
            setupBrowserScreenshotClick();
            
            console.log('截图已成功加载和显示');
        };
        
        // 图片加载失败处理
        browserScreenshot.onerror = function() {
            console.error('截图加载失败');
            updateBrowserStatus('截图加载失败，请重新刷新', 'error', 'ri-error-warning-line');
            screenshotOverlay.classList.remove('hidden');
        };
        
        screenshotOverlay.classList.add('hidden');
        
        // 更新时间戳
        const timestamp = new Date(data.timestamp * 1000);
        screenshotTimestamp.textContent = `最后更新: ${timestamp.toLocaleTimeString()}`;
    }
    
    // 暴露函数到全局作用域以便调试
    window.handleBrowserScreenshot = handleBrowserScreenshot;
    window.handleBrowserStatus = handleBrowserStatus;
    window.showBrowserView = showBrowserView;
    window.closeBrowserView = closeBrowserView;
    window.getCurrentBrowserSession = () => currentBrowserSession;
    
    // 更新浏览器状态消息
    function updateBrowserStatus(message, type = 'info', icon = 'ri-loader-line spinning') {
        browserStatus.innerHTML = `<i class="${icon}"></i> ${message}`;
        browserStatus.className = `status-message status-${type}`;
    }
    
    // 设置浏览器截图点击功能
    function setupBrowserScreenshotClick() {
        // 移除之前的事件监听器
        browserScreenshot.onclick = null;
        
        // 添加新的点击事件监听器
        browserScreenshot.onclick = function(event) {
            if (!currentBrowserSession || !screenshotOverlay.classList.contains('hidden')) {
                return;
            }
            
            // 获取点击坐标（相对于图片，考虑缩放）
            const rect = browserScreenshot.getBoundingClientRect();
            const scaleX = browserScreenshot.naturalWidth / (rect.width / currentZoom);
            const scaleY = browserScreenshot.naturalHeight / (rect.height / currentZoom);
            
            // 计算在实际浏览器中的坐标
            const browserX = Math.round((event.clientX - rect.left) * scaleX / currentZoom);
            const browserY = Math.round((event.clientY - rect.top) * scaleY / currentZoom);
            
            // 计算在显示图片中的坐标（用于动画显示）
            const displayX = event.clientX - rect.left;
            const displayY = event.clientY - rect.top;
            
            // 发送点击事件到后端
            if (socket && currentBrowserSession) {
                socket.emit('browser_click', {
                    session_id: currentBrowserSession,
                    x: browserX,
                    y: browserY
                });
                
                // 显示点击位置的视觉反馈（使用显示坐标）
                showClickFeedback(displayX, displayY);
            }
        };
        
        // 添加鼠标悬停效果
        browserScreenshot.style.cursor = 'pointer';
        browserScreenshot.title = '点击此处与浏览器交互';
    }
    
    // ============ 缩放和平移功能 ============
    
    // 初始化缩放和平移功能
    function initZoomAndPan() {
        if (!zoomInBtn || !zoomOutBtn || !zoomResetBtn || !panResetBtn) {
            console.log('缩放控制按钮未找到，跳过初始化');
            return;
        }
        
        // 缩放按钮事件
        zoomInBtn.addEventListener('click', function() {
            zoomIn();
        });
        
        zoomOutBtn.addEventListener('click', function() {
            zoomOut();
        });
        
        zoomResetBtn.addEventListener('click', function() {
            resetZoom();
        });
        
        panResetBtn.addEventListener('click', function() {
            resetPan();
        });
        
        // 截图视口拖拽事件
        if (screenshotViewport) {
            screenshotViewport.addEventListener('mousedown', function(e) {
                if (e.button === 0) { // 左键
                    isDragging = true;
                    dragStart.x = e.clientX;
                    dragStart.y = e.clientY;
                    scrollStart.x = screenshotViewport.scrollLeft;
                    scrollStart.y = screenshotViewport.scrollTop;
                    screenshotViewport.style.cursor = 'grabbing';
                    e.preventDefault();
                }
            });
            
            screenshotViewport.addEventListener('mousemove', function(e) {
                if (isDragging) {
                    const deltaX = e.clientX - dragStart.x;
                    const deltaY = e.clientY - dragStart.y;
                    screenshotViewport.scrollLeft = scrollStart.x - deltaX;
                    screenshotViewport.scrollTop = scrollStart.y - deltaY;
                }
            });
            
            screenshotViewport.addEventListener('mouseup', function(e) {
                if (isDragging) {
                    isDragging = false;
                    screenshotViewport.style.cursor = 'grab';
                }
            });
            
            screenshotViewport.addEventListener('mouseleave', function(e) {
                if (isDragging) {
                    isDragging = false;
                    screenshotViewport.style.cursor = 'grab';
                }
            });
            
            // 鼠标滚轮缩放
            screenshotViewport.addEventListener('wheel', function(e) {
                if (e.ctrlKey) {
                    e.preventDefault();
                    if (e.deltaY < 0) {
                        zoomIn();
                    } else {
                        zoomOut();
                    }
                }
            });
        }
    }
    
    // 放大
    function zoomIn() {
        if (currentZoom < 3.0) {
            currentZoom = Math.min(3.0, currentZoom + 0.2);
            applyZoom();
        }
    }
    
    // 缩小
    function zoomOut() {
        if (currentZoom > 0.5) {
            currentZoom = Math.max(0.5, currentZoom - 0.2);
            applyZoom();
        }
    }
    
    // 重置缩放
    function resetZoom() {
        currentZoom = 1.0;
        applyZoom();
    }
    
    // 重置位置
    function resetPan() {
        if (screenshotViewport) {
            screenshotViewport.scrollLeft = 0;
            screenshotViewport.scrollTop = 0;
        }
    }
    
    // 应用缩放
    function applyZoom() {
        if (browserScreenshot && zoomLevelSpan) {
            // 使用transform scale来缩放，保持图片原始尺寸显示
            browserScreenshot.style.transform = `scale(${currentZoom})`;
            browserScreenshot.style.transformOrigin = '0 0'; // 从左上角开始缩放
            zoomLevelSpan.textContent = Math.round(currentZoom * 100) + '%';
            
            // 更新按钮状态
            if (zoomInBtn) zoomInBtn.disabled = currentZoom >= 3.0;
            if (zoomOutBtn) zoomOutBtn.disabled = currentZoom <= 0.5;
        }
    }
    
    // 显示点击位置的视觉反馈
    function showClickFeedback(x, y) {
        // 获取截图视口容器
        const container = screenshotViewport || document.getElementById('screenshot-viewport');
        
        // 确保容器设置为相对定位
        if (container && container.style.position !== 'relative') {
            container.style.position = 'relative';
        }
        
        // 创建点击反馈元素
        const feedback = document.createElement('div');
        feedback.className = 'click-feedback';
        
        // 计算点击反馈位置（考虑滚动和缩放）
        const scrollLeft = container.scrollLeft || 0;
        const scrollTop = container.scrollTop || 0;
        
        // 使用容器内的绝对定位
        feedback.style.cssText = `
            position: absolute;
            left: ${x - 10 + scrollLeft}px;
            top: ${y - 10 + scrollTop}px;
            width: 20px;
            height: 20px;
            border: 3px solid #007acc;
            border-radius: 50%;
            background: rgba(0, 122, 204, 0.15);
            pointer-events: none;
            animation: clickPulse 0.6s ease-out;
            z-index: 1000;
            box-shadow: 
                0 0 15px rgba(0, 122, 204, 0.6),
                inset 0 0 10px rgba(255, 255, 255, 0.3);
            backdrop-filter: blur(2px);
            transform-origin: center center;
        `;
        
        // 将反馈元素添加到截图容器中
        container.appendChild(feedback);
        
        // 调试信息输出
        console.log('点击反馈位置调试信息:', {
            originalX: x,
            originalY: y,
            scrollLeft: scrollLeft,
            scrollTop: scrollTop,
            finalX: x - 10 + scrollLeft,
            finalY: y - 10 + scrollTop,
            currentZoom: currentZoom
        });
        
        // 动画结束后移除元素
        setTimeout(() => {
            if (container.contains(feedback)) {
                container.removeChild(feedback);
            }
        }, 600);
    }
    
    // 处理点击接收确认
    function handleClickReceived(data) {
        if (data.session_id === currentBrowserSession) {
            updateBrowserStatus(`正在执行点击: (${data.x}, ${data.y})`, 'warning', 'ri-hand-finger-line');
        }
    }
    
    // 处理点击执行完成
    function handleClickExecuted(data) {
        if (data.session_id === currentBrowserSession) {
            updateBrowserStatus(`点击已执行: (${data.x}, ${data.y})`, 'success', 'ri-check-line');
            
            // 2秒后恢复状态显示
            setTimeout(() => {
                updateBrowserStatus('浏览器运行中，点击图片进行交互', 'success', 'ri-computer-line');
            }, 2000);
        }
    }
    
    // ============ 键盘输入控制功能 ============
    
    // 初始化键盘输入控制
    function initKeyboardControls() {
        // 发送文本按钮
        sendTextBtn.addEventListener('click', function() {
            sendTextInput();
        });
        
        // 清空输入按钮
        clearInputBtn.addEventListener('click', function() {
            clearBrowserInput();
        });
        
        // 输入框回车发送
        textInput.addEventListener('keypress', function(event) {
            if (event.key === 'Enter') {
                sendTextInput();
            }
        });
        
        // 输入框实时监听
        textInput.addEventListener('input', function() {
            const hasText = textInput.value.trim().length > 0;
            sendTextBtn.disabled = !hasText || !currentBrowserSession;
        });
        
        // 特殊按键按钮
        keyButtons.forEach(button => {
            button.addEventListener('click', function() {
                const key = this.dataset.key;
                sendKeyPress(key);
            });
        });
        
        // 全局键盘监听（当输入框获得焦点时）
        textInput.addEventListener('keydown', function(event) {
            // 某些特殊按键直接发送到浏览器
            if (event.ctrlKey || event.altKey || event.metaKey) {
                event.preventDefault();
                const key = getKeyString(event);
                sendKeyPress(key);
            }
        });
    }
    
    // 发送文本输入
    function sendTextInput() {
        const text = textInput.value.trim();
        
        if (!text || !currentBrowserSession || !socket) {
            return;
        }
        
        // 添加视觉反馈
        textInput.classList.add('sending');
        sendTextBtn.classList.add('sending');
        
        socket.emit('browser_input', {
            session_id: currentBrowserSession,
            action: 'type',
            text: text
        });
        
        // 清空输入框
        textInput.value = '';
        sendTextBtn.disabled = true;
        
        // 显示发送状态
        updateBrowserStatus(`正在输入: ${text}`, 'warning', 'ri-keyboard-line');
        
        // 移除动画效果
        setTimeout(() => {
            textInput.classList.remove('sending');
            sendTextBtn.classList.remove('sending');
        }, 600);
    }
    
    // 发送按键操作
    function sendKeyPress(key) {
        if (!currentBrowserSession || !socket) {
            return;
        }
        
        // 查找按键按钮并添加视觉反馈
        const keyBtn = document.querySelector(`[data-key="${key}"]`);
        if (keyBtn) {
            keyBtn.classList.add('active');
            setTimeout(() => {
                keyBtn.classList.remove('active');
            }, 400);
        }
        
        socket.emit('browser_input', {
            session_id: currentBrowserSession,
            action: 'press',
            key: key
        });
        
        updateBrowserStatus(`正在按键: ${key}`, 'warning', 'ri-keyboard-line');
    }
    
    // 清空浏览器输入框
    function clearBrowserInput() {
        if (!currentBrowserSession || !socket) {
            return;
        }
        
        socket.emit('browser_input', {
            session_id: currentBrowserSession,
            action: 'clear'
        });
        
        updateBrowserStatus('正在清空输入框...', 'warning', 'ri-delete-bin-line');
    }
    
    // 获取键盘事件的键名
    function getKeyString(event) {
        let keys = [];
        
        if (event.ctrlKey) keys.push('Control');
        if (event.altKey) keys.push('Alt');
        if (event.metaKey) keys.push('Meta');
        if (event.shiftKey) keys.push('Shift');
        
        if (event.key && !['Control', 'Alt', 'Meta', 'Shift'].includes(event.key)) {
            keys.push(event.key);
        }
        
        return keys.join('+');
    }
    
    // 处理输入接收确认
    function handleInputReceived(data) {
        if (data.session_id === currentBrowserSession) {
            updateBrowserStatus(data.message, 'info', 'ri-keyboard-line');
        }
    }
    
    // 处理输入执行完成
    function handleInputExecuted(data) {
        if (data.session_id === currentBrowserSession) {
            updateBrowserStatus(data.message, 'success', 'ri-check-line');
            
            // 2秒后恢复状态显示
            setTimeout(() => {
                updateBrowserStatus('浏览器运行中，可以输入文本和按键', 'success', 'ri-computer-line');
            }, 2000);
        }
    }
    
    // ============ Cookie失效处理功能 ============
    
    // 处理Cookie失效事件
    function handleCookieExpired(data) {
        console.log('Cookie失效事件:', data);
        
        // 显示警告提示
        alert(`⚠️ Cookie失效通知\n\n文件: ${data.cookie_file}\n原因: 登录状态已过期\n\n系统将自动打开浏览器窗口，请重新登录。`);
        
        // 自动打开浏览器视图让用户重新登录
        currentBrowserSession = data.session_id;
        showBrowserView();
        
        // 更新状态显示
        updateBrowserStatus(data.message, 'warning', 'ri-error-warning-line');
        
        // 在浏览器视图中显示特殊提示
        const specialHint = document.createElement('div');
        specialHint.className = 'cookie-expired-hint';
        specialHint.innerHTML = `
            <div style="
                background: linear-gradient(135deg, #ff6b6b, #ee5a24);
                color: white;
                padding: 12px 16px;
                border-radius: 8px;
                margin-bottom: 16px;
                display: flex;
                align-items: center;
                gap: 10px;
                box-shadow: 0 4px 12px rgba(238, 90, 36, 0.3);
            ">
                <i class="ri-error-warning-line" style="font-size: 20px;"></i>
                <div>
                    <strong>Cookie已失效</strong><br>
                    <small>请在浏览器中重新登录您的抖音账号</small>
                </div>
            </div>
        `;
        
        // 将提示插入到浏览器控制区域
        const browserControls = document.querySelector('.browser-controls');
        if (browserControls) {
            browserControls.parentNode.insertBefore(specialHint, browserControls);
            
            // 5秒后自动移除提示
            setTimeout(() => {
                if (specialHint.parentNode) {
                    specialHint.parentNode.removeChild(specialHint);
                }
            }, 10000);
        }
    }
    
    // 在DOMContentLoaded中初始化键盘控制
    initKeyboardControls();
    
    // 初始化缩放和平移功能
    initZoomAndPan();
    
    // ============ 浏览器指纹管理功能 ============
    
    // 浏览器指纹相关变量
    let allFingerprints = [];
    let filteredFingerprints = [];
    let currentFingerprintCookie = null;
    
    // 加载浏览器指纹数据
    function loadFingerprints() {
        fetch('/api/fingerprints')
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    allFingerprints = data.fingerprints;
                    filteredFingerprints = [...allFingerprints];
                    updateFingerprintTable();
                    updateFingerprintStats();
                } else {
                    console.error('加载指纹失败:', data.message);
                    showFingerprintError('加载指纹数据失败: ' + data.message);
                }
            })
            .catch(error => {
                console.error('加载指纹请求失败:', error);
                showFingerprintError('网络错误，无法加载指纹数据');
            });
    }
    
    // 更新指纹表格
    function updateFingerprintTable() {
        const tbody = document.getElementById('fingerprint-table-body');
        
        if (filteredFingerprints.length === 0) {
            tbody.innerHTML = `
                <tr class="loading-row">
                    <td colspan="8" class="loading-cell">
                        <i class="ri-ghost-line"></i> 暂无指纹数据
                    </td>
                </tr>
            `;
            return;
        }
        
        tbody.innerHTML = filteredFingerprints.map(fp => {
            // 格式化时间显示
            const createTime = fp.created_time ? new Date(fp.created_time).toLocaleDateString('zh-CN') : '-';
            const lastUsed = fp.last_used ? new Date(fp.last_used).toLocaleDateString('zh-CN') : '未使用';
            
            return `
                <tr>
                    <td>
                        <span class="cookie-name-cell" onclick="showFingerprintDetail('${fp.cookie_name}')">
                            ${fp.cookie_name}
                        </span>
                    </td>
                    <td class="user-agent-cell" title="${fp.user_agent || '-'}">
                        ${fp.user_agent ? fp.user_agent.substring(0, 50) + '...' : '-'}
                    </td>
                    <td class="resolution-cell">
                        ${fp.screen_resolution || '-'}
                    </td>
                    <td class="timezone-cell">
                        ${fp.timezone || '-'}
                    </td>
                    <td class="language-cell">
                        ${fp.language || '-'}
                    </td>
                    <td class="datetime-cell">
                        ${createTime}
                    </td>
                    <td class="datetime-cell">
                        ${lastUsed}
                    </td>
                    <td>
                        <div class="action-buttons">
                            <button class="action-btn" onclick="showFingerprintDetail('${fp.cookie_name}')" title="查看详情">
                                <i class="ri-eye-line"></i>
                            </button>
                            <button class="action-btn danger" onclick="regenerateFingerprint('${fp.cookie_name}')" title="重新生成">
                                <i class="ri-refresh-line"></i>
                            </button>
                            <button class="action-btn danger" onclick="deleteFingerprint('${fp.cookie_name}')" title="删除指纹">
                                <i class="ri-delete-bin-line"></i>
                            </button>
                        </div>
                    </td>
                </tr>
            `;
        }).join('');
    }
    
    // 更新指纹统计
    function updateFingerprintStats() {
        const totalCount = allFingerprints.length;
        const recentCount = allFingerprints.filter(fp => {
            if (!fp.last_used) return false;
            const lastUsed = new Date(fp.last_used);
            const weekAgo = new Date();
            weekAgo.setDate(weekAgo.getDate() - 7);
            return lastUsed > weekAgo;
        }).length;
        
        document.getElementById('total-fingerprints').textContent = totalCount;
        document.getElementById('active-fingerprints').textContent = recentCount;
    }
    
    // 显示指纹详情
    function showFingerprintDetail(cookieName) {
        currentFingerprintCookie = cookieName;
        
        // 显示加载状态
        const modal = document.getElementById('fingerprint-detail-modal');
        modal.classList.remove('hidden');
        
        // 重置详情内容
        resetFingerprintDetailContent();
        
        // 获取指纹详情
        fetch(`/api/fingerprints/${encodeURIComponent(cookieName)}`)
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    populateFingerprintDetail(data.fingerprint);
                } else {
                    showFingerprintError('获取指纹详情失败: ' + data.message);
                }
            })
            .catch(error => {
                console.error('获取指纹详情失败:', error);
                showFingerprintError('网络错误，无法获取指纹详情');
            });
    }
    
    // 重置指纹详情内容
    function resetFingerprintDetailContent() {
        const fields = [
            'detail-cookie-name', 'detail-user-agent', 'detail-platform', 'detail-language',
            'detail-screen-resolution', 'detail-viewport', 'detail-color-depth', 'detail-timezone',
            'detail-cpu-cores', 'detail-memory', 'detail-webgl-vendor', 'detail-webgl-renderer',
            'detail-canvas-noise', 'detail-plugins-count', 'detail-fonts-count', 'detail-dnt'
        ];
        
        fields.forEach(fieldId => {
            const element = document.getElementById(fieldId);
            if (element) {
                element.textContent = '加载中...';
            }
        });
    }
    
    // 填充指纹详情
    function populateFingerprintDetail(fingerprint) {
        document.getElementById('detail-cookie-name').textContent = currentFingerprintCookie;
        document.getElementById('detail-user-agent').textContent = fingerprint.userAgent || '-';
        document.getElementById('detail-platform').textContent = fingerprint.platform || '-';
        document.getElementById('detail-language').textContent = fingerprint.language || '-';
        
        const screen = fingerprint.screen || {};
        document.getElementById('detail-screen-resolution').textContent = 
            screen.width && screen.height ? `${screen.width} × ${screen.height}` : '-';
        
        const viewport = fingerprint.viewport || {};
        document.getElementById('detail-viewport').textContent = 
            viewport.width && viewport.height ? `${viewport.width} × ${viewport.height}` : '-';
        
        document.getElementById('detail-color-depth').textContent = 
            screen.colorDepth ? `${screen.colorDepth} 位` : '-';
        document.getElementById('detail-timezone').textContent = fingerprint.timezone || '-';
        
        document.getElementById('detail-cpu-cores').textContent = 
            fingerprint.hardwareConcurrency ? `${fingerprint.hardwareConcurrency} 核` : '-';
        document.getElementById('detail-memory').textContent = 
            fingerprint.deviceMemory ? `${fingerprint.deviceMemory} GB` : '-';
        
        const webgl = fingerprint.webgl || {};
        document.getElementById('detail-webgl-vendor').textContent = webgl.vendor || '-';
        document.getElementById('detail-webgl-renderer').textContent = webgl.renderer || '-';
        
        const canvas = fingerprint.canvas || {};
        document.getElementById('detail-canvas-noise').textContent = 
            canvas.noise ? canvas.noise.toFixed(6) : '-';
        
        document.getElementById('detail-plugins-count').textContent = 
            fingerprint.plugins ? `${fingerprint.plugins.length} 个` : '-';
        document.getElementById('detail-fonts-count').textContent = 
            fingerprint.fonts ? `${fingerprint.fonts.length} 个` : '-';
        
        document.getElementById('detail-dnt').textContent = 
            fingerprint.doNotTrack === null ? '未设置' : 
            fingerprint.doNotTrack === '1' ? '启用' : '禁用';
    }
    
    // 重新生成指纹
    function regenerateFingerprint(cookieName) {
        if (!confirm(`确定要重新生成 ${cookieName} 的浏览器指纹吗？\\n\\n注意：这将完全改变该账号的浏览器环境参数。`)) {
            return;
        }
        
        const button = event.target.closest('button');
        const originalContent = button.innerHTML;
        button.innerHTML = '<i class="ri-loader-line spinning"></i>';
        button.disabled = true;
        
        fetch(`/api/fingerprints/${encodeURIComponent(cookieName)}/regenerate`, {
            method: 'POST'
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                showSuccessMessage(`✅ ${data.message}`);
                loadFingerprints(); // 重新加载指纹列表
                
                // 如果详情窗口打开着，更新详情
                if (currentFingerprintCookie === cookieName) {
                    populateFingerprintDetail(data.fingerprint);
                }
            } else {
                showFingerprintError('重新生成指纹失败: ' + data.message);
            }
        })
        .catch(error => {
            console.error('重新生成指纹失败:', error);
            showFingerprintError('网络错误，重新生成指纹失败');
        })
        .finally(() => {
            button.innerHTML = originalContent;
            button.disabled = false;
        });
    }
    
    // 删除指纹
    function deleteFingerprint(cookieName) {
        if (!confirm(`确定要删除 ${cookieName} 的浏览器指纹吗？\\n\\n注意：删除后该账号将失去当前的浏览器环境保护，下次使用时会自动生成新指纹。`)) {
            return;
        }
        
        const button = event.target.closest('button');
        const originalContent = button.innerHTML;
        button.innerHTML = '<i class="ri-loader-line spinning"></i>';
        button.disabled = true;
        
        fetch(`/api/fingerprints/${encodeURIComponent(cookieName)}`, {
            method: 'DELETE'
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                showSuccessMessage(`✅ ${data.message}`);
                loadFingerprints(); // 重新加载指纹列表
                
                // 如果详情窗口打开着并且是当前删除的指纹，关闭窗口
                if (currentFingerprintCookie === cookieName) {
                    document.getElementById('fingerprint-detail-modal').classList.add('hidden');
                    currentFingerprintCookie = null;
                }
            } else {
                showFingerprintError('删除指纹失败: ' + data.message);
            }
        })
        .catch(error => {
            console.error('删除指纹失败:', error);
            showFingerprintError('网络错误，删除指纹失败');
        })
        .finally(() => {
            button.innerHTML = originalContent;
            button.disabled = false;
        });
    }
    
    // 复制指纹JSON数据
    function copyFingerprintJson() {
        if (!currentFingerprintCookie) {
            return;
        }
        
        fetch(`/api/fingerprints/${encodeURIComponent(currentFingerprintCookie)}`)
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    const jsonText = JSON.stringify(data.fingerprint, null, 2);
                    navigator.clipboard.writeText(jsonText).then(() => {
                        showSuccessMessage('✅ 指纹JSON数据已复制到剪贴板');
                    }).catch(() => {
                        // 创建临时文本区域
                        const textarea = document.createElement('textarea');
                        textarea.value = jsonText;
                        document.body.appendChild(textarea);
                        textarea.select();
                        document.execCommand('copy');
                        document.body.removeChild(textarea);
                        showSuccessMessage('✅ 指纹JSON数据已复制');
                    });
                } else {
                    showFingerprintError('获取指纹数据失败');
                }
            })
            .catch(error => {
                console.error('获取指纹数据失败:', error);
                showFingerprintError('网络错误');
            });
    }
    
    // 搜索指纹
    function searchFingerprints() {
        const searchTerm = document.getElementById('fingerprint-search').value.toLowerCase();
        
        filteredFingerprints = allFingerprints.filter(fp => 
            fp.cookie_name.toLowerCase().includes(searchTerm)
        );
        
        updateFingerprintTable();
    }
    
    // 过滤指纹
    function filterFingerprints(type) {
        const now = new Date();
        const weekAgo = new Date();
        weekAgo.setDate(weekAgo.getDate() - 7);
        
        if (type === 'recent') {
            filteredFingerprints = allFingerprints.filter(fp => {
                if (!fp.last_used) return false;
                return new Date(fp.last_used) > weekAgo;
            });
        } else {
            filteredFingerprints = [...allFingerprints];
        }
        
        updateFingerprintTable();
        
        // 更新过滤按钮状态
        document.querySelectorAll('.filter-btn').forEach(btn => btn.classList.remove('active'));
        document.getElementById(`show-${type}-fingerprints`).classList.add('active');
    }
    
    // 显示指纹错误
    function showFingerprintError(message) {
        const tbody = document.getElementById('fingerprint-table-body');
        tbody.innerHTML = `
            <tr class="loading-row">
                <td colspan="8" class="loading-cell" style="color: var(--error-color);">
                    <i class="ri-error-warning-line"></i> ${message}
                </td>
            </tr>
        `;
    }
    
    // 显示成功消息
    function showSuccessMessage(message) {
        // 创建临时提示
        const toast = document.createElement('div');
        toast.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            background: var(--success-color);
            color: white;
            padding: 12px 20px;
            border-radius: 8px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
            z-index: 10000;
            font-size: 14px;
            animation: slideIn 0.3s ease-out;
        `;
        toast.textContent = message;
        
        document.body.appendChild(toast);
        
        setTimeout(() => {
            toast.style.animation = 'slideOut 0.3s ease-in forwards';
            setTimeout(() => {
                if (toast.parentNode) {
                    toast.parentNode.removeChild(toast);
                }
            }, 300);
        }, 3000);
    }
    
    // 设置指纹管理事件监听器
    function setupFingerprintEvents() {
        // 刷新按钮
        const refreshBtn = document.getElementById('refresh-fingerprints');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', loadFingerprints);
        }
        
        // 搜索框
        const searchInput = document.getElementById('fingerprint-search');
        if (searchInput) {
            searchInput.addEventListener('input', searchFingerprints);
        }
        
        // 过滤按钮
        const showAllBtn = document.getElementById('show-all-fingerprints');
        if (showAllBtn) {
            showAllBtn.addEventListener('click', () => filterFingerprints('all'));
        }
        
        const showRecentBtn = document.getElementById('show-recent-fingerprints');
        if (showRecentBtn) {
            showRecentBtn.addEventListener('click', () => filterFingerprints('recent'));
        }
        
        // 详情模态框关闭
        const closeDetailBtn = document.getElementById('close-fingerprint-detail');
        if (closeDetailBtn) {
            closeDetailBtn.addEventListener('click', () => {
                document.getElementById('fingerprint-detail-modal').classList.add('hidden');
                currentFingerprintCookie = null;
            });
        }
        
        // 重新生成指纹按钮
        const regenerateBtn = document.getElementById('regenerate-fingerprint');
        if (regenerateBtn) {
            regenerateBtn.addEventListener('click', () => {
                if (currentFingerprintCookie) {
                    regenerateFingerprint(currentFingerprintCookie);
                }
            });
        }
        
        // 复制JSON按钮
        const copyJsonBtn = document.getElementById('copy-fingerprint-json');
        if (copyJsonBtn) {
            copyJsonBtn.addEventListener('click', copyFingerprintJson);
        }
    }
    
    // 初始化指纹管理
    setupFingerprintEvents();
    
    // 添加CSS动画
    const style = document.createElement('style');
    style.textContent = `
        @keyframes slideIn {
            from { transform: translateX(100%); opacity: 0; }
            to { transform: translateX(0); opacity: 1; }
        }
        @keyframes slideOut {
            from { transform: translateX(0); opacity: 1; }
            to { transform: translateX(100%); opacity: 0; }
        }
    `;
    document.head.appendChild(style);
    
    // 暴露全局函数供HTML调用
    window.showFingerprintDetail = showFingerprintDetail;
    window.regenerateFingerprint = regenerateFingerprint;
    window.deleteFingerprint = deleteFingerprint;
    
    // 显示文件右键菜单
    function showFileContextMenu(event, filePath, fileName) {
        // 移除已存在的菜单
        const existingMenu = document.getElementById('file-context-menu');
        if (existingMenu) {
            existingMenu.remove();
        }
        
        // 创建右键菜单
        const menu = document.createElement('div');
        menu.id = 'file-context-menu';
        menu.className = 'context-menu';
        menu.style.position = 'fixed';
        menu.style.left = event.clientX + 'px';
        menu.style.top = event.clientY + 'px';
        menu.style.zIndex = '9999';
        
        // 检查文件是否已选中
        const isSelected = selectedVideos.find(v => normalizePath(v.path) === normalizePath(filePath));
        
        // 添加选择/取消选择菜单项
        const toggleSelectItem = document.createElement('div');
        toggleSelectItem.className = 'context-menu-item';
        if (isSelected) {
            toggleSelectItem.innerHTML = '<i class="ri-checkbox-blank-line"></i> 取消选择';
            toggleSelectItem.addEventListener('click', function() {
                toggleSelectVideo(filePath, fileName);
                menu.remove();
            });
        } else {
            toggleSelectItem.innerHTML = '<i class="ri-checkbox-line"></i> 选择';
            toggleSelectItem.addEventListener('click', function() {
                toggleSelectVideo(filePath, fileName);
                menu.remove();
            });
        }
        
        // 添加分隔线
        const separator = document.createElement('div');
        separator.className = 'context-menu-separator';
        
        // 添加删除文件菜单项
        const deleteFileItem = document.createElement('div');
        deleteFileItem.className = 'context-menu-item danger';
        deleteFileItem.innerHTML = '<i class="ri-delete-bin-line"></i> 删除文件';
        deleteFileItem.addEventListener('click', function() {
            deleteFileWithConfirm(filePath, fileName);
            menu.remove();
        });
        
        menu.appendChild(toggleSelectItem);
        menu.appendChild(separator);
        menu.appendChild(deleteFileItem);
        
        document.body.appendChild(menu);
        
        // 点击其他地方时关闭菜单
        const closeMenu = function(e) {
            if (!menu.contains(e.target)) {
                menu.remove();
                document.removeEventListener('click', closeMenu);
            }
        };
        
        setTimeout(() => {
            document.addEventListener('click', closeMenu);
        }, 10);
    }
    
    // 显示文件夹右键菜单
    function showFolderContextMenu(event, folderPath, folderName) {
        // 移除已存在的菜单
        const existingMenu = document.getElementById('folder-context-menu');
        if (existingMenu) {
            existingMenu.remove();
        }
        
        // 创建右键菜单
        const menu = document.createElement('div');
        menu.id = 'folder-context-menu';
        menu.className = 'context-menu';
        menu.style.position = 'fixed';
        menu.style.left = event.clientX + 'px';
        menu.style.top = event.clientY + 'px';
        menu.style.zIndex = '9999';
        
        // 添加菜单项
        const selectAllItem = document.createElement('div');
        selectAllItem.className = 'context-menu-item';
        selectAllItem.innerHTML = '<i class="ri-checkbox-multiple-line"></i> 选择该文件夹所有视频';
        selectAllItem.addEventListener('click', function() {
            selectAllVideosInFolder(folderPath, folderName);
            menu.remove();
        });
        
        const unselectAllItem = document.createElement('div');
        unselectAllItem.className = 'context-menu-item';
        unselectAllItem.innerHTML = '<i class="ri-checkbox-blank-line"></i> 取消选择该文件夹所有视频';
        unselectAllItem.addEventListener('click', function() {
            unselectAllVideosInFolder(folderPath, folderName);
            menu.remove();
        });
        
        // 添加分隔线
        const separator = document.createElement('div');
        separator.className = 'context-menu-separator';
        
        const deleteFolderItem = document.createElement('div');
        deleteFolderItem.className = 'context-menu-item danger';
        deleteFolderItem.innerHTML = '<i class="ri-delete-bin-line"></i> 删除文件夹及内容';
        deleteFolderItem.addEventListener('click', function() {
            deleteFolderWithConfirm(folderPath, folderName);
            menu.remove();
        });
        
        menu.appendChild(selectAllItem);
        menu.appendChild(unselectAllItem);
        menu.appendChild(separator);
        menu.appendChild(deleteFolderItem);
        
        document.body.appendChild(menu);
        
        // 点击其他地方时关闭菜单
        const closeMenu = function(e) {
            if (!menu.contains(e.target)) {
                menu.remove();
                document.removeEventListener('click', closeMenu);
            }
        };
        
        setTimeout(() => {
            document.addEventListener('click', closeMenu);
        }, 10);
    }
    
    // 选择文件夹中所有视频
    function selectAllVideosInFolder(folderPath, folderName) {
        const normalizedFolderPath = normalizePath(folderPath);  // 修复路径格式
        fetch('/api/folder_videos', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ folder_path: normalizedFolderPath })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                let addedCount = 0;
                data.videos.forEach(video => {
                    const normalizedVideoPath = normalizePath(video.path);  // 修复路径格式
                    // 检查是否已经选中
                    const existingIndex = selectedVideos.findIndex(v => normalizePath(v.path) === normalizedVideoPath);
                    if (existingIndex === -1) {
                        selectedVideos.push({
                            path: normalizedVideoPath,
                            name: video.name
                        });
                        addedCount++;
                    }
                });
                
                // 刷新显示
                updateSelectedVideosList();
                loadVideos();
                
                if (addedCount > 0) {
                    alert(`成功添加 ${addedCount} 个视频到选择列表中`);
                } else {
                    alert('该文件夹中的所有视频都已选中');
                }
            } else {
                alert('获取文件夹视频列表失败: ' + data.message);
            }
        })
        .catch(error => {
            console.error('选择文件夹视频失败:', error);
            alert('选择文件夹视频失败，请重试');
        });
    }
    
    // 取消选择文件夹中所有视频
    function unselectAllVideosInFolder(folderPath, folderName) {
        const normalizedFolderPath = normalizePath(folderPath);  // 修复路径格式
        fetch('/api/folder_videos', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ folder_path: normalizedFolderPath })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                let removedCount = 0;
                data.videos.forEach(video => {
                    const normalizedVideoPath = normalizePath(video.path);  // 修复路径格式
                    const existingIndex = selectedVideos.findIndex(v => normalizePath(v.path) === normalizedVideoPath);
                    if (existingIndex !== -1) {
                        selectedVideos.splice(existingIndex, 1);
                        removedCount++;
                    }
                });
                
                // 刷新显示
                updateSelectedVideosList();
                loadVideos();
                
                if (removedCount > 0) {
                    alert(`成功从选择列表中移除 ${removedCount} 个视频`);
                } else {
                    alert('该文件夹中没有已选中的视频');
                }
            } else {
                alert('获取文件夹视频列表失败: ' + data.message);
            }
        })
        .catch(error => {
            console.error('取消选择文件夹视频失败:', error);
            alert('取消选择文件夹视频失败，请重试');
        });
    }
    
    // 全选所有视频
    function selectAllVideos() {
        fetch('/api/videos')
            .then(response => response.json())
            .then(videos => {
                // 递归获取所有视频文件
                function getAllVideosFromTree(items) {
                    let allVideos = [];
                    items.forEach(item => {
                        if (item.type === 'file') {
                            allVideos.push({
                                path: normalizePath(item.path),  // 修复路径格式
                                name: item.name
                            });
                        } else if (item.type === 'folder' && item.children) {
                            allVideos = allVideos.concat(getAllVideosFromTree(item.children));
                        }
                    });
                    return allVideos;
                }
                
                const allVideos = getAllVideosFromTree(videos);
                let addedCount = 0;
                
                allVideos.forEach(video => {
                    const normalizedVideoPath = normalizePath(video.path);  // 修复路径格式
                    const existingIndex = selectedVideos.findIndex(v => normalizePath(v.path) === normalizedVideoPath);
                    if (existingIndex === -1) {
                        selectedVideos.push({
                            path: normalizedVideoPath,
                            name: video.name
                        });
                        addedCount++;
                    }
                });
                
                // 刷新显示
                updateSelectedVideosList();
                loadVideos();
                
                if (addedCount > 0) {
                    alert(`成功添加 ${addedCount} 个视频到选择列表中`);
                } else {
                    alert('所有视频都已选中');
                }
            })
            .catch(error => {
                console.error('获取视频列表失败:', error);
                alert('获取视频列表失败，请重试');
            });
    }
    
    // 删除文件夹及内容（带确认）
    function deleteFolderWithConfirm(folderPath, folderName) {
        const confirmMsg = `确定要删除文件夹"${folderName}"及其所有内容吗？\n\n此操作无法撤销！`;
        if (confirm(confirmMsg)) {
            deleteLocalFolder(folderPath, folderName);
        }
    }
    
    // 删除单个文件（带确认）
    function deleteFileWithConfirm(filePath, fileName) {
        const confirmMsg = `确定要删除文件"${fileName}"吗？\n\n此操作无法撤销！`;
        if (confirm(confirmMsg)) {
            deleteLocalFile(filePath, fileName);
        }
    }
    
    // 删除本地文件夹
    function deleteLocalFolder(folderPath, folderName) {
        const normalizedPath = normalizePath(folderPath);
        
        fetch('/api/videos/delete_folder', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ 
                folder_path: normalizedPath,
                folder_name: folderName
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                // 从选中列表中移除该文件夹下的所有视频
                for (let i = selectedVideos.length - 1; i >= 0; i--) {
                    const videoPath = normalizePath(selectedVideos[i].path);
                    if (videoPath.startsWith(normalizedPath + '/') || videoPath === normalizedPath) {
                        selectedVideos.splice(i, 1);
                    }
                }
                
                // 刷新显示
                updateSelectedVideosList();
                loadVideos();
                
                alert(`文件夹"${folderName}"删除成功！${data.deleted_count ? `共删除了${data.deleted_count}个文件` : ''}`);
            } else {
                alert('删除文件夹失败: ' + data.message);
            }
        })
        .catch(error => {
            console.error('删除文件夹失败:', error);
            alert('删除文件夹失败，请重试');
        });
    }
    
    // 删除本地文件
    function deleteLocalFile(filePath, fileName) {
        const normalizedPath = normalizePath(filePath);
        
        fetch('/api/videos/delete_file', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ 
                file_path: normalizedPath,
                file_name: fileName
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                // 从选中列表中移除该文件
                const index = selectedVideos.findIndex(v => normalizePath(v.path) === normalizedPath);
                if (index !== -1) {
                    selectedVideos.splice(index, 1);
                }
                
                // 刷新显示
                updateSelectedVideosList();
                loadVideos();
                
                alert(`文件"${fileName}"删除成功！`);
            } else {
                alert('删除文件失败: ' + data.message);
            }
        })
        .catch(error => {
            console.error('删除文件失败:', error);
            alert('删除文件失败，请重试');
        });
    }

    // 清空所有选择
    function clearAllVideos() {
        if (selectedVideos.length === 0) {
            alert('当前没有选中的视频');
            return;
        }
        
        const count = selectedVideos.length;
        selectedVideos.length = 0; // 清空数组但保持引用
        
        // 刷新显示
        updateSelectedVideosList();
        loadVideos();
        
        alert(`已清空 ${count} 个已选择的视频`);
    }
    
    // 将函数暴露到全局作用域，供HTML调用
    window.selectAllVideos = selectAllVideos;
    window.clearAllVideos = clearAllVideos;
    window.validateSelectedCookie = validateSelectedCookie;
    window.clearExpiredStatus = clearExpiredStatus;
    
    // 清除cookie失效状态
    function clearExpiredStatus(cookieFile) {
        if (expiredCookies.has(cookieFile)) {
            expiredCookies.delete(cookieFile);
            loadCookies(); // 刷新显示
            alert(`已清除Cookie ${cookieFile} 的失效状态`);
        }
    }
    
    // 验证cookie有效性
    function validateSelectedCookie() {
        const selectedCookie = cookieSelect.value;
        
        if (!selectedCookie) {
            alert('请先选择一个Cookie');
            return;
        }
        
        // 创建临时验证按钮状态
        const validateBtn = document.getElementById('validate-cookie-btn');
        if (validateBtn) {
            validateBtn.disabled = true;
            validateBtn.textContent = '验证中...';
        }
        
        fetch(`/api/cookies/${selectedCookie}/validate`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                if (data.valid) {
                    // Cookie有效，清除失效状态
                    if (expiredCookies.has(selectedCookie)) {
                        expiredCookies.delete(selectedCookie);
                        loadCookies();
                    }
                    alert('Cookie验证成功，可以正常使用');
                } else {
                    // Cookie无效，添加到失效列表
                    expiredCookies.add(selectedCookie);
                    loadCookies();
                    alert(`Cookie验证失败: ${data.message}`);
                }
            } else {
                alert(`Cookie验证出错: ${data.message}`);
            }
        })
        .catch(error => {
            console.error('Cookie验证请求失败:', error);
            alert('Cookie验证请求失败，请重试');
        })
        .finally(() => {
            if (validateBtn) {
                validateBtn.disabled = false;
                validateBtn.textContent = '验证Cookie';
            }
        });
    }
    
    // 多账号任务管理变量
    let multiTasks = [];
    let isMultiUploading = false;
    let multiUploadRefreshInterval = null;
    
    // 获取多账号任务管理相关DOM元素
    const taskCookieSelect = document.getElementById('task-cookie-select');
    const taskLocationInput = document.getElementById('task-location');
    const taskIntervalInput = document.getElementById('task-interval');
    const taskPublishDateInput = document.getElementById('task-publish-date');
    const taskPublishHourSelect = document.getElementById('task-publish-hour');
    const taskPublishMinuteSelect = document.getElementById('task-publish-minute');
    const taskScheduleContainer = document.getElementById('task-schedule-container');
    const multiTaskTableBody = document.getElementById('multi-task-table-body');
    const startMultiUploadBtn = document.getElementById('start-multi-upload-btn');
    const stopMultiUploadBtn = document.getElementById('stop-multi-upload-btn');
    
    // 初始化多账号任务管理
    function initMultiTaskManagement() {
        // 加载Cookie列表到任务选择器
        loadTaskCookieOptions();
        
        // 初始化时间选择器
        initTaskTimeSelectors();
        
        // 绑定定时发布选项切换
        document.querySelectorAll('input[name="task-publish-type"]').forEach(radio => {
            radio.addEventListener('change', toggleTaskScheduleOptions);
        });
        
        // 加载任务列表
        loadMultiTasks();
        
        // 开始定期刷新任务状态
        startMultiTaskRefresh();
    }
    
    // 加载Cookie选项到任务选择器
    function loadTaskCookieOptions() {
        fetch('/api/cookies')
            .then(response => response.json())
            .then(data => {
                const cookies = data.cookies || [];
                taskCookieSelect.innerHTML = '<option value="">请选择Cookie</option>';
                
                cookies.forEach(cookie => {
                    const option = document.createElement('option');
                    option.value = cookie.filename;
                    
                    // 检查是否失效
                    if (expiredCookies.has(cookie.filename) || cookie.expired) {
                        option.textContent = `${cookie.name} (失效)`;
                        option.style.color = '#ff4444';
                        option.disabled = true;
                    } else {
                        option.textContent = cookie.name;
                    }
                    
                    taskCookieSelect.appendChild(option);
                });
            })
            .catch(error => {
                console.error('加载Cookie列表失败:', error);
            });
    }
    
    // 初始化任务时间选择器
    function initTaskTimeSelectors() {
        // 小时选择器
        taskPublishHourSelect.innerHTML = '';
        for (let i = 0; i < 24; i++) {
            const option = document.createElement('option');
            option.value = i.toString().padStart(2, '0');
            option.textContent = i.toString().padStart(2, '0');
            taskPublishHourSelect.appendChild(option);
        }
        
        // 分钟选择器
        taskPublishMinuteSelect.innerHTML = '';
        for (let i = 0; i < 60; i += 5) {
            const option = document.createElement('option');
            option.value = i.toString().padStart(2, '0');
            option.textContent = i.toString().padStart(2, '0');
            taskPublishMinuteSelect.appendChild(option);
        }
        
        // 设置默认日期为今天
        const today = new Date();
        taskPublishDateInput.value = today.toISOString().split('T')[0];
    }
    
    // 切换任务定时发布选项
    function toggleTaskScheduleOptions() {
        const scheduleRadio = document.querySelector('input[name="task-publish-type"][value="schedule"]');
        if (scheduleRadio.checked) {
            taskScheduleContainer.classList.remove('hidden');
        } else {
            taskScheduleContainer.classList.add('hidden');
        }
    }
    
    // 复制当前选择的视频到任务表单
    function copySelectedVideos() {
        if (selectedVideos.length === 0) {
            alert('请先选择要上传的视频');
            return;
        }
        
        // 这里可以添加视觉反馈，表示视频已复制
        const copyBtn = document.getElementById('copy-videos-btn');
        const originalText = copyBtn.innerHTML;
        copyBtn.innerHTML = '<i class="ri-check-line"></i> 已复制';
        copyBtn.style.background = '#28a745';
        
        setTimeout(() => {
            copyBtn.innerHTML = originalText;
            copyBtn.style.background = '';
        }, 2000);
        
        alert(`已复制 ${selectedVideos.length} 个视频到任务配置`);
    }
    
    // 添加账号任务
    function addAccountTask() {
        const selectedCookie = taskCookieSelect.value;
        const location = taskLocationInput.value.trim() || '杭州市';
        const interval = parseInt(taskIntervalInput.value) || 5;
        const publishType = document.querySelector('input[name="task-publish-type"]:checked').value;
        
        if (!selectedCookie) {
            alert('请选择一个Cookie账号');
            return;
        }
        
        if (selectedVideos.length === 0) {
            alert('请先选择要上传的视频');
            return;
        }
        
        // 检查是否已存在该账号的任务
        const existingTask = multiTasks.find(task => task.cookie === selectedCookie);
        if (existingTask) {
            alert(`账号 ${selectedCookie} 已存在任务，请先删除后再添加`);
            return;
        }
        
        const taskData = {
            cookie: selectedCookie,
            videos: selectedVideos.map(v => v.path),
            location: location,
            upload_interval: interval,
            publish_type: publishType
        };
        
        if (publishType === 'schedule') {
            taskData.publish_date = taskPublishDateInput.value;
            taskData.publish_hour = taskPublishHourSelect.value;
            taskData.publish_minute = taskPublishMinuteSelect.value;
            
            if (!taskData.publish_date) {
                alert('请选择定时发布日期');
                return;
            }
        }
        
        // 发送请求添加任务
        fetch('/api/multi_tasks', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(taskData)
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                alert(`成功添加账号 ${selectedCookie} 的上传任务`);
                loadMultiTasks(); // 刷新任务列表
                
                // 清空视频选择
                selectedVideos.length = 0;
                updateSelectedVideosList();
                loadVideos();
            } else {
                alert('添加任务失败: ' + data.message);
            }
        })
        .catch(error => {
            console.error('添加任务请求失败:', error);
            alert('添加任务请求失败，请重试');
        });
    }
    
    // 加载多账号任务列表
    function loadMultiTasks() {
        fetch('/api/multi_tasks')
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    multiTasks = data.tasks;
                    isMultiUploading = data.is_uploading;
                    updateMultiTaskTable();
                    updateMultiUploadButtons();
                }
            })
            .catch(error => {
                console.error('加载任务列表失败:', error);
            });
    }
    
    // 更新任务表格
    function updateMultiTaskTable() {
        if (multiTasks.length === 0) {
            multiTaskTableBody.innerHTML = `
                <tr class="empty-row">
                    <td colspan="7" class="empty-cell">
                        <i class="ri-inbox-line"></i> 暂无任务，请添加账号任务
                    </td>
                </tr>
            `;
            return;
        }
        
        multiTaskTableBody.innerHTML = '';
        
        multiTasks.forEach(task => {
            const row = document.createElement('tr');
            row.className = getTaskRowClass(task.status);
            
            const progress = task.total_videos > 0 
                ? Math.round((task.completed_videos / task.total_videos) * 100) 
                : 0;
            
            const statusText = getTaskStatusText(task);
            const publishInfo = task.publish_type === 'schedule' 
                ? `${task.publish_date} ${task.publish_hour}:${task.publish_minute}`
                : '立即发布';
            
            row.innerHTML = `
                <td>
                    <div class="cookie-info">
                        <i class="ri-user-line"></i>
                        <span>${task.cookie}</span>
                        ${expiredCookies.has(task.cookie) ? '<span class="expired-badge">失效</span>' : ''}
                    </div>
                </td>
                <td>
                    <span class="video-count">${task.total_videos}</span>
                </td>
                <td>
                    <div class="progress-container">
                        <div class="progress-bar">
                            <div class="progress-fill" style="width: ${progress}%"></div>
                        </div>
                        <span class="progress-text">${task.completed_videos}/${task.total_videos} (${progress}%)</span>
                    </div>
                </td>
                <td>
                    <div class="status-container">
                        <span class="status-text">${statusText}</span>
                        ${getCurrentVideoStatus(task) ? `<div class="current-video">${getCurrentVideoStatus(task)}</div>` : ''}
                    </div>
                </td>
                <td>
                    <span class="location-text">${task.location}</span>
                </td>
                <td>
                    <span class="interval-text">${task.upload_interval}分钟</span>
                </td>
                <td>
                    <div class="task-actions">
                        ${!isMultiUploading ? `
                            <button class="danger-button small" onclick="deleteTask(${task.id})" title="删除任务">
                                <i class="ri-delete-bin-line"></i>
                            </button>
                        ` : ''}
                        <button class="secondary-button small" onclick="viewTaskDetails(${task.id})" title="查看详情">
                            <i class="ri-eye-line"></i>
                        </button>
                    </div>
                </td>
            `;
            
            multiTaskTableBody.appendChild(row);
        });
    }
    
    // 获取任务行样式类
    function getTaskRowClass(status) {
        switch (status) {
            case 'waiting': return 'task-waiting';
            case 'uploading': return 'task-uploading';
            case 'completed': return 'task-completed';
            case 'failed': return 'task-failed';
            case 'stopped': return 'task-stopped';
            default: return '';
        }
    }
    
    // 获取任务状态文本
    function getTaskStatusText(task) {
        switch (task.status) {
            case 'waiting': return '等待中';
            case 'uploading': return '上传中';
            case 'completed': return '已完成';
            case 'failed': return '失败';
            case 'stopped': return '已停止';
            default: return task.status;
        }
    }
    
    // 获取当前视频状态（处理已完成任务的显示）
    function getCurrentVideoStatus(task) {
        // 如果任务已完成，不显示current_video信息
        if (task.status === 'completed') {
            return '';
        }
        return task.current_video || '';
    }
    
    // 更新多账号上传按钮状态
    function updateMultiUploadButtons() {
        if (isMultiUploading) {
            startMultiUploadBtn.classList.add('hidden');
            stopMultiUploadBtn.classList.remove('hidden');
        } else {
            startMultiUploadBtn.classList.remove('hidden');
            stopMultiUploadBtn.classList.add('hidden');
        }
    }
    
    // 开始多账号上传
    function startMultiUpload() {
        if (multiTasks.length === 0) {
            alert('请先添加上传任务');
            return;
        }
        
        // 检查是否有失效的cookie
        const failedTasks = multiTasks.filter(task => expiredCookies.has(task.cookie));
        if (failedTasks.length > 0) {
            const failedCookies = failedTasks.map(task => task.cookie).join(', ');
            if (!confirm(`检测到失效Cookie: ${failedCookies}\n\n这些任务将被跳过，是否继续上传？`)) {
                return;
            }
        }
        
        const uploadMode = document.querySelector('input[name="upload-mode"]:checked').value;
        
        fetch('/api/multi_upload', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ mode: uploadMode })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                alert(`多账号上传已开始（${uploadMode === 'sequential' ? '轮询' : '并发'}模式）`);
                isMultiUploading = true;
                updateMultiUploadButtons();
                
                // 开始定期刷新状态
                if (multiUploadRefreshInterval) {
                    clearInterval(multiUploadRefreshInterval);
                }
                multiUploadRefreshInterval = setInterval(loadMultiTasks, 3000);
            } else {
                alert('启动多账号上传失败: ' + data.message);
            }
        })
        .catch(error => {
            console.error('启动多账号上传失败:', error);
            alert('启动多账号上传失败，请重试');
        });
    }
    
    // 停止多账号上传
    function stopMultiUpload() {
        if (!confirm('确定要停止多账号上传吗？')) {
            return;
        }
        
        fetch('/api/multi_upload/stop', {
            method: 'POST'
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                alert('多账号上传已停止');
                isMultiUploading = false;
                updateMultiUploadButtons();
                
                // 停止刷新
                if (multiUploadRefreshInterval) {
                    clearInterval(multiUploadRefreshInterval);
                    multiUploadRefreshInterval = null;
                }
                
                loadMultiTasks(); // 刷新状态
            } else {
                alert('停止上传失败: ' + data.message);
            }
        })
        .catch(error => {
            console.error('停止上传失败:', error);
            alert('停止上传失败，请重试');
        });
    }
    
    // 删除任务
    function deleteTask(taskId) {
        if (!confirm('确定要删除这个任务吗？')) {
            return;
        }
        
        fetch(`/api/multi_tasks/${taskId}`, {
            method: 'DELETE'
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                alert(data.message);
                loadMultiTasks(); // 刷新任务列表
            } else {
                alert('删除任务失败: ' + data.message);
            }
        })
        .catch(error => {
            console.error('删除任务失败:', error);
            alert('删除任务失败，请重试');
        });
    }
    
    // 清空所有任务
    function clearAllTasks() {
        if (multiTasks.length === 0) {
            alert('没有任务需要清空');
            return;
        }
        
        if (!confirm('确定要清空所有任务吗？此操作不可撤销。')) {
            return;
        }
        
        fetch('/api/multi_tasks/clear', {
            method: 'POST'
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                alert(data.message);
                loadMultiTasks(); // 刷新任务列表
            } else {
                alert('清空任务失败: ' + data.message);
            }
        })
        .catch(error => {
            console.error('清空任务失败:', error);
            alert('清空任务失败，请重试');
        });
    }
    
    // 查看任务详情
    function viewTaskDetails(taskId) {
        const task = multiTasks.find(t => t.id === taskId);
        if (!task) {
            alert('任务不存在');
            return;
        }
        
        const publishInfo = task.publish_type === 'schedule' 
            ? `定时发布：${task.publish_date} ${task.publish_hour}:${task.publish_minute}`
            : '立即发布';
        
        const videoList = task.videos.slice(0, 10).map(v => `• ${v.split('/').pop()}`).join('\n');
        const moreVideos = task.videos.length > 10 ? `\n... 还有 ${task.videos.length - 10} 个视频` : '';
        
        alert(`任务详情：
        
账号：${task.cookie}
状态：${getTaskStatusText(task)}
视频数量：${task.total_videos}
已完成：${task.completed_videos}
上传位置：${task.location}
上传间隔：${task.upload_interval}分钟
发布方式：${publishInfo}
创建时间：${task.created_time}

视频列表：
${videoList}${moreVideos}`);
    }
    
    // 开始多任务状态刷新
    function startMultiTaskRefresh() {
        // 每3秒刷新一次任务状态（无论是否在上传）
        setInterval(() => {
            loadMultiTasks();
        }, 3000);
        
        // 每60秒刷新一次Cookie列表（减少频率避免用户选择被重置）
        setInterval(() => {
            // 只有在没有用户正在操作时才刷新Cookie列表
            if (!document.querySelector('#cookie-select:focus')) {
                loadCookies();
                loadTaskCookieOptions();
            }
        }, 60000);
        
        // 每30秒刷新一次指纹数据
        setInterval(() => {
            loadFingerprints();
        }, 30000);
        
        // 每45秒刷新一次代理数据
        setInterval(() => {
            loadProxies();
            loadProxyAssignments();
        }, 45000);
    }
    
    // 页面初始化
    initTimeSelectors();
    loadCookies();
    loadVideos();
    loadProxies();
    loadProxyAssignments();
    initWebSocket();
    setupFingerprintEvents();
    initMultiTaskManagement(); // 初始化多账号任务管理
    
    // 页面可见性检测 - 当页面重新获得焦点时刷新数据
    let lastVisibilityChange = 0;
    document.addEventListener('visibilitychange', function() {
        if (!document.hidden) {
            const now = Date.now();
            // 避免频繁刷新：只有在页面隐藏超过30秒后重新可见时才刷新
            if (now - lastVisibilityChange > 30000) {
                setTimeout(() => {
                    console.log('页面长时间后重新获得焦点，刷新数据...');
                    // 只有在没有用户正在操作时才刷新Cookie列表
                    if (!document.querySelector('#cookie-select:focus')) {
                        loadCookies();
                        loadTaskCookieOptions();
                    }
                    loadMultiTasks();
                    loadFingerprints();
                    loadProxies();
                    loadProxyAssignments();
                }, 1000);
            }
        } else {
            lastVisibilityChange = Date.now();
        }
    });
    
    // 绑定事件监听器
    cookieSelect.addEventListener('change', function() {
        // 记录手动选择时间
        lastCookieManualSelection = Date.now();
        console.log('用户手动选择Cookie，启动保护期');
        updateSelectedCookieIndicator();
    });
    generateCookieBtn.addEventListener('click', generateCookie);
    deleteCookieBtn.addEventListener('click', deleteCookie);
    startUploadBtn.addEventListener('click', startUpload);
    publishNowRadio.addEventListener('change', toggleScheduleOptions);
    publishScheduleRadio.addEventListener('change', toggleScheduleOptions);
    
    // 全局刷新函数
    function refreshAllData() {
        const refreshBtn = document.getElementById('floating-refresh-btn');
        if (refreshBtn) {
            refreshBtn.classList.add('refreshing');
            refreshBtn.style.pointerEvents = 'none';
        }
        
        console.log('开始全局数据刷新...');
        
        // 清空已选择的视频
        selectedVideos.length = 0;
        updateSelectedVideosList();
        
        // 并行刷新所有数据
        Promise.all([
            fetch('/api/cookies').then(r => r.json()).then(() => loadCookies()),
            fetch('/api/multi_tasks').then(r => r.json()).then(() => loadMultiTasks()),
            fetch('/api/fingerprints').then(r => r.json()).then(() => loadFingerprints()),
            fetch('/api/proxies').then(r => r.json()).then(() => loadProxies()),
            fetch('/api/proxy_mappings').then(r => r.json()).then(() => loadProxyAssignments()),
            fetch('/api/videos').then(r => r.json()).then(() => loadVideos())
        ]).then(() => {
            console.log('全局数据刷新完成');
            // 刷新任务Cookie选项
            loadTaskCookieOptions();
            
            // 显示成功提示
            showSuccessMessage('✅ 数据刷新完成，已清空视频选择');
        }).catch(error => {
            console.error('数据刷新失败:', error);
            alert('数据刷新失败，请检查网络连接');
        }).finally(() => {
            if (refreshBtn) {
                refreshBtn.classList.remove('refreshing');
                refreshBtn.style.pointerEvents = 'auto';
            }
        });
    }
    
    // 视频删除管理相关变量
    let remoteVideosList = [];
    let selectedRemoteVideos = [];
    let currentDeleteAccount = null;
    
    // 视频删除管理功能
    function initVideoDeleteManagement() {
        // 初始化删除账号选择器
        loadDeleteCookieOptions();
        
        // 监听WebSocket删除相关事件
        if (socket) {
            socket.on('video_list_result', handleVideoListResult);
            socket.on('video_list_error', handleVideoListError);
            socket.on('delete_status_update', handleDeleteStatusUpdate);
            socket.on('delete_completed', handleDeleteCompleted);
            socket.on('delete_error', handleDeleteError);
        }
    }
    
    function loadDeleteCookieOptions() {
        const deleteCookieSelect = document.getElementById('delete-cookie-select');
        if (!deleteCookieSelect) return;
        
        fetch('/api/cookies')
            .then(response => response.json())
            .then(data => {
                const cookies = data.cookies || [];
                deleteCookieSelect.innerHTML = '<option value="">请选择Cookie</option>';
                
                cookies.forEach(cookie => {
                    const option = document.createElement('option');
                    option.value = cookie.filename;
                    option.textContent = cookie.name;
                    if (cookie.expired) {
                        option.style.color = 'rgb(255, 68, 68)';
                        option.textContent += ' (已过期)';
                    }
                    deleteCookieSelect.appendChild(option);
                });
            })
            .catch(error => {
                console.error('加载删除Cookie选项失败:', error);
            });
    }
    
    function getRemoteVideos() {
        const deleteCookieSelect = document.getElementById('delete-cookie-select');
        const remoteVideosStatus = document.getElementById('remote-videos-status');
        const remoteVideosContainer = document.getElementById('remote-videos-container');
        
        const selectedCookie = deleteCookieSelect.value;
        if (!selectedCookie) {
            alert('请先选择一个账号');
            return;
        }
        
        currentDeleteAccount = selectedCookie;
        
        // 显示加载状态
        remoteVideosStatus.classList.remove('hidden');
        remoteVideosContainer.classList.add('hidden');
        remoteVideosStatus.innerHTML = '<i class="ri-loader-line spinning"></i> 正在获取视频列表...';
        
        // 请求获取视频列表
        fetch('/api/videos/list_remote', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                account_file: selectedCookie
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                console.log('获取视频列表请求已发送，等待结果...');
            } else {
                throw new Error(data.message);
            }
        })
        .catch(error => {
            console.error('获取视频列表失败:', error);
            remoteVideosStatus.classList.add('hidden');
            alert('获取视频列表失败: ' + error.message);
        });
    }
    
    function handleVideoListResult(data) {
        const remoteVideosStatus = document.getElementById('remote-videos-status');
        const remoteVideosContainer = document.getElementById('remote-videos-container');
        
        console.log('收到视频列表结果:', data);
        
        remoteVideosStatus.classList.add('hidden');
        
        if (data.result && data.result.success) {
            remoteVideosList = data.result.videos || [];
            selectedRemoteVideos = [];
            
            // 更新表格
            updateRemoteVideosTable();
            remoteVideosContainer.classList.remove('hidden');
            
            console.log(`成功获取 ${remoteVideosList.length} 个视频`);
        } else {
            const message = data.result ? data.result.message : '未知错误';
            alert('获取视频列表失败: ' + message);
            console.error('视频列表获取失败:', data);
        }
    }
    
    function handleVideoListError(data) {
        const remoteVideosStatus = document.getElementById('remote-videos-status');
        
        remoteVideosStatus.classList.add('hidden');
        alert('获取视频列表出错: ' + data.error);
        console.error('视频列表获取错误:', data);
    }
    
    function handleVideoListProgress(data) {
        const remoteVideosStatus = document.getElementById('remote-videos-status');
        
        if (remoteVideosStatus && !remoteVideosStatus.classList.contains('hidden')) {
            remoteVideosStatus.innerHTML = `<i class="ri-loader-line spinning"></i> ${data.status}`;
        }
        console.log('视频列表加载进度:', data.status);
    }
    
    function updateRemoteVideosTable() {
        const tableBody = document.getElementById('remote-videos-table-body');
        if (!tableBody) return;
        
        tableBody.innerHTML = '';
        
        if (remoteVideosList.length === 0) {
            const emptyRow = document.createElement('tr');
            emptyRow.className = 'empty-row';
            emptyRow.innerHTML = '<td colspan="7" class="empty-cell"><i class="ri-inbox-line"></i> 没有找到视频</td>';
            tableBody.appendChild(emptyRow);
            return;
        }
        
        remoteVideosList.forEach((video, index) => {
            const row = document.createElement('tr');
            row.className = video.can_delete ? '' : 'disabled-row';
            
            // 根据视频状态确定状态徽章样式
            let statusBadgeClass = 'status-unknown';
            let statusIcon = '';
            
            if (video.status === '仅自己可见') {
                statusBadgeClass = 'status-private';
                statusIcon = '<i class="ri-lock-line"></i> ';
            } else if (video.status === '公开') {
                statusBadgeClass = 'status-published';
                statusIcon = '<i class="ri-global-line"></i> ';
            } else if (video.status === '好友可见') {
                statusBadgeClass = 'status-friends';
                statusIcon = '<i class="ri-team-line"></i> ';
            } else if (video.status === '已发布') {
                statusBadgeClass = 'status-published';
                statusIcon = '<i class="ri-global-line"></i> ';
            } else {
                statusBadgeClass = 'status-other';
                statusIcon = '<i class="ri-question-line"></i> ';
            }
            
            // 构建播放数据显示
            let metricsDisplay = '';
            if (video.metrics) {
                const playCount = video.metrics['播放'] || '0';
                const likeCount = video.metrics['点赞'] || '0';
                const commentCount = video.metrics['评论'] || '0';
                const shareCount = video.metrics['分享'] || '0';
                
                metricsDisplay = `
                    <div class="video-metrics">
                        <span class="metric-item">
                            <i class="ri-play-circle-line"></i> ${playCount}
                        </span>
                        <span class="metric-item">
                            <i class="ri-heart-line"></i> ${likeCount}
                        </span>
                        <span class="metric-item">
                            <i class="ri-chat-3-line"></i> ${commentCount}
                        </span>
                        <span class="metric-item">
                            <i class="ri-share-line"></i> ${shareCount}
                        </span>
                    </div>
                `;
            } else {
                metricsDisplay = video.play_count || '0';
            }
            
            row.innerHTML = `
                <td>
                    <input type="checkbox" 
                           ${video.can_delete ? '' : 'disabled'} 
                           onchange="toggleRemoteVideoSelection(${index})" 
                           ${selectedRemoteVideos.includes(index) ? 'checked' : ''}>
                </td>
                <td>${index + 1}</td>
                <td class="video-title" title="${video.title}">
                    ${video.title}
                    ${video.is_disabled ? '<i class="ri-error-warning-line disabled-indicator" title="视频被禁用"></i>' : ''}
                </td>
                <td>${video.publish_time}</td>
                <td>
                    <span class="status-badge ${statusBadgeClass}">
                        ${statusIcon}${video.status}
                    </span>
                </td>
                <td class="metrics-cell">${metricsDisplay}</td>
                <td>
                    <span class="delete-status ${video.can_delete ? 'can-delete' : 'cannot-delete'}">
                        <i class="${video.can_delete ? 'ri-check-line' : 'ri-close-line'}"></i>
                        ${video.can_delete ? '可删除' : '不可删除'}
                    </span>
                </td>
            `;
            
            tableBody.appendChild(row);
        });
        
        updateDeleteButtonStates();
    }
    
    function toggleRemoteVideoSelection(index) {
        const video = remoteVideosList[index];
        if (!video.can_delete) return;
        
        const selectedIndex = selectedRemoteVideos.indexOf(index);
        if (selectedIndex > -1) {
            selectedRemoteVideos.splice(selectedIndex, 1);
        } else {
            selectedRemoteVideos.push(index);
        }
        
        updateDeleteButtonStates();
        updateSelectAllRemoteCheckbox();
    }
    
    function selectAllRemoteVideos() {
        selectedRemoteVideos = [];
        remoteVideosList.forEach((video, index) => {
            if (video.can_delete) {
                selectedRemoteVideos.push(index);
            }
        });
        updateRemoteVideosTable();
    }
    
    function clearAllRemoteVideos() {
        selectedRemoteVideos = [];
        updateRemoteVideosTable();
    }
    
    function toggleAllRemoteVideos() {
        const selectAllCheckbox = document.getElementById('select-all-remote');
        
        if (selectAllCheckbox.checked) {
            selectAllRemoteVideos();
        } else {
            clearAllRemoteVideos();
        }
    }
    
    function updateSelectAllRemoteCheckbox() {
        const selectAllCheckbox = document.getElementById('select-all-remote');
        if (!selectAllCheckbox) return;
        
        const deletableVideos = remoteVideosList.filter(video => video.can_delete);
        const selectedDeletableVideos = selectedRemoteVideos.filter(index => remoteVideosList[index].can_delete);
        
        selectAllCheckbox.checked = deletableVideos.length > 0 && selectedDeletableVideos.length === deletableVideos.length;
        selectAllCheckbox.indeterminate = selectedDeletableVideos.length > 0 && selectedDeletableVideos.length < deletableVideos.length;
    }
    
    function updateDeleteButtonStates() {
        const deleteSelectedBtn = document.getElementById('delete-selected-videos-btn');
        if (deleteSelectedBtn) {
            deleteSelectedBtn.disabled = selectedRemoteVideos.length === 0;
        }
        
        updateSelectAllRemoteCheckbox();
    }
    
    function deleteSelectedVideos() {
        if (selectedRemoteVideos.length === 0) {
            alert('请先选择要删除的视频');
            return;
        }
        
        const selectedTitles = selectedRemoteVideos.map(index => remoteVideosList[index].title);
        const maxCount = document.getElementById('max-delete-count').value;
        
        if (!confirm(`确定要删除选中的 ${selectedRemoteVideos.length} 个视频吗？\n\n删除的视频：\n${selectedTitles.slice(0, 5).join('\n')}${selectedTitles.length > 5 ? '\n...' : ''}\n\n此操作不可恢复！`)) {
            return;
        }
        
        startDeleteProcess({
            account_file: currentDeleteAccount,
            delete_type: 'selected',
            video_titles: selectedTitles,
            max_count: maxCount ? parseInt(maxCount) : null
        });
    }
    
    function deleteAllVideos() {
        const deletableVideos = remoteVideosList.filter(video => video.can_delete);
        
        if (deletableVideos.length === 0) {
            alert('没有可删除的视频');
            return;
        }
        
        const maxCount = document.getElementById('max-delete-count').value;
        const actualDeleteCount = maxCount ? Math.min(parseInt(maxCount), deletableVideos.length) : deletableVideos.length;
        
        if (!confirm(`确定要删除所有 ${actualDeleteCount} 个可删除的视频吗？\n\n此操作不可恢复！`)) {
            return;
        }
        
        startDeleteProcess({
            account_file: currentDeleteAccount,
            delete_type: 'all',
            max_count: maxCount ? parseInt(maxCount) : null
        });
    }
    
    function startDeleteProcess(deleteConfig) {
        const deleteStatusContainer = document.getElementById('delete-status-container');
        const deleteStatus = document.getElementById('delete-status');
        const deleteProgressBar = document.getElementById('delete-progress-bar');
        const deleteProgressText = document.getElementById('delete-progress-text');
        
        // 显示删除状态区域
        deleteStatusContainer.classList.remove('hidden');
        deleteStatus.innerHTML = '<i class="ri-loader-line spinning"></i> 正在启动删除任务...';
        deleteProgressBar.style.width = '0%';
        deleteProgressText.textContent = '0 / ?';
        
        // 禁用删除按钮
        const deleteSelectedBtn = document.getElementById('delete-selected-videos-btn');
        const deleteAllBtn = document.getElementById('delete-all-videos-btn');
        if (deleteSelectedBtn) deleteSelectedBtn.disabled = true;
        if (deleteAllBtn) deleteAllBtn.disabled = true;
        
        fetch('/api/videos/delete', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(deleteConfig)
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                deleteStatus.innerHTML = '<i class="ri-loader-line spinning"></i> 删除任务已启动，正在处理...';
            } else {
                throw new Error(data.message);
            }
        })
        .catch(error => {
            console.error('启动删除任务失败:', error);
            deleteStatus.innerHTML = '<i class="ri-error-warning-line"></i> 启动删除任务失败: ' + error.message;
            // 重新启用删除按钮
            updateDeleteButtonStates();
            if (deleteAllBtn) deleteAllBtn.disabled = false;
        });
    }
    
    function handleDeleteStatusUpdate(data) {
        const deleteStatus = document.getElementById('delete-status');
        if (deleteStatus) {
            deleteStatus.innerHTML = `<i class="ri-loader-line spinning"></i> ${data.status}`;
        }
        console.log('删除状态更新:', data.status);
    }
    
    function handleDeleteCompleted(data) {
        const deleteStatus = document.getElementById('delete-status');
        const deleteProgressBar = document.getElementById('delete-progress-bar');
        const deleteProgressText = document.getElementById('delete-progress-text');
        
        console.log('删除完成:', data);
        
        if (data.result.success) {
            if (deleteStatus) {
                deleteStatus.innerHTML = `<i class="ri-check-line"></i> ${data.result.message}`;
            }
            if (deleteProgressBar) {
                deleteProgressBar.style.width = '100%';
            }
            if (deleteProgressText) {
                deleteProgressText.textContent = `${data.result.deleted_count} / ${data.result.total_videos}`;
            }
            
            // 刷新视频列表
            setTimeout(() => {
                getRemoteVideos();
            }, 2000);
        } else {
            if (deleteStatus) {
                deleteStatus.innerHTML = `<i class="ri-error-warning-line"></i> 删除失败: ${data.result.message}`;
            }
        }
        
        // 重新启用删除按钮
        updateDeleteButtonStates();
        const deleteAllBtn = document.getElementById('delete-all-videos-btn');
        if (deleteAllBtn) deleteAllBtn.disabled = false;
    }
    
    function handleDeleteError(data) {
        const deleteStatus = document.getElementById('delete-status');
        
        if (deleteStatus) {
            deleteStatus.innerHTML = `<i class="ri-error-warning-line"></i> 删除出错: ${data.error}`;
        }
        console.error('删除错误:', data);
        
        // 重新启用删除按钮
        updateDeleteButtonStates();
        const deleteAllBtn = document.getElementById('delete-all-videos-btn');
        if (deleteAllBtn) deleteAllBtn.disabled = false;
    }

    // 初始化视频删除管理
    if (document.getElementById('delete-cookie-select')) {
        initVideoDeleteManagement();
    }
    
    // 初始化视频权限设置管理
    if (document.getElementById('permission-cookie-select')) {
        initVideoPermissionManagement();
    }
    
    // 将函数暴露到全局作用域，供HTML调用
    window.selectAllVideos = selectAllVideos;
    window.clearAllVideos = clearAllVideos;
    window.validateSelectedCookie = validateSelectedCookie;
    window.clearExpiredStatus = clearExpiredStatus;
    window.refreshAllData = refreshAllData;
    
    // 多账号任务管理函数暴露
    window.addAccountTask = addAccountTask;
    window.copySelectedVideos = copySelectedVideos;
    window.startMultiUpload = startMultiUpload;
    window.stopMultiUpload = stopMultiUpload;
    window.deleteTask = deleteTask;
    window.clearAllTasks = clearAllTasks;
    window.viewTaskDetails = viewTaskDetails;
    
    // 视频删除管理函数暴露
    window.getRemoteVideos = getRemoteVideos;
    window.selectAllRemoteVideos = selectAllRemoteVideos;
    window.clearAllRemoteVideos = clearAllRemoteVideos;
    window.toggleAllRemoteVideos = toggleAllRemoteVideos;
    window.deleteSelectedVideos = deleteSelectedVideos;
    window.deleteAllVideos = deleteAllVideos;
    window.toggleRemoteVideoSelection = toggleRemoteVideoSelection;
    
    // ===========================================
    // 视频权限设置管理功能
    // ===========================================

    let permissionVideosList = [];
    let selectedPermissionVideos = [];
    let currentPermissionAccount = '';

    function initVideoPermissionManagement() {
        // 权限设置socket事件监听
        if (socket) {
            socket.on('permission_status_update', handlePermissionStatusUpdate);
            socket.on('permission_completed', handlePermissionCompleted);
            socket.on('permission_error', handlePermissionError);
            socket.on('permission_video_list_result', handlePermissionVideoListResult);
            socket.on('permission_video_list_error', handlePermissionVideoListError);
        }
        
        loadPermissionCookieOptions();
    }

    function loadPermissionCookieOptions() {
        fetch('/api/cookies')
            .then(response => response.json())
            .then(data => {
                const select = document.getElementById('permission-cookie-select');
                if (!select) return;
                
                select.innerHTML = '<option value="">请选择Cookie</option>';
                data.cookies.forEach(cookie => {
                    const option = document.createElement('option');
                    option.value = cookie.filename;
                    option.textContent = cookie.name;
                    if (cookie.expired) {
                        option.style.color = 'rgb(255, 68, 68)';
                        option.textContent += ' (已过期)';
                    }
                    select.appendChild(option);
                });
            })
            .catch(error => {
                console.error('加载权限设置Cookie选项失败:', error);
            });
    }

    function getPermissionVideos() {
        const accountSelect = document.getElementById('permission-cookie-select');
        const permissionType = document.getElementById('permission-type-select').value;
        
        if (!accountSelect.value) {
            alert('请先选择账号');
            return;
        }
        
        if (!permissionType) {
            alert('请先选择权限类型');
            return;
        }
        
        currentPermissionAccount = accountSelect.value;
        
        const permissionVideosStatus = document.getElementById('permission-videos-status');
        const permissionVideosContainer = document.getElementById('permission-videos-container');
        
        permissionVideosStatus.classList.remove('hidden');
        permissionVideosContainer.classList.add('hidden');
        permissionVideosStatus.innerHTML = '<i class="ri-loader-line spinning"></i> 正在获取视频列表...';
        
        fetch('/api/videos/list_remote_permissions', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                account_file: accountSelect.value
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                // 状态消息会通过socket更新
            } else {
                throw new Error(data.message);
            }
        })
        .catch(error => {
            console.error('获取权限视频列表失败:', error);
            permissionVideosStatus.classList.add('hidden');
            alert('获取视频列表失败: ' + error.message);
        });
    }

    function selectAllPermissionVideos() {
        selectedPermissionVideos = [];
        permissionVideosList.forEach((video, index) => {
            selectedPermissionVideos.push(index);
        });
        updatePermissionVideosTable();
    }

    function clearAllPermissionVideos() {
        selectedPermissionVideos = [];
        updatePermissionVideosTable();
    }

    function toggleAllPermissionVideos() {
        const selectAllCheckbox = document.getElementById('select-all-permission');
        
        if (selectAllCheckbox.checked) {
            selectAllPermissionVideos();
        } else {
            clearAllPermissionVideos();
        }
    }

    function togglePermissionVideoSelection(index) {
        const selectedIndex = selectedPermissionVideos.indexOf(index);
        if (selectedIndex > -1) {
            selectedPermissionVideos.splice(selectedIndex, 1);
        } else {
            selectedPermissionVideos.push(index);
        }
        
        updatePermissionButtonStates();
        updateSelectAllPermissionCheckbox();
    }

    function updatePermissionVideosTable() {
        const tableBody = document.getElementById('permission-videos-table-body');
        if (!tableBody) return;
        
        tableBody.innerHTML = '';
        
        if (permissionVideosList.length === 0) {
            const emptyRow = document.createElement('tr');
            emptyRow.className = 'empty-row';
            emptyRow.innerHTML = '<td colspan="7" class="empty-cell"><i class="ri-inbox-line"></i> 没有找到视频</td>';
            tableBody.appendChild(emptyRow);
            return;
        }
        
        permissionVideosList.forEach((video, index) => {
            const row = document.createElement('tr');
            
            // 根据视频状态确定状态徽章样式
            let statusBadgeClass = 'status-unknown';
            let statusIcon = '';
            
            if (video.status === '仅自己可见') {
                statusBadgeClass = 'status-private';
                statusIcon = '<i class="ri-lock-line"></i> ';
            } else if (video.status === '公开') {
                statusBadgeClass = 'status-published';
                statusIcon = '<i class="ri-global-line"></i> ';
            } else if (video.status === '好友可见') {
                statusBadgeClass = 'status-friends';
                statusIcon = '<i class="ri-team-line"></i> ';
            } else if (video.status === '已发布') {
                statusBadgeClass = 'status-published';
                statusIcon = '<i class="ri-global-line"></i> ';
            } else {
                statusBadgeClass = 'status-other';
                statusIcon = '<i class="ri-question-line"></i> ';
            }
            
            // 构建播放数据显示
            let metricsDisplay = '';
            if (video.metrics) {
                const playCount = video.metrics['播放'] || '0';
                const likeCount = video.metrics['点赞'] || '0';
                const commentCount = video.metrics['评论'] || '0';
                const shareCount = video.metrics['分享'] || '0';
                
                metricsDisplay = `
                    <div class="video-metrics">
                        <span class="metric-item">
                            <i class="ri-play-circle-line"></i> ${playCount}
                        </span>
                        <span class="metric-item">
                            <i class="ri-heart-line"></i> ${likeCount}
                        </span>
                        <span class="metric-item">
                            <i class="ri-chat-3-line"></i> ${commentCount}
                        </span>
                        <span class="metric-item">
                            <i class="ri-share-line"></i> ${shareCount}
                        </span>
                    </div>
                `;
            } else {
                metricsDisplay = video.play_count || '0';
            }
            
            row.innerHTML = `
                <td>
                    <input type="checkbox" 
                           onchange="togglePermissionVideoSelection(${index})" 
                           ${selectedPermissionVideos.includes(index) ? 'checked' : ''}>
                </td>
                <td>${index + 1}</td>
                <td class="video-title" title="${video.title}">
                    ${video.title}
                    ${video.is_disabled ? '<i class="ri-error-warning-line disabled-indicator" title="视频被禁用"></i>' : ''}
                </td>
                <td>${video.publish_time}</td>
                <td>
                    <span class="status-badge ${statusBadgeClass}">
                        ${statusIcon}${video.status}
                    </span>
                </td>
                <td class="metrics-cell">${metricsDisplay}</td>
                <td>
                    <span class="permission-status ready">
                        <i class="ri-checkbox-circle-line"></i>
                        等待设置
                    </span>
                </td>
            `;
            
            tableBody.appendChild(row);
        });
        
        updatePermissionButtonStates();
    }

    function updateSelectAllPermissionCheckbox() {
        const selectAllCheckbox = document.getElementById('select-all-permission');
        if (!selectAllCheckbox) return;
        
        selectAllCheckbox.checked = permissionVideosList.length > 0 && selectedPermissionVideos.length === permissionVideosList.length;
        selectAllCheckbox.indeterminate = selectedPermissionVideos.length > 0 && selectedPermissionVideos.length < permissionVideosList.length;
    }

    function updatePermissionButtonStates() {
        const setSelectedBtn = document.getElementById('set-selected-permissions-btn');
        if (setSelectedBtn) {
            setSelectedBtn.disabled = selectedPermissionVideos.length === 0;
        }
        
        updateSelectAllPermissionCheckbox();
    }

    function setSelectedPermissions() {
        const permissionType = document.getElementById('permission-type-select').value;
        
        if (selectedPermissionVideos.length === 0) {
            alert('请先选择要设置的视频');
            return;
        }
        
        if (!permissionType) {
            alert('请先选择权限类型');
            return;
        }
        
        const selectedTitles = selectedPermissionVideos.map(index => permissionVideosList[index].title);
        const maxCount = document.getElementById('max-permission-count').value;
        
        const permissionNames = {"0": "公开", "1": "仅自己可见", "2": "好友可见"};
        const permissionName = permissionNames[permissionType];
        
        if (!confirm(`确定要将选中的 ${selectedPermissionVideos.length} 个视频设置为 ${permissionName} 吗？\n\n设置的视频：\n${selectedTitles.slice(0, 5).join('\n')}${selectedTitles.length > 5 ? '\n...' : ''}\n\n此操作不可恢复！`)) {
            return;
        }
        
        startPermissionProcess({
            account_file: currentPermissionAccount,
            permission_value: permissionType,
            video_titles: selectedTitles,
            max_count: maxCount ? parseInt(maxCount) : null
        });
    }

    function setAllPermissions() {
        const permissionType = document.getElementById('permission-type-select').value;
        
        if (permissionVideosList.length === 0) {
            alert('没有可设置的视频');
            return;
        }
        
        if (!permissionType) {
            alert('请先选择权限类型');
            return;
        }
        
        const maxCount = document.getElementById('max-permission-count').value;
        const actualSetCount = maxCount ? Math.min(parseInt(maxCount), permissionVideosList.length) : permissionVideosList.length;
        
        const permissionNames = {"0": "公开", "1": "仅自己可见", "2": "好友可见"};
        const permissionName = permissionNames[permissionType];
        
        if (!confirm(`确定要将所有 ${actualSetCount} 个视频设置为 ${permissionName} 吗？\n\n此操作不可恢复！`)) {
            return;
        }
        
        startPermissionProcess({
            account_file: currentPermissionAccount,
            permission_value: permissionType,
            max_count: maxCount ? parseInt(maxCount) : null
        });
    }

    function startPermissionProcess(permissionConfig) {
        const permissionStatusContainer = document.getElementById('permission-status-container');
        const permissionStatus = document.getElementById('permission-status');
        const permissionProgressBar = document.getElementById('permission-progress-bar');
        const permissionProgressText = document.getElementById('permission-progress-text');
        
        // 显示权限设置状态区域
        permissionStatusContainer.classList.remove('hidden');
        permissionStatus.innerHTML = '<i class="ri-loader-line spinning"></i> 正在启动权限设置任务...';
        permissionProgressBar.style.width = '0%';
        permissionProgressText.textContent = '0 / ?';
        
        // 禁用设置按钮
        const setSelectedBtn = document.getElementById('set-selected-permissions-btn');
        const setAllBtn = document.getElementById('set-all-permissions-btn');
        if (setSelectedBtn) setSelectedBtn.disabled = true;
        if (setAllBtn) setAllBtn.disabled = true;
        
        fetch('/api/videos/set_permissions', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(permissionConfig)
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                permissionStatus.innerHTML = '<i class="ri-loader-line spinning"></i> 权限设置任务已启动，正在处理...';
            } else {
                throw new Error(data.message);
            }
        })
        .catch(error => {
            console.error('启动权限设置任务失败:', error);
            permissionStatus.innerHTML = '<i class="ri-error-warning-line"></i> 启动权限设置任务失败: ' + error.message;
            // 重新启用设置按钮
            updatePermissionButtonStates();
            if (setAllBtn) setAllBtn.disabled = false;
        });
    }

    function handlePermissionStatusUpdate(data) {
        const permissionStatus = document.getElementById('permission-status');
        if (permissionStatus) {
            permissionStatus.innerHTML = `<i class="ri-loader-line spinning"></i> ${data.status}`;
        }
        console.log('权限设置状态更新:', data.status);
    }

    function handlePermissionCompleted(data) {
        const permissionStatus = document.getElementById('permission-status');
        const permissionProgressBar = document.getElementById('permission-progress-bar');
        const permissionProgressText = document.getElementById('permission-progress-text');
        
        console.log('权限设置完成:', data);
        
        if (data.result.success) {
            if (permissionStatus) {
                permissionStatus.innerHTML = `<i class="ri-check-line"></i> ${data.result.message}`;
            }
            if (permissionProgressBar) {
                permissionProgressBar.style.width = '100%';
            }
            if (permissionProgressText) {
                permissionProgressText.textContent = `${data.result.success_count} / ${data.result.total_videos}`;
            }
            
            // 刷新视频列表
            setTimeout(() => {
                getPermissionVideos();
            }, 2000);
        } else {
            if (permissionStatus) {
                permissionStatus.innerHTML = `<i class="ri-error-warning-line"></i> 权限设置失败: ${data.result.message}`;
            }
        }
        
        // 重新启用设置按钮
        updatePermissionButtonStates();
        const setAllBtn = document.getElementById('set-all-permissions-btn');
        if (setAllBtn) setAllBtn.disabled = false;
    }

    function handlePermissionError(data) {
        const permissionStatus = document.getElementById('permission-status');
        
        if (permissionStatus) {
            permissionStatus.innerHTML = `<i class="ri-error-warning-line"></i> 权限设置出错: ${data.error}`;
        }
        console.error('权限设置错误:', data);
        
        // 重新启用设置按钮
        updatePermissionButtonStates();
        const setAllBtn = document.getElementById('set-all-permissions-btn');
        if (setAllBtn) setAllBtn.disabled = false;
    }

    function handlePermissionVideoListResult(data) {
        const permissionVideosStatus = document.getElementById('permission-videos-status');
        const permissionVideosContainer = document.getElementById('permission-videos-container');
        
        permissionVideosStatus.classList.add('hidden');
        
        if (data.result && data.result.success) {
            permissionVideosList = data.result.videos || [];
            selectedPermissionVideos = [];
            
            updatePermissionVideosTable();
            permissionVideosContainer.classList.remove('hidden');
        } else {
            alert('获取权限视频列表失败: ' + (data.result ? data.result.message : '未知错误'));
        }
    }

    function handlePermissionVideoListError(data) {
        const permissionVideosStatus = document.getElementById('permission-videos-status');
        
        permissionVideosStatus.textContent = '获取权限视频列表出错: ' + data.error;
        console.error('获取权限视频列表错误:', data);
    }
    
    function handlePermissionVideoListProgress(data) {
        const permissionVideosStatus = document.getElementById('permission-videos-status');
        
        if (permissionVideosStatus && !permissionVideosStatus.classList.contains('hidden')) {
            permissionVideosStatus.innerHTML = `<i class="ri-loader-line spinning"></i> ${data.status}`;
        }
        console.log('权限视频列表加载进度:', data.status);
    }
    



    
    // 压缩包上传函数
    function uploadArchive(input) {
        const file = input.files[0];
        if (!file) return;

        // 检查文件类型
        const allowedTypes = ['.zip', '.rar', '.7z'];
        const fileName = file.name.toLowerCase();
        const isValidType = allowedTypes.some(type => fileName.endsWith(type));
        
        if (!isValidType) {
            alert('仅支持 .zip、.rar、.7z 格式的压缩包');
            input.value = '';
            return;
        }

        // 检查文件大小 (限制为500MB)
        const maxSize = 500 * 1024 * 1024; // 500MB
        if (file.size > maxSize) {
            alert('压缩包文件过大，请选择小于500MB的文件');
            input.value = '';
            return;
        }

        // 显示上传进度
        const progressDialog = createUploadProgressDialog();
        document.body.appendChild(progressDialog);
        
        // 创建FormData
        const formData = new FormData();
        formData.append('archive', file);

        // 发送上传请求
        const xhr = new XMLHttpRequest();
        
        // 监听上传进度
        xhr.upload.addEventListener('progress', function(e) {
            if (e.lengthComputable) {
                const percentComplete = (e.loaded / e.total) * 100;
                updateUploadProgress(progressDialog, percentComplete, '正在上传压缩包...');
            }
        });

        // 监听响应
        xhr.addEventListener('load', function() {
            if (xhr.status === 200) {
                try {
                    const response = JSON.parse(xhr.responseText);
                    if (response.success) {
                        updateUploadProgress(progressDialog, 100, '上传完成，正在解压...');
                        // 开始解压处理
                        handleArchiveExtraction(progressDialog, response.task_id);
                    } else {
                        closeUploadProgress(progressDialog);
                        alert('上传失败: ' + response.message);
                    }
                } catch (e) {
                    closeUploadProgress(progressDialog);
                    alert('解析服务器响应失败');
                }
            } else {
                closeUploadProgress(progressDialog);
                alert('上传失败，服务器错误: ' + xhr.status);
            }
            input.value = ''; // 清空输入
        });

        xhr.addEventListener('error', function() {
            closeUploadProgress(progressDialog);
            alert('上传失败，网络错误');
            input.value = '';
        });

        // 发送请求
        xhr.open('POST', '/api/upload_archive');
        xhr.send(formData);
    }

    function createUploadProgressDialog() {
        const dialog = document.createElement('div');
        dialog.className = 'upload-progress-dialog';
        dialog.innerHTML = `
            <div class="upload-progress-content">
                <h3><i class="ri-folder-zip-line"></i> 压缩包上传</h3>
                <div class="progress-bar-container">
                    <div class="progress-bar" id="upload-progress-bar"></div>
                </div>
                <div class="progress-text" id="upload-progress-text">准备上传...</div>
                <div class="upload-details" id="upload-details"></div>
                <button class="cancel-btn" onclick="closeUploadProgress(this.closest('.upload-progress-dialog'))">
                    <i class="ri-close-line"></i> 关闭
                </button>
            </div>
        `;
        return dialog;
    }

    function updateUploadProgress(dialog, percent, message, details = '') {
        const progressBar = dialog.querySelector('#upload-progress-bar');
        const progressText = dialog.querySelector('#upload-progress-text');
        const detailsDiv = dialog.querySelector('#upload-details');
        
        progressBar.style.width = Math.min(percent, 100) + '%';
        progressText.textContent = message;
        if (details) {
            detailsDiv.textContent = details;
        }
    }

    function closeUploadProgress(dialog) {
        if (dialog && dialog.parentNode) {
            dialog.parentNode.removeChild(dialog);
        }
    }

    function handleArchiveExtraction(progressDialog, taskId) {
        // 轮询解压状态
        const checkStatus = () => {
            fetch(`/api/extract_status/${taskId}`)
                .then(response => response.json())
                .then(data => {
                    if (data.status === 'completed') {
                        updateUploadProgress(progressDialog, 100, '解压完成！', 
                            `成功解压 ${data.extracted_count} 个视频文件`);
                        
                        // 刷新视频列表
                        setTimeout(() => {
                            loadVideos();
                            closeUploadProgress(progressDialog);
                        }, 2000);
                        
                    } else if (data.status === 'error') {
                        updateUploadProgress(progressDialog, 100, '解压失败', data.error);
                        setTimeout(() => closeUploadProgress(progressDialog), 3000);
                        
                    } else if (data.status === 'processing') {
                        updateUploadProgress(progressDialog, 80, '正在解压...', data.message || '');
                        setTimeout(checkStatus, 1000);
                        
                    } else {
                        // 未知状态，继续检查
                        setTimeout(checkStatus, 1000);
                    }
                })
                .catch(error => {
                    console.error('检查解压状态失败:', error);
                    updateUploadProgress(progressDialog, 100, '检查状态失败', error.message);
                    setTimeout(() => closeUploadProgress(progressDialog), 3000);
                });
        };
        
        checkStatus();
    }

    // 视频权限设置函数暴露
    window.getPermissionVideos = getPermissionVideos;
    window.selectAllPermissionVideos = selectAllPermissionVideos;
    window.clearAllPermissionVideos = clearAllPermissionVideos;
    window.toggleAllPermissionVideos = toggleAllPermissionVideos;
    window.setSelectedPermissions = setSelectedPermissions;
    window.setAllPermissions = setAllPermissions;
    window.togglePermissionVideoSelection = togglePermissionVideoSelection;
    window.uploadArchive = uploadArchive;
    window.closeUploadProgress = closeUploadProgress;

    // 内容采集函数暴露
    window.selectAllResults = selectAllResults;
    window.clearAllSelections = clearAllSelections;
    window.downloadSingleVideo = downloadSingleVideo;
    window.viewVideoDetail = viewVideoDetail;
    window.getVideoFromUrl = getVideoFromUrl;
    window.copyToClipboard = copyToClipboard;

    // 初始化时间选择器、加载数据等
    initMultiTaskManagement();
    initVideoDeleteManagement();
    initVideoPermissionManagement();
    
    // 初始化抖音内容采集功能
    initContentCrawler();
    
    // 初始化Downloader服务控制
    initDownloaderService();
    
    // 确保下载进度面板初始隐藏
    const downloadProgressMessage = document.getElementById('download-progress-message');
    if (downloadProgressMessage) {
        downloadProgressMessage.classList.add('hidden');
    }
    
    // 确保采集状态消息初始隐藏
    const crawlerStatusMessage = document.getElementById('crawler-status-message');
    if (crawlerStatusMessage) {
        crawlerStatusMessage.classList.add('hidden');
        crawlerStatusMessage.innerHTML = ''; // 清空内容
    }
    
    // 确保采集进度条初始隐藏
    const crawlerProgress = document.getElementById('crawler-progress');
    if (crawlerProgress) {
        crawlerProgress.classList.add('hidden');
    }
    
    // 定期刷新所有数据
    startRefreshInterval();

    // ... existing code ...

    // 抖音内容采集功能初始化和相关函数
    function initContentCrawler() {
        // 初始化选项卡切换
        initCrawlerTabs();
        
        // 加载Cookie和代理选项到采集功能
        loadCrawlerOptions();
        
        // 设置事件监听器
        setupCrawlerEventListeners();
        
        // 初始化结果存储
        window.crawlerResults = [];
    }
    
    function initCrawlerTabs() {
        const tabButtons = document.querySelectorAll('.crawler-tabs .tab-btn');
        const tabContents = document.querySelectorAll('.tab-content');
        
        tabButtons.forEach(button => {
            button.addEventListener('click', function() {
                const targetTab = this.getAttribute('data-tab');
                
                // 移除所有活动状态
                tabButtons.forEach(btn => btn.classList.remove('active'));
                tabContents.forEach(content => content.classList.remove('active'));
                
                // 添加活动状态
                this.classList.add('active');
                document.getElementById(targetTab + '-tab').classList.add('active');
            });
        });
    }
    
    function loadCrawlerOptions() {
        // 加载Cookie选项
        const cookieSelects = [
            'search-cookie', 'detail-cookie', 'account-cookie', 'hot-cookie', 'download-cookie'
        ];
        
        fetch('/api/cookies')
            .then(response => response.json())
            .then(data => {
                const cookies = data.cookies || [];
                cookieSelects.forEach(selectId => {
                    const select = document.getElementById(selectId);
                    if (select) {
                        select.innerHTML = '<option value="">请选择Cookie</option>';
                        cookies.forEach(cookie => {
                            const option = document.createElement('option');
                            option.value = cookie.filename;
                            option.textContent = cookie.name;
                            select.appendChild(option);
                        });
                    }
                });
            })
            .catch(error => {
                console.error('加载Cookie选项失败:', error);
            });
        
        // 加载代理选项
        const proxySelects = [
            'search-proxy', 'detail-proxy', 'account-proxy', 'hot-proxy', 'link-proxy', 'download-proxy'
        ];
        
        fetch('/api/proxies')
            .then(response => response.json())
            .then(data => {
                const proxies = data.proxies || [];
                proxySelects.forEach(selectId => {
                    const select = document.getElementById(selectId);
                    if (select) {
                        select.innerHTML = '<option value="">不使用代理</option>';
                        proxies.forEach(proxy => {
                            const option = document.createElement('option');
                            option.value = proxy.url;
                            option.textContent = `${proxy.name} (${proxy.url})`;
                            select.appendChild(option);
                        });
                    }
                });
            })
            .catch(error => {
                console.error('加载代理选项失败:', error);
            });
    }
    
    function setupCrawlerEventListeners() {
        // 先移除可能存在的事件监听器，避免重复绑定
        const elements = [
            'start-search', 'get-detail', 'get-account', 'get-hot', 'parse-link',
            'export-results', 'batch-download', 'clear-results', 'confirm-download', 'cancel-download'
        ];
        
        elements.forEach(id => {
            const element = document.getElementById(id);
            if (element) {
                // 克隆元素来移除所有事件监听器
                const newElement = element.cloneNode(true);
                element.parentNode.replaceChild(newElement, element);
            }
        });
        
        // 重新绑定事件
        const searchBtn = document.getElementById('start-search');
        if (searchBtn) searchBtn.addEventListener('click', startVideoSearch);
        
        const detailBtn = document.getElementById('get-detail');
        if (detailBtn) detailBtn.addEventListener('click', getVideoDetail);
        
        const accountBtn = document.getElementById('get-account');
        if (accountBtn) accountBtn.addEventListener('click', getUserAccount);
        
        const hotBtn = document.getElementById('get-hot');
        if (hotBtn) hotBtn.addEventListener('click', getHotData);
        
        const parseBtn = document.getElementById('parse-link');
        if (parseBtn) parseBtn.addEventListener('click', parseLink);
        
        const exportBtn = document.getElementById('export-results');
        if (exportBtn) exportBtn.addEventListener('click', exportResults);
        
        const downloadBtn = document.getElementById('batch-download');
        if (downloadBtn) downloadBtn.addEventListener('click', batchDownload);
        
        const clearBtn = document.getElementById('clear-results');
        if (clearBtn) clearBtn.addEventListener('click', clearResults);
        
        // 下载设置面板事件监听器
        const confirmDownloadBtn = document.getElementById('confirm-download');
        if (confirmDownloadBtn) confirmDownloadBtn.addEventListener('click', confirmDownload);
        
        const cancelDownloadBtn = document.getElementById('cancel-download');
        if (cancelDownloadBtn) cancelDownloadBtn.addEventListener('click', cancelDownload);
        
        const stopDownloadBtn = document.getElementById('stop-download');
        if (stopDownloadBtn) stopDownloadBtn.addEventListener('click', stopDownload);
        
        const stopDownloadProgressBtn = document.getElementById('stop-download-progress');
        if (stopDownloadProgressBtn) stopDownloadProgressBtn.addEventListener('click', stopDownload);
        
        // 监听下载Cookie选择变化，启用/禁用确认按钮
        const downloadCookieSelect = document.getElementById('download-cookie');
        if (downloadCookieSelect) {
            downloadCookieSelect.addEventListener('change', function() {
                const confirmBtn = document.getElementById('confirm-download');
                if (confirmBtn) {
                    confirmBtn.disabled = !this.value;
                }
            });
        }
    }
    
    // 显示采集状态
    function showCrawlerStatus(message, type = 'info', icon = 'ri-loader-line spinning') {
        const statusElement = document.getElementById('crawler-status-message');
        const progressElement = document.getElementById('crawler-progress');
        
        statusElement.innerHTML = `<i class="${icon}"></i> ${message}`;
        statusElement.className = `status-message ${type}`;
        statusElement.classList.remove('hidden');
        
        // 只有在加载状态时才显示进度条
        if (icon.includes('spinning')) {
            progressElement.classList.remove('hidden');
        } else {
            progressElement.classList.add('hidden');
        }
    }
    
    // 隐藏采集状态
    function hideCrawlerStatus() {
        const statusElement = document.getElementById('crawler-status-message');
        const progressElement = document.getElementById('crawler-progress');
        
        statusElement.classList.add('hidden');
        progressElement.classList.add('hidden');
        // 清除内容，避免下次显示时出现旧内容
        statusElement.innerHTML = '';
    }
    
    // 显示完成状态（几秒后自动隐藏）
    function showCompletionStatus(message, type = 'success', duration = 3000) {
        const icon = type === 'success' ? 'ri-checkbox-circle-line' : 'ri-error-warning-line';
        showCrawlerStatus(message, type, icon);
        
        // 自动隐藏
        setTimeout(() => {
            hideCrawlerStatus();
        }, duration);
    }
    
    // 视频搜索功能
    function startVideoSearch() {
        const keyword = document.getElementById('search-keyword').value.trim();
        const pages = parseInt(document.getElementById('search-pages').value) || 5;
        const cookie = document.getElementById('search-cookie').value;
        const proxy = document.getElementById('search-proxy').value;
        
        if (!keyword) {
            alert('请输入搜索关键词！');
            return;
        }
        
        if (!cookie) {
            alert('请选择Cookie！抖音内容采集必须使用Cookie才能正常工作。');
            return;
        }
        
        showCrawlerStatus('正在搜索视频...');
        
        const searchData = {
            keyword: keyword,
            pages: pages,
            cookie: cookie,
            proxy: proxy
        };
        
        fetch('/api/douyin/search/video', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(searchData)
        })
        .then(response => {
            console.log('搜索API响应状态:', response.status);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            return response.json();
        })
        .then(data => {
            console.log('搜索API返回数据:', data);
            if (data.success) {
                if (data.data && Array.isArray(data.data)) {
                    // 显示成功完成状态
                    showCompletionStatus(`✅ 搜索完成！找到 ${data.data.length} 个视频`, 'success');
                    displaySearchResults(data.data, '视频搜索');
                    showSuccessMessage(`搜索完成！找到 ${data.data.length} 个结果`);
                } else {
                    showCompletionStatus('⚠️ 搜索完成，但数据格式异常', 'warning');
                    console.error('搜索数据格式异常:', data.data);
                    alert('搜索完成，但数据格式异常');
                }
            } else {
                showCompletionStatus(`❌ 搜索失败：${data.message}`, 'error');
                console.error('搜索失败:', data.message);
                alert(`搜索失败：${data.message}`);
            }
        })
        .catch(error => {
            showCompletionStatus(`❌ 搜索请求失败：${error.message}`, 'error');
            console.error('搜索请求失败:', error);
            alert(`搜索请求失败：${error.message}`);
        });
    }
    
    // 获取视频详情
    function getVideoDetail() {
        const detailId = document.getElementById('detail-id').value.trim();
        const cookie = document.getElementById('detail-cookie').value;
        const proxy = document.getElementById('detail-proxy').value;
        
        if (!detailId) {
            alert('请输入视频ID！');
            return;
        }
        
        if (!cookie) {
            alert('请选择Cookie！抖音内容采集必须使用Cookie才能正常工作。');
            return;
        }
        
        showCrawlerStatus('正在获取视频详情...');
        
        const detailData = {
            detail_id: detailId,
            cookie: cookie,
            proxy: proxy
        };
        
        fetch('/api/douyin/detail', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(detailData)
        })
        .then(response => response.json())
        .then(data => {
            hideCrawlerStatus();
            if (data.success) {
                displaySearchResults([data.data], '视频详情');
                showSuccessMessage('视频详情获取成功！');
            } else {
                alert(`获取详情失败：${data.message}`);
            }
        })
        .catch(error => {
            hideCrawlerStatus();
            console.error('获取详情失败:', error);
            alert('获取详情失败，请检查网络连接');
        });
    }
    
    // 获取用户作品
    function getUserAccount() {
        const accountUrl = document.getElementById('account-url').value.trim();
        const tabType = document.getElementById('account-tab-type').value;
        const pages = parseInt(document.getElementById('account-pages').value) || 5;
        const cookie = document.getElementById('account-cookie').value;
        const proxy = document.getElementById('account-proxy').value;
        
        if (!accountUrl) {
            alert('请输入抖音账号链接！');
            return;
        }
        
        if (!cookie) {
            alert('请选择Cookie！抖音内容采集必须使用Cookie才能正常工作。');
            return;
        }
        
        showCrawlerStatus('正在解析账号链接并获取作品...');
        
        const accountData = {
            account_url: accountUrl,
            tab: tabType,
            pages: pages,
            cookie: cookie,
            proxy: proxy
        };
        
        fetch('/api/douyin/account', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(accountData)
        })
        .then(response => response.json())
        .then(data => {
            hideCrawlerStatus();
            if (data.success) {
                displaySearchResults(data.data, '用户作品');
                showSuccessMessage(`获取成功！找到 ${data.data.length || 0} 个作品`);
            } else {
                alert(`获取用户作品失败：${data.message}`);
            }
        })
        .catch(error => {
            hideCrawlerStatus();
            console.error('获取用户作品失败:', error);
            alert('获取用户作品失败，请检查网络连接');
        });
    }
    
    // 获取热榜数据
    function getHotData() {
        const hotBtn = document.getElementById('get-hot');
        
        // 防止重复点击
        if (hotBtn && hotBtn.disabled) {
            console.log('热榜数据获取正在进行中，请稍候...');
            return;
        }
        
        const cookie = document.getElementById('hot-cookie').value;
        const proxy = document.getElementById('hot-proxy').value;
        
        if (!cookie) {
            alert('请选择Cookie！抖音内容采集必须使用Cookie才能正常工作。');
            return;
        }
        
        // 禁用按钮
        if (hotBtn) {
            hotBtn.disabled = true;
            hotBtn.innerHTML = '<i class="ri-loader-line spinning"></i> 获取中...';
        }
        
        showCrawlerStatus('正在获取热榜数据...');
        console.log('开始获取热榜数据:', { cookie, proxy });
        
        const params = new URLSearchParams();
        if (cookie) params.append('cookie', cookie);
        if (proxy) params.append('proxy', proxy);
        
        fetch(`/api/douyin/hot?${params.toString()}`)
        .then(response => {
            console.log('热榜API响应状态:', response.status);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            return response.json();
        })
        .then(data => {
            console.log('热榜API响应数据:', data);
            hideCrawlerStatus();
            
            if (data.success && data.data) {
                if (Array.isArray(data.data) && data.data.length > 0) {
                    displaySearchResults(data.data, '热榜数据');
                    showSuccessMessage(data.message || `热榜数据获取成功！共 ${data.data.length} 条`);
                } else {
                    displaySearchResults([], '热榜数据');
                    alert('热榜数据为空，请稍后重试');
                }
            } else {
                console.error('热榜API响应错误:', data);
                alert(`获取热榜失败：${data.message || '未知错误'}`);
            }
        })
        .catch(error => {
            hideCrawlerStatus();
            console.error('获取热榜请求失败:', error);
            alert(`获取热榜失败：${error.message}`);
        })
        .finally(() => {
            // 恢复按钮状态
            if (hotBtn) {
                hotBtn.disabled = false;
                hotBtn.innerHTML = '<i class="ri-fire-line"></i> 获取热榜';
            }
        });
    }
    
    // 解析链接
    function parseLink() {
        const text = document.getElementById('link-text').value.trim();
        const proxy = document.getElementById('link-proxy').value;
        
        if (!text) {
            alert('请输入分享链接或文本！');
            return;
        }
        
        showCrawlerStatus('正在解析链接...');
        
        const parseData = {
            text: text,
            proxy: proxy
        };
        
        fetch('/api/douyin/link_parse', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(parseData)
        })
        .then(response => response.json())
        .then(data => {
            hideCrawlerStatus();
            if (data.success) {
                const urls = data.data.urls || [];
                displayLinkResults(urls);
                showSuccessMessage(`链接解析成功！找到 ${urls.length} 个链接`);
            } else {
                alert(`链接解析失败：${data.message}`);
            }
        })
        .catch(error => {
            hideCrawlerStatus();
            console.error('链接解析失败:', error);
            alert('链接解析失败，请检查网络连接');
        });
    }
    
    // 显示搜索结果
    function displaySearchResults(results, type) {
        window.crawlerResults = results;
        const container = document.getElementById('results-container');
        
        if (!results || results.length === 0) {
            container.innerHTML = `
                <div class="empty-results">
                    <i class="ri-inbox-line"></i>
                    <p>没有找到相关内容</p>
                    <span>尝试调整搜索条件</span>
                </div>
            `;
            return;
        }
        
        let html = `
            <div class="results-summary">
                <h4><i class="ri-file-list-3-line"></i> ${type} - 共 ${results.length} 条结果</h4>
                <div class="summary-actions">
                    <button onclick="selectAllResults()" class="mini-btn">
                        <i class="ri-checkbox-multiple-line"></i> 全选
                    </button>
                    <button onclick="clearAllSelections()" class="mini-btn">
                        <i class="ri-checkbox-blank-line"></i> 清空
                    </button>
                </div>
            </div>
            <div class="results-table">
                <table>
                    <thead>
                        <tr>
                            <th width="40"><input type="checkbox" id="select-all-results"></th>
                            <th width="100">封面</th>
                            <th>标题</th>
                            <th width="80">时长</th>
                            <th width="100">作者</th>
                            <th width="80">点赞</th>
                            <th width="120">发布时间</th>
                            <th width="100">操作</th>
                        </tr>
                    </thead>
                    <tbody>
        `;
        
        results.forEach((item, index) => {
            const title = item.desc || item.title || '无标题';
            const author = item.author?.nickname || item.nickname || '未知作者';
            const duration = formatDuration(item.duration || 0);
            const likeCount = formatNumber(item.statistics?.digg_count || item.digg_count || 0);
            const createTime = formatTime(item.create_time || item.createTime);
            const cover = item.cover?.[0] || item.video?.cover || '';
            const awemeId = item.aweme_id || item.id || '';
            
            html += `
                <tr>
                    <td><input type="checkbox" class="result-checkbox" data-index="${index}"></td>
                    <td>
                        <div class="video-cover">
                            ${cover ? `<img src="${cover}" alt="封面" loading="lazy">` : '<div class="no-cover"><i class="ri-image-line"></i></div>'}
                        </div>
                    </td>
                    <td>
                        <div class="video-title" title="${title}">
                            ${title.length > 50 ? title.substring(0, 50) + '...' : title}
                        </div>
                    </td>
                    <td>${duration}</td>
                    <td>${author}</td>
                    <td>${likeCount}</td>
                    <td>${createTime}</td>
                    <td>
                        <button onclick="downloadSingleVideo('${awemeId}')" class="mini-btn primary">
                            <i class="ri-download-line"></i>
                        </button>
                        <button onclick="viewVideoDetail('${awemeId}')" class="mini-btn secondary">
                            <i class="ri-eye-line"></i>
                        </button>
                    </td>
                </tr>
            `;
        });
        
        html += `
                    </tbody>
                </table>
            </div>
        `;
        
        container.innerHTML = html;
        
        // 显示操作按钮
        document.getElementById('export-results').classList.remove('hidden');
        document.getElementById('batch-download').classList.remove('hidden');
        document.getElementById('clear-results').classList.remove('hidden');
        
        // 设置全选复选框事件
        document.getElementById('select-all-results').addEventListener('change', function() {
            const checkboxes = document.querySelectorAll('.result-checkbox');
            checkboxes.forEach(cb => cb.checked = this.checked);
        });
    }
    
    // 显示链接解析结果
    function displayLinkResults(urls) {
        const container = document.getElementById('results-container');
        
        if (!urls || urls.length === 0) {
            container.innerHTML = `
                <div class="empty-results">
                    <i class="ri-links-line"></i>
                    <p>没有解析到有效链接</p>
                    <span>请检查输入的文本内容</span>
                </div>
            `;
            return;
        }
        
        let html = `
            <div class="results-summary">
                <h4><i class="ri-links-line"></i> 链接解析结果 - 共 ${urls.length} 个链接</h4>
            </div>
            <div class="link-results">
        `;
        
        urls.forEach((urlItem, index) => {
            // 处理不同的数据格式 - 可能是字符串也可能是对象
            let urlText, urlType, originalText;
            if (typeof urlItem === 'string') {
                urlText = urlItem;
                urlType = 'unknown';
                originalText = urlItem;
            } else if (typeof urlItem === 'object' && urlItem !== null) {
                urlText = urlItem.url || urlItem.toString();
                urlType = urlItem.type || 'unknown';
                originalText = urlItem.original || urlItem.url || urlItem.toString();
            } else {
                urlText = String(urlItem);
                urlType = 'unknown';
                originalText = String(urlItem);
            }
            
            // 确定链接类型图标
            let linkIcon = 'ri-link';
            let linkTypeText = '链接';
            if (urlType.includes('user')) {
                linkIcon = 'ri-user-line';
                linkTypeText = '用户主页';
            } else if (urlType.includes('content') || urlType.includes('video')) {
                linkIcon = 'ri-video-line';
                linkTypeText = '视频内容';
            }
            
            html += `
                <div class="link-item">
                    <div class="link-content">
                        <i class="${linkIcon}"></i>
                        <div class="link-info">
                            <span class="link-text" title="${urlText}">${urlText}</span>
                            <small class="link-type">${linkTypeText}</small>
                        </div>
                    </div>
                    <div class="link-actions">
                        <button onclick="copyToClipboard('${urlText.replace(/'/g, "\\'")}'" title="复制链接" class="mini-btn">
                            <i class="ri-file-copy-line"></i> 复制
                        </button>
                        <button onclick="getVideoFromUrl('${urlText.replace(/'/g, "\\'")}'" title="获取详情" class="mini-btn primary">
                            <i class="ri-download-line"></i> 获取详情
                        </button>
                    </div>
                </div>
            `;
        });
        
        html += '</div>';
        container.innerHTML = html;
        
        // 显示部分操作按钮
        document.getElementById('clear-results').classList.remove('hidden');
    }
    
    // 工具函数
    function formatDuration(duration) {
        if (!duration) return '--';
        
        // 如果是字符串格式 "00:00:00" 或 "mm:ss"
        if (typeof duration === 'string') {
            if (duration === '00:00:00' || duration === '-1' || duration === '0') {
                return '--';
            }
            // 如果已经是正确格式的时间字符串，直接返回
            if (duration.includes(':')) {
                const parts = duration.split(':');
                if (parts.length >= 2) {
                    const minutes = parseInt(parts[parts.length - 2]) || 0;
                    const seconds = parseInt(parts[parts.length - 1]) || 0;
                    return `${minutes}:${seconds.toString().padStart(2, '0')}`;
                }
            }
        }
        
        // 如果是数字（秒数）
        if (typeof duration === 'number' && duration > 0) {
            const minutes = Math.floor(duration / 60);
            const remainingSeconds = duration % 60;
            return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`;
        }
        
        return '--';
    }
    
    function formatNumber(num) {
        if (!num) return '0';
        if (num >= 10000) {
            return `${(num / 10000).toFixed(1)}万`;
        }
        return num.toString();
    }
    
    function formatTime(timestamp) {
        if (!timestamp) return '--';
        
        let date;
        
        // 如果是字符串格式 "2025-06-17 17:21:14"
        if (typeof timestamp === 'string') {
            // 处理各种字符串时间格式
            date = new Date(timestamp);
        } else if (typeof timestamp === 'number') {
            // 如果是时间戳（秒或毫秒）
            if (timestamp < 10000000000) {
                // 10位时间戳（秒）
                date = new Date(timestamp * 1000);
            } else {
                // 13位时间戳（毫秒）
                date = new Date(timestamp);
            }
        } else {
            return '--';
        }
        
        // 检查日期是否有效
        if (isNaN(date.getTime())) {
            return '--';
        }
        
        return date.toLocaleDateString();
    }
    
    // 结果操作函数
    function selectAllResults() {
        const checkboxes = document.querySelectorAll('.result-checkbox');
        checkboxes.forEach(cb => cb.checked = true);
        document.getElementById('select-all-results').checked = true;
    }
    
    function clearAllSelections() {
        const checkboxes = document.querySelectorAll('.result-checkbox');
        checkboxes.forEach(cb => cb.checked = false);
        document.getElementById('select-all-results').checked = false;
    }
    
    // 导出结果
    function exportResults() {
        if (!window.crawlerResults || window.crawlerResults.length === 0) {
            alert('没有可导出的数据！');
            return;
        }
        
        const jsonData = JSON.stringify(window.crawlerResults, null, 2);
        const blob = new Blob([jsonData], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        
        const a = document.createElement('a');
        a.href = url;
        a.download = `douyin_crawler_results_${new Date().getTime()}.json`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        
        showSuccessMessage('数据导出成功！');
    }
    
    // 批量下载 - 显示下载设置面板
    function batchDownload() {
        const selectedCheckboxes = document.querySelectorAll('.result-checkbox:checked');
        if (selectedCheckboxes.length === 0) {
            alert('请先选择要下载的视频！');
            return;
        }
        
        const selectedVideos = [];
        selectedCheckboxes.forEach(cb => {
            const index = parseInt(cb.getAttribute('data-index'));
            const video = window.crawlerResults[index];
            if (video) {
                selectedVideos.push(video);
            }
        });
        
        if (selectedVideos.length === 0) {
            alert('没有有效的视频可下载！');
            return;
        }
        
        // 存储选中的视频数据
        window.selectedDownloadVideos = selectedVideos;
        
        // 显示下载设置面板
        const settingsPanel = document.getElementById('download-settings-panel');
        settingsPanel.classList.remove('hidden');
        
        // 更新下载按钮文本
        const confirmBtn = document.getElementById('confirm-download');
        confirmBtn.textContent = `确认下载选中的 ${selectedVideos.length} 个视频`;
        
        // 滚动到设置面板
        settingsPanel.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
    
    // 确认下载选中的视频
    function confirmDownload() {
        const downloadCookie = document.getElementById('download-cookie').value;
        const downloadProxy = document.getElementById('download-proxy').value;
        
        if (!downloadCookie) {
            alert('请先选择Cookie！下载视频必须使用Cookie才能正常工作。');
            return;
        }
        
        if (!window.selectedDownloadVideos || window.selectedDownloadVideos.length === 0) {
            alert('没有选中的视频可下载！');
            return;
        }
        
        const videosCount = window.selectedDownloadVideos.length;
        if (!confirm(`确定要下载 ${videosCount} 个视频吗？\n视频将保存到 downloads 文件夹中。`)) {
            return;
        }
        
        // 隐藏设置面板
        document.getElementById('download-settings-panel').classList.add('hidden');
        
        // 隐藏原有的状态消息，下载进度将通过WebSocket事件显示
        hideCrawlerStatus();
        
        const downloadData = {
            videos: window.selectedDownloadVideos,
            cookie: downloadCookie,
            proxy: downloadProxy
        };
        
        fetch('/api/douyin/download', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(downloadData)
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                // 现在API是异步的，只返回任务启动消息
                // 真正的下载结果通过WebSocket推送，由handleDownloadProgress处理
                showCompletionStatus(`✅ ${data.message}`, 'success', 3000);
                console.log('下载任务已启动:', data.message);
                
                // 不再显示alert，改为提示信息
                showSuccessMessage('下载任务已启动，请查看进度面板了解实时状态');
            } else {
                showCompletionStatus(`❌ 下载启动失败：${data.message}`, 'error', 5000);
                alert(`❌ 下载启动失败：${data.message}`);
            }
        })
        .catch(error => {
            showCompletionStatus('❌ 下载请求失败，请检查网络连接', 'error', 5000);
            console.error('下载请求失败:', error);
            alert('下载请求失败，请检查网络连接状态。\n注意：如果后端正在下载，请通过进度面板查看下载状态。');
        })
        .finally(() => {
            // 清理选中的视频数据
            window.selectedDownloadVideos = null;
        });
    }
    
    // 取消下载
    function cancelDownload() {
        // 隐藏设置面板
        document.getElementById('download-settings-panel').classList.add('hidden');
        // 清理选中的视频数据
        window.selectedDownloadVideos = null;
    }
    
    // 停止下载函数
    function stopDownload() {
        if (confirm('确定要停止当前下载任务吗？已下载的视频将保留。')) {
            fetch('/api/douyin/download/stop', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                }
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    console.log('停止下载请求已发送:', data.message);
                    showCompletionStatus('停止信号已发送，正在停止下载...', 'info', 2000);
                } else {
                    console.error('停止下载失败:', data.message);
                    alert('停止下载失败: ' + data.message);
                }
            })
            .catch(error => {
                console.error('停止下载请求失败:', error);
                alert('停止下载请求失败: ' + error.message);
            });
        }
    }
    
    // 清空结果
    function clearResults() {
        window.crawlerResults = [];
        const container = document.getElementById('results-container');
        container.innerHTML = `
            <div class="empty-results">
                <i class="ri-inbox-line"></i>
                <p>暂无采集结果</p>
                <span>使用上方功能开始采集抖音内容</span>
            </div>
        `;
        
        // 隐藏操作按钮
        document.getElementById('export-results').classList.add('hidden');
        document.getElementById('batch-download').classList.add('hidden');
        document.getElementById('clear-results').classList.add('hidden');
    }
    
    // 单个视频下载
    function downloadSingleVideo(awemeId) {
        if (!awemeId) {
            alert('❌ 视频ID无效');
            return;
        }
        
        // 从当前结果中找到对应的视频信息
        let videoInfo = null;
        if (window.crawlerResults) {
            videoInfo = window.crawlerResults.find(v => 
                (v.aweme_id && v.aweme_id === awemeId) || 
                (v.id && v.id === awemeId)
            );
        }
        
        if (!videoInfo) {
            // 如果找不到视频信息，创建基本信息
            videoInfo = {
                aweme_id: awemeId,
                id: awemeId,
                desc: `视频_${awemeId}`,
                title: `视频_${awemeId}`
            };
        }
        
        // 优先使用下载设置面板的Cookie，否则使用搜索设置的Cookie
        let cookie = '';
        let proxy = '';
        
        const downloadCookieSelect = document.getElementById('download-cookie');
        const downloadProxySelect = document.getElementById('download-proxy');
        const searchCookieSelect = document.getElementById('search-cookie');
        const searchProxySelect = document.getElementById('search-proxy');
        
        if (downloadCookieSelect && downloadCookieSelect.value) {
            cookie = downloadCookieSelect.value;
            proxy = downloadProxySelect ? downloadProxySelect.value : '';
        } else if (searchCookieSelect && searchCookieSelect.value) {
            cookie = searchCookieSelect.value;
            proxy = searchProxySelect ? searchProxySelect.value : '';
        }
        
        if (!cookie) {
            alert('请先选择Cookie！下载视频必须使用Cookie才能正常工作。\n您可以在搜索设置或批量下载设置中选择Cookie。');
            return;
        }
        
        const videoTitle = videoInfo.desc || videoInfo.title || awemeId;
        if (!confirm(`确定要下载视频吗？\n标题: ${videoTitle}\nID: ${awemeId}`)) {
            return;
        }
        
        // 显示下载状态
        showCrawlerStatus(`正在下载视频: ${videoTitle}...`);
        
        const downloadData = {
            videos: [videoInfo],
            cookie: cookie,
            proxy: proxy
        };
        
        fetch('/api/douyin/download', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(downloadData)
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                // 现在API是异步的，只返回任务启动消息
                showCompletionStatus(`✅ ${data.message}`, 'success', 3000);
                console.log('单个视频下载任务已启动:', data.message);
                
                // 提示用户查看进度
                showSuccessMessage('视频下载任务已启动，请查看进度面板了解下载状态');
            } else {
                showCompletionStatus(`❌ 下载启动失败：${data.message}`, 'error', 5000);
                alert(`❌ 下载启动失败：${data.message}`);
            }
        })
        .catch(error => {
            showCompletionStatus('❌ 下载请求失败，请检查网络连接', 'error', 5000);
            console.error('下载请求失败:', error);
            alert('下载请求失败，请检查网络连接状态。\n注意：如果后端正在下载，请通过进度面板查看下载状态。');
        });
    }
    
    // 查看视频详情
    function viewVideoDetail(awemeId) {
        // 切换到详情标签并填入ID
        document.querySelector('[data-tab="detail"]').click();
        document.getElementById('detail-id').value = awemeId;
    }
    
    // 从URL获取视频
    function getVideoFromUrl(url) {
        if (!url) {
            alert('❌ 链接无效');
            return;
        }
        
        // 切换到详情标签并填入链接，让用户手动获取详情
        const detailTab = document.querySelector('[data-tab="detail"]');
        if (detailTab) {
            detailTab.click();
            
            // 尝试从URL中提取视频ID
            const idMatch = url.match(/\/(?:video|note|slides)\/(\d{19})/);
            if (idMatch) {
                const detailIdInput = document.getElementById('detail-id');
                if (detailIdInput) {
                    detailIdInput.value = idMatch[1];
                    showSuccessMessage('已自动填入视频ID，请点击"获取详情"按钮');
                    return;
                }
            }
        }
        
        // 如果无法自动提取ID，提示用户
        alert(`💡 请手动操作：\n1. 切换到"视频详情"标签\n2. 将链接粘贴到详情页面获取信息\n\n链接已复制到剪贴板: ${url}`);
        
        // 复制链接到剪贴板
        copyToClipboard(url);
    }
    
    // 复制到剪贴板
    function copyToClipboard(text) {
        navigator.clipboard.writeText(text).then(function() {
            showSuccessMessage('链接已复制到剪贴板！');
        }, function(err) {
            console.error('复制失败:', err);
            alert('复制失败，请手动复制');
        });
    }
    
    // Downloader服务控制功能
    function initDownloaderService() {
        const statusIndicator = document.getElementById('downloader-status-indicator');
        const statusText = document.getElementById('downloader-status-text');
        const startBtn = document.getElementById('start-downloader-btn');
        const stopBtn = document.getElementById('stop-downloader-btn');
        const refreshBtn = document.getElementById('refresh-downloader-status');
        const showLogsBtn = document.getElementById('show-downloader-logs');
        const clearLogsBtn = document.getElementById('clear-logs');
        const autoScrollBtn = document.getElementById('auto-scroll-logs');
        
        // 绑定事件监听器
        if (startBtn) {
            startBtn.addEventListener('click', startDownloaderService);
        }
        if (stopBtn) {
            stopBtn.addEventListener('click', stopDownloaderService);
        }
        if (refreshBtn) {
            refreshBtn.addEventListener('click', refreshDownloaderStatus);
        }
        if (showLogsBtn) {
            showLogsBtn.addEventListener('click', toggleDownloaderLogs);
        }
        if (clearLogsBtn) {
            clearLogsBtn.addEventListener('click', clearDownloaderLogs);
        }
        if (autoScrollBtn) {
            autoScrollBtn.addEventListener('click', toggleAutoScroll);
        }
        
        // 初始状态检查
        refreshDownloaderStatus();
        
        // 定期检查状态和更新日志
        setInterval(refreshDownloaderStatus, 30000); // 每30秒检查一次状态
        setInterval(updateDownloaderLogs, 5000); // 每5秒更新一次日志
    }
    
    async function refreshDownloaderStatus() {
        const statusIndicator = document.getElementById('downloader-status-indicator');
        const statusText = document.getElementById('downloader-status-text');
        const startBtn = document.getElementById('start-downloader-btn');
        const stopBtn = document.getElementById('stop-downloader-btn');
        
        // 设置检查状态
        updateDownloaderStatus('checking', '正在检查服务状态...', false, false);
        
        try {
            const response = await fetch('/api/downloader/status');
            const data = await response.json();
            
            if (data.running) {
                updateDownloaderStatus('online', '服务运行中 - 端口5555', false, true);
            } else {
                updateDownloaderStatus('offline', '服务离线', true, false);
            }
        } catch (error) {
            console.error('检查Downloader状态失败:', error);
            updateDownloaderStatus('offline', '连接失败', true, false);
        }
    }
    
    async function startDownloaderService() {
        const startBtn = document.getElementById('start-downloader-btn');
        const stopBtn = document.getElementById('stop-downloader-btn');
        
        startBtn.disabled = true;
        startBtn.innerHTML = '<i class="ri-loader-line spinning"></i> 启动中...';
        
        updateDownloaderStatus('checking', '正在启动Downloader服务，请稍候...', false, false);
        
        try {
            const response = await fetch('/api/downloader/start', {
                method: 'POST'
            });
            const data = await response.json();
            
            if (data.success) {
                updateDownloaderStatus('online', data.message, false, true);
                showSuccessMessage('✅ Downloader服务启动成功');
                
                // 等待几秒后再次检查状态确认
                setTimeout(refreshDownloaderStatus, 3000);
            } else {
                updateDownloaderStatus('offline', data.message, true, false);
                alert('❌ 启动失败: ' + data.message);
            }
        } catch (error) {
            console.error('启动Downloader服务失败:', error);
            updateDownloaderStatus('offline', '启动失败: ' + error.message, true, false);
            alert('❌ 启动失败: ' + error.message);
        } finally {
            startBtn.disabled = false;
            startBtn.innerHTML = '<i class="ri-play-circle-line"></i> 启动服务';
        }
    }
    
    async function stopDownloaderService() {
        const startBtn = document.getElementById('start-downloader-btn');
        const stopBtn = document.getElementById('stop-downloader-btn');
        
        if (!confirm('确定要停止Downloader服务吗？这将中断正在进行的采集任务。')) {
            return;
        }
        
        stopBtn.disabled = true;
        stopBtn.innerHTML = '<i class="ri-loader-line spinning"></i> 停止中...';
        
        updateDownloaderStatus('checking', '正在停止Downloader服务...', false, false);
        
        try {
            const response = await fetch('/api/downloader/stop', {
                method: 'POST'
            });
            const data = await response.json();
            
            updateDownloaderStatus('offline', data.message, true, false);
            showSuccessMessage('✅ Downloader服务已停止');
        } catch (error) {
            console.error('停止Downloader服务失败:', error);
            updateDownloaderStatus('offline', '停止失败: ' + error.message, true, false);
            alert('❌ 停止失败: ' + error.message);
        } finally {
            stopBtn.disabled = false;
            stopBtn.innerHTML = '<i class="ri-stop-circle-line"></i> 停止服务';
        }
    }
    
    function updateDownloaderStatus(status, message, startEnabled, stopEnabled) {
        const statusIndicator = document.getElementById('downloader-status-indicator');
        const statusText = document.getElementById('downloader-status-text');
        const startBtn = document.getElementById('start-downloader-btn');
        const stopBtn = document.getElementById('stop-downloader-btn');
        
        if (statusIndicator) {
            // 移除所有状态类
            statusIndicator.className = 'status-indicator';
            statusIndicator.classList.add(status);
            
            // 更新图标和文本
            const icon = statusIndicator.querySelector('i');
            const span = statusIndicator.querySelector('span');
            
            if (status === 'online') {
                icon.className = 'ri-check-circle-line';
                span.textContent = '在线';
            } else if (status === 'offline') {
                icon.className = 'ri-close-circle-line';
                span.textContent = '离线';
            } else if (status === 'checking') {
                icon.className = 'ri-loader-line spinning';
                span.textContent = '检查中';
            }
        }
        
        if (statusText) {
            statusText.textContent = message;
        }
        
        if (startBtn) {
            startBtn.disabled = !startEnabled;
        }
        
        if (stopBtn) {
            stopBtn.disabled = !stopEnabled;
        }
        
        // 更新日志按钮状态
        const showLogsBtn = document.getElementById('show-downloader-logs');
        if (showLogsBtn) {
            showLogsBtn.disabled = status === 'offline';
        }
    }
    
    async function toggleDownloaderLogs() {
        const logsContainer = document.getElementById('downloader-logs-container');
        const showLogsBtn = document.getElementById('show-downloader-logs');
        
        if (logsContainer.classList.contains('hidden')) {
            logsContainer.classList.remove('hidden');
            showLogsBtn.innerHTML = '<i class="ri-eye-off-line"></i> 隐藏日志';
            await updateDownloaderLogs();
        } else {
            logsContainer.classList.add('hidden');
            showLogsBtn.innerHTML = '<i class="ri-file-text-line"></i> 查看日志';
        }
    }
    
    async function updateDownloaderLogs() {
        const logsContainer = document.getElementById('downloader-logs-container');
        if (logsContainer.classList.contains('hidden')) {
            return; // 如果日志面板隐藏，不更新
        }
        
        try {
            const response = await fetch('/api/downloader/logs');
            const data = await response.json();
            
            const logsElement = document.getElementById('downloader-logs');
            if (logsElement && data.logs) {
                // 格式化日志显示
                const formattedLogs = data.logs.map(log => {
                    const logLevel = log.match(/\] (\w+):/);
                    if (logLevel) {
                        const level = logLevel[1].toLowerCase();
                        return `<span class="log-${level}">${log}</span>`;
                    }
                    return log;
                }).join('\n');
                
                logsElement.innerHTML = formattedLogs;
                
                // 自动滚动到底部
                const autoScrollBtn = document.getElementById('auto-scroll-logs');
                if (autoScrollBtn && autoScrollBtn.classList.contains('active')) {
                    const logsContent = document.querySelector('.logs-content');
                    if (logsContent) {
                        logsContent.scrollTop = logsContent.scrollHeight;
                    }
                }
            }
        } catch (error) {
            console.error('获取日志失败:', error);
        }
    }
    
    async function clearDownloaderLogs() {
        if (!confirm('确定要清空所有日志吗？')) {
            return;
        }
        
        try {
            const response = await fetch('/api/downloader/logs/clear', {
                method: 'POST'
            });
            const data = await response.json();
            
            if (data.success) {
                const logsElement = document.getElementById('downloader-logs');
                if (logsElement) {
                    logsElement.innerHTML = '';
                }
                showSuccessMessage('日志已清空');
            }
        } catch (error) {
            console.error('清空日志失败:', error);
            alert('清空日志失败: ' + error.message);
        }
    }
    
    function toggleAutoScroll() {
        const autoScrollBtn = document.getElementById('auto-scroll-logs');
        if (autoScrollBtn) {
            autoScrollBtn.classList.toggle('active');
            
            if (autoScrollBtn.classList.contains('active')) {
                autoScrollBtn.title = '自动滚动: 开启';
                // 立即滚动到底部
                const logsContent = document.querySelector('.logs-content');
                if (logsContent) {
                    logsContent.scrollTop = logsContent.scrollHeight;
                }
            } else {
                autoScrollBtn.title = '自动滚动: 关闭';
            }
        }
    }
    
    // 检查下载状态函数
    function checkDownloadStatus() {
        fetch('/api/douyin/download/status')
            .then(response => response.json())
            .then(data => {
                if (data.success && data.data.is_downloading) {
                    console.log('🔄 检测到正在进行的下载任务，恢复进度显示');
                    
                    // 显示下载进度面板
                    const progressMessage = document.getElementById('download-progress-message');
                    if (progressMessage) {
                        progressMessage.classList.remove('hidden');
                        progressMessage.classList.add('info');
                        
                        // 更新显示内容
                        const progressText = document.getElementById('download-progress-text');
                        if (progressText) {
                            progressText.textContent = '下载进行中... (页面刷新后恢复显示)';
                        }
                        
                        // 显示停止按钮，隐藏确认按钮  
                        const confirmBtn = document.getElementById('confirm-download');
                        const stopBtn = document.getElementById('stop-download');
                        const stopProgressBtn = document.getElementById('stop-download-progress');
                        if (confirmBtn) confirmBtn.classList.add('hidden');
                        if (stopBtn) stopBtn.classList.remove('hidden');
                        if (stopProgressBtn) stopProgressBtn.classList.remove('hidden');
                    }
                    
                    // 显示提示消息
                    showSuccessMessage('⚠️ 检测到正在进行的下载任务。注意：刷新页面会断开实时进度显示！');
                }
            })
            .catch(error => {
                console.log('检查下载状态失败:', error);
                // 静默失败，不显示错误消息，避免干扰用户体验
            });
    }

    // 抖音视频下载（修复为使用正确的HTML元素）
    async function douyinDownload() {
        const checkedBoxes = document.querySelectorAll('#search-results-container input[type="checkbox"]:checked');
        const selectedVideos = Array.from(checkedBoxes).map(checkbox => {
            const videoId = checkbox.dataset.videoId;
            return searchResultsGlobal.find(video => 
                (video.aweme_id || video.id) === videoId
            );
        }).filter(video => video); // 过滤掉undefined的项

        if (selectedVideos.length === 0) {
            showMessage('请先选择要下载的视频', 'error');
            return;
        }

        const cookie = document.getElementById('download-cookie').value;
        const proxy = document.getElementById('download-proxy').value;

        if (!cookie) {
            showMessage('请选择Cookie文件', 'error');
            return;
        }

        // 显示下载进度面板（使用实际存在的元素）
        const progressMessage = document.getElementById('download-progress-message');
        const stopProgressBtn = document.getElementById('stop-download-progress');
        
        if (progressMessage) {
            progressMessage.classList.remove('hidden');
            progressMessage.className = 'status-message info';
            const progressText = document.getElementById('download-progress-text');
            if (progressText) {
                progressText.textContent = '正在准备下载...';
            }
        }
        
        if (stopProgressBtn) {
            stopProgressBtn.classList.remove('hidden');
        }

        try {
            const response = await fetch('/api/douyin/download', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    videos: selectedVideos,
                    cookie: cookie,
                    proxy: proxy
                })
            });

            const result = await response.json();
            
            if (result.success) {
                showCompletionStatus(result.message, 'success');
                // 注意：现在下载任务在后台异步执行，结果通过WebSocket推送
            } else {
                showCompletionStatus(result.message || '下载启动失败', 'error');
                // 隐藏进度面板
                if (progressMessage) {
                    progressMessage.classList.add('hidden');
                }
                if (stopProgressBtn) {
                    stopProgressBtn.classList.add('hidden');
                }
            }
        } catch (error) {
            console.error('下载请求失败:', error);
            showCompletionStatus('网络请求失败，请检查连接', 'error');
            // 隐藏进度面板
            if (progressMessage) {
                progressMessage.classList.add('hidden');
            }
            if (stopProgressBtn) {
                stopProgressBtn.classList.add('hidden');
            }
        }
    }

    // 处理下载进度更新（使用实际的HTML元素）
    function handleDownloadProgress(data) {
        console.log('收到下载进度更新:', data);
        
        // 使用实际存在的HTML元素
        const progressMessage = document.getElementById('download-progress-message');
        const progressText = document.getElementById('download-progress-text');
        const progressBar = document.getElementById('download-progress-bar');
        const progressPercent = document.getElementById('download-progress-percent');
        const successCount = document.getElementById('download-success-count');
        const failedCount = document.getElementById('download-failed-count');
        const currentTotal = document.getElementById('download-current-total');
        const stopProgressBtn = document.getElementById('stop-download-progress');
        
        if (!progressMessage) {
            console.error('找不到下载进度面板元素');
            return;
        }
        
        // 显示进度面板
        progressMessage.classList.remove('hidden');
        
        // 更新进度信息文本
        if (progressText) {
            progressText.textContent = data.message || '正在处理...';
        }
        
        // 更新进度条
        const percent = data.total > 0 ? Math.round((data.current / data.total) * 100) : 0;
        if (progressBar) {
            progressBar.style.width = `${percent}%`;
        }
        if (progressPercent) {
            progressPercent.textContent = `${percent}%`;
        }
        
        // 更新统计信息
        if (successCount) {
            successCount.textContent = `成功: ${data.success_count || 0}`;
        }
        if (failedCount) {
            failedCount.textContent = `失败: ${data.failed_count || 0}`;
        }
        if (currentTotal) {
            currentTotal.textContent = `${data.current || 0} / ${data.total || 0}`;
        }
        
        // 根据状态更新样式和按钮
        progressMessage.className = 'status-message'; // 重置class
        
        if (data.status === 'started') {
            progressMessage.classList.add('info');
            if (stopProgressBtn) {
                stopProgressBtn.classList.remove('hidden');
            }
        } else if (data.status === 'downloading') {
            progressMessage.classList.add('info');
        } else if (data.status === 'success') {
            // 单个视频成功时保持info样式
            progressMessage.classList.add('info');
        } else if (data.status === 'failed') {
            // 单个视频失败时显示警告色
            progressMessage.classList.add('warning');
        } else if (data.status === 'completed') {
            if (data.failed_count > 0) {
                progressMessage.classList.add('warning');
            } else {
                progressMessage.classList.add('success');
            }
            if (stopProgressBtn) {
                stopProgressBtn.classList.add('hidden');
            }
            // 3秒后自动隐藏
            setTimeout(() => {
                progressMessage.classList.add('hidden');
                refreshStats();
            }, 3000);
        } else if (data.status === 'stopped') {
            progressMessage.classList.add('warning');
            if (stopProgressBtn) {
                stopProgressBtn.classList.add('hidden');
            }
            // 3秒后自动隐藏
            setTimeout(() => {
                progressMessage.classList.add('hidden');
            }, 3000);
        }
        
        // 输出详细信息到控制台
        if (data.video_title) {
            console.log(`下载进度: ${data.video_title} - ${data.status}`);
            if (data.error) {
                console.warn(`下载错误: ${data.error}`);
            }
        }
    }
}); 