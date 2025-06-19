from utils.fingerprint_manager import fingerprint_manager

async def set_init_script(context, cookie_name=None):
    """设置初始化脚本，包括浏览器指纹伪装和人类行为模拟"""
    from utils.human_behavior import human_behavior
    
    # 注入人类行为模拟脚本
    await human_behavior.add_behavior_script(context)
    
    # 增强反检测脚本
    basic_anti_detect_script = """
    // 增强反检测脚本
    (function() {
        'use strict';
        
        // === 1. 隐藏webdriver相关标识 ===
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined,
            configurable: true
        });
        
        // 移除所有CDC相关属性
        const cdcProps = Object.getOwnPropertyNames(window).filter(prop => prop.includes('cdc_'));
        cdcProps.forEach(prop => {
            try {
                delete window[prop];
            } catch(e) {}
        });
        
        // 移除$chrome_asyncScriptInfo
        delete window.$chrome_asyncScriptInfo;
        delete window.$cdc_asdjflasutopfhvcZLmcfl_;
        
        // === 2. 伪装Chrome对象 ===
        if (!window.chrome) {
            window.chrome = {};
        }
        
        if (!window.chrome.runtime) {
            window.chrome.runtime = {
                onConnect: { addListener: () => {}, removeListener: () => {} },
                onMessage: { addListener: () => {}, removeListener: () => {} },
                connect: () => ({ postMessage: () => {}, onMessage: { addListener: () => {} } }),
                sendMessage: () => {},
                id: 'chrome-extension://invalid'
            };
        }
        
        if (!window.chrome.app) {
            window.chrome.app = {
                isInstalled: false,
                InstallState: {
                    DISABLED: 'disabled',
                    INSTALLED: 'installed', 
                    NOT_INSTALLED: 'not_installed'
                },
                RunningState: {
                    CANNOT_RUN: 'cannot_run',
                    READY_TO_RUN: 'ready_to_run',
                    RUNNING: 'running'
                }
            };
        }
        
        // === 3. 伪装插件和扩展 ===
        const realPlugins = [
            { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
            { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: 'Chrome PDF Viewer' },
            { name: 'Native Client', filename: 'internal-nacl-plugin', description: 'Native Client Executable' },
            { name: 'Chromium PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format' }
        ];
        
        Object.defineProperty(navigator, 'plugins', {
            get: () => {
                const pluginArray = realPlugins.map((plugin, index) => ({
                    ...plugin,
                    length: 1,
                    0: { type: 'application/pdf', suffixes: 'pdf', description: plugin.description }
                }));
                pluginArray.length = realPlugins.length;
                return pluginArray;
            },
            configurable: true
        });
        
        // === 4. 伪装语言和平台信息 ===
        const languages = ['zh-CN', 'zh', 'en-US', 'en'];
        Object.defineProperty(navigator, 'languages', {
            get: () => languages,
            configurable: true
        });
        
        // === 5. 伪装权限API ===
        if (navigator.permissions && navigator.permissions.query) {
            const originalQuery = navigator.permissions.query.bind(navigator.permissions);
            navigator.permissions.query = (parameters) => {
                if (parameters.name === 'notifications') {
                    return Promise.resolve({ 
                        state: Notification.permission,
                        onchange: null,
                        addEventListener: () => {},
                        removeEventListener: () => {}
                    });
                }
                return originalQuery(parameters);
            };
        }
        
        // === 6. 伪装DeviceMotion和DeviceOrientation ===
        window.DeviceMotionEvent = window.DeviceMotionEvent || (() => {});
        window.DeviceOrientationEvent = window.DeviceOrientationEvent || (() => {});
        
        // === 7. 伪装Battery API ===
        if (navigator.getBattery) {
            const originalGetBattery = navigator.getBattery.bind(navigator);
            navigator.getBattery = () => {
                return originalGetBattery().catch(() => {
                    return Promise.resolve({
                        charging: true,
                        chargingTime: 0,
                        dischargingTime: Infinity,
                        level: Math.random() * 0.3 + 0.7, // 70-100%
                        addEventListener: () => {},
                        removeEventListener: () => {}
                    });
                });
            };
        }
        
        // === 8. 覆盖函数的toString方法 ===
        const nativeToStringFunctionString = Error.toString.toString();
        const nativeFunction = nativeToStringFunctionString.replace('toString', '');
        
        // 重写所有被修改函数的toString方法
        [
            [navigator.permissions.query, 'function query() { [native code] }'],
            [navigator.getBattery, 'function getBattery() { [native code] }']
        ].forEach(([func, str]) => {
            if (func) {
                Object.defineProperty(func, 'toString', {
                    value: () => str,
                    configurable: true
                });
            }
        });
        
        // === 9. 伪装Notification API ===
        if (window.Notification) {
            Object.defineProperty(Notification, 'permission', {
                get: () => 'default',
                configurable: true
            });
        }
        
        // === 10. 隐藏自动化痕迹 ===
        Object.defineProperty(document, 'documentElement', {
            get: () => {
                const element = document.querySelector('html');
                if (element && element.getAttribute) {
                    const webdriver = element.getAttribute('webdriver');
                    if (webdriver) {
                        element.removeAttribute('webdriver');
                    }
                }
                return element;
            },
            configurable: true
        });
        
        // === 11. 伪装鼠标和触摸事件 ===
        ['click', 'mousedown', 'mouseup', 'mousemove', 'touchstart', 'touchend', 'touchmove'].forEach(eventType => {
            const originalAddEventListener = EventTarget.prototype.addEventListener;
            EventTarget.prototype.addEventListener = function(type, listener, options) {
                if (type === eventType && listener.toString().includes('webdriver')) {
                    return; // 阻止webdriver相关的事件监听器
                }
                return originalAddEventListener.call(this, type, listener, options);
            };
        });
        
        // === 12. 伪装性能API ===
        if (window.performance && window.performance.timing) {
            Object.defineProperty(window.performance, 'timing', {
                get: () => ({
                    connectEnd: Date.now() - Math.random() * 100,
                    connectStart: Date.now() - Math.random() * 200,
                    domComplete: Date.now() + Math.random() * 1000,
                    domContentLoadedEventEnd: Date.now() + Math.random() * 500,
                    domContentLoadedEventStart: Date.now() + Math.random() * 400,
                    domInteractive: Date.now() + Math.random() * 300,
                    domLoading: Date.now() - Math.random() * 50,
                    domainLookupEnd: Date.now() - Math.random() * 300,
                    domainLookupStart: Date.now() - Math.random() * 400,
                    fetchStart: Date.now() - Math.random() * 500,
                    loadEventEnd: Date.now() + Math.random() * 1200,
                    loadEventStart: Date.now() + Math.random() * 1100,
                    navigationStart: Date.now() - Math.random() * 600,
                    redirectEnd: 0,
                    redirectStart: 0,
                    requestStart: Date.now() - Math.random() * 80,
                    responseEnd: Date.now() - Math.random() * 30,
                    responseStart: Date.now() - Math.random() * 60,
                    secureConnectionStart: Date.now() - Math.random() * 150,
                    unloadEventEnd: Date.now() - Math.random() * 600,
                    unloadEventStart: Date.now() - Math.random() * 620
                }),
                configurable: true
            });
        }
        
        // === 13. 防止脚本检测 ===
        const script = document.currentScript;
        if (script) {
            script.remove();
        }
        
        console.log('🛡️ 增强反检测脚本已激活 - 所有已知检测方法已被规避');
    })();
    """
    
    # 注入基础反检测脚本
    await context.add_init_script(basic_anti_detect_script)
    
    # 如果提供了cookie名称，则注入对应的浏览器指纹
    if cookie_name:
        try:
            fingerprint = fingerprint_manager.get_or_create_fingerprint(cookie_name)
            fingerprint_script = fingerprint_manager.inject_fingerprint_script(fingerprint)
            await context.add_init_script(fingerprint_script)
            print(f"✅ 已为 {cookie_name} 注入浏览器指纹伪装")
        except Exception as e:
            print(f"❌ 注入浏览器指纹失败: {str(e)}")
    
    return context 