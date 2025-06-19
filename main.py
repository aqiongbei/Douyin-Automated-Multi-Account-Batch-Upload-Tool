# -*- coding: utf-8 -*-
from datetime import datetime

from playwright.async_api import Playwright, async_playwright, Page
import os
import asyncio

from conf import LOCAL_CHROME_PATH
from utils.base_social_media import set_init_script
from utils.log import douyin_logger
from utils.proxy_manager import proxy_manager


def get_browser_launch_options(headless=True, proxy_config=None):
    """获取统一的浏览器启动配置"""
    options = {
        'headless': headless,
        'args': [
            # === 基础反检测参数 ===
            '--no-first-run',
            '--disable-blink-features=AutomationControlled',
            '--disable-web-security',
            '--disable-features=VizDisplayCompositor',
            '--disable-features=TranslateUI',
            '--disable-ipc-flooding-protection',
            '--disable-renderer-backgrounding',
            '--disable-backgrounding-occluded-windows',
            '--disable-client-side-phishing-detection',
            '--disable-component-extensions-with-background-pages',
            '--disable-default-apps',
            '--disable-extensions',
            '--disable-hang-monitor',
            '--disable-popup-blocking',
            '--disable-prompt-on-repost',
            '--disable-sync',
            '--no-default-browser-check',
            
            # === 增强反检测参数 ===
            '--disable-blink-features=AutomationControlled',  # 禁用自动化控制检测
            '--exclude-switches=enable-automation',           # 排除自动化开关
            '--disable-infobars',                            # 禁用信息栏
            '--disable-dev-shm-usage',                       # 禁用开发共享内存
            '--disable-browser-side-navigation',             # 禁用浏览器端导航
            '--disable-gpu',                                 # 禁用GPU硬件加速
            '--disable-features=TranslateUI',                # 禁用翻译界面
            '--disable-features=BlinkGenPropertyTrees',      # 禁用属性树
            '--disable-background-timer-throttling',         # 禁用后台定时器节流
            '--disable-renderer-backgrounding',              # 禁用渲染器后台运行
            '--disable-backgrounding-occluded-windows',      # 禁用被遮挡窗口的后台运行
            '--disable-restore-session-state',               # 禁用恢复会话状态
            '--disable-component-update',                    # 禁用组件更新
            '--disable-domain-reliability',                  # 禁用域可靠性
            '--disable-features=AudioServiceOutOfProcess',   # 禁用音频服务进程
            '--disable-features=VizDisplayCompositor',       # 禁用显示合成器
            '--autoplay-policy=user-gesture-required',       # 需要用户手势才能自动播放
            '--disable-software-rasterizer',                 # 禁用软件栅格化
            '--disable-background-networking',               # 禁用后台网络
            '--disable-background-mode',                     # 禁用后台模式
            '--disable-default-apps',                        # 禁用默认应用
            '--disable-extensions-file-access-check',        # 禁用扩展文件访问检查
            '--disable-extensions-http-throttling',          # 禁用扩展HTTP节流
            '--disable-search-engine-choice-screen',         # 禁用搜索引擎选择屏幕
            '--simulate-outdated-no-au',                     # 模拟过时无自动更新
            '--force-color-profile=srgb',                    # 强制颜色配置为sRGB
            '--metrics-recording-only',                      # 仅记录指标
            '--disable-print-preview',                       # 禁用打印预览
            '--no-crash-upload',                             # 禁用崩溃上传
            '--enable-precise-memory-info',                  # 启用精确内存信息
            
            # === 用户代理和语言相关 ===
            '--lang=zh-CN',                                  # 设置语言为中文
            '--disable-plugins-discovery',                   # 禁用插件发现
            '--allow-running-insecure-content',              # 允许运行不安全内容
            '--disable-web-resources',                       # 禁用Web资源
            '--reduce-security-for-testing',                 # 为测试减少安全性
            '--allow-http-background-page',                  # 允许HTTP后台页面
            '--disable-features=ImprovedCookieControls',     # 禁用改进的Cookie控制
            '--disable-features=LazyFrameLoading',           # 禁用延迟框架加载
            '--disable-features=GlobalMediaControls',        # 禁用全局媒体控制
            '--disable-features=DestroyProfileOnBrowserClose', # 禁用浏览器关闭时销毁配置文件
            '--disable-features=MediaRouter',                # 禁用媒体路由器
            '--disable-features=DialMediaRouteProvider',     # 禁用拨号媒体路由提供者
            '--disable-features=AcceptCHFrame',              # 禁用AcceptCH框架
            '--disable-features=AutoExpandDetailsElement',   # 禁用详情元素自动展开
            '--disable-features=CertificateTransparencyComponentUpdater', # 禁用证书透明度组件更新器
            '--disable-features=AvoidUnnecessaryBeforeUnloadCheckSync',   # 禁用不必要的beforeunload检查同步
            '--disable-features=LogJsConsoleMessages',       # 禁用JS控制台消息日志
            
            # === 性能和稳定性 ===
            '--max_old_space_size=4096',                     # 设置最大旧空间大小
            '--no-sandbox',                                  # 禁用沙盒（仅在必要时使用）
            '--disable-setuid-sandbox',                      # 禁用setuid沙盒
            '--disable-dev-shm-usage',                       # 禁用/dev/shm使用
            '--disable-accelerated-2d-canvas',               # 禁用2D画布硬件加速
            '--disable-accelerated-jpeg-decoding',           # 禁用JPEG解码硬件加速
            '--disable-accelerated-mjpeg-decode',            # 禁用MJPEG解码硬件加速
            '--disable-accelerated-video-decode',            # 禁用视频解码硬件加速
            '--disable-accelerated-video-encode',            # 禁用视频编码硬件加速
            '--disable-app-list-dismiss-on-blur',            # 禁用应用列表失焦时消失
            '--disable-accelerated-2d-canvas',               # 禁用2D画布硬件加速
            '--num-raster-threads=4',                        # 设置栅格化线程数
        ]
    }
    
    if proxy_config:
        options['proxy'] = proxy_config
    
    # 检查并使用配置的Chrome路径
    if LOCAL_CHROME_PATH and os.path.exists(LOCAL_CHROME_PATH):
        options["executable_path"] = LOCAL_CHROME_PATH
        douyin_logger.info(f"使用配置的Chrome路径: {LOCAL_CHROME_PATH}")
    else:
        if LOCAL_CHROME_PATH:
            douyin_logger.warning(f"配置的Chrome路径不存在: {LOCAL_CHROME_PATH}")
        douyin_logger.info("使用系统默认Chromium")
    
    return options


async def cookie_auth(account_file):
    from utils.fingerprint_manager import fingerprint_manager
    
    cookie_filename = os.path.basename(account_file)
    proxy_config = proxy_manager.get_proxy_for_playwright(cookie_filename)
    launch_options = get_browser_launch_options(headless=True, proxy_config=proxy_config)
    
    # 获取浏览器指纹配置
    fingerprint_config = fingerprint_manager.get_playwright_config(cookie_filename)

    browser = None
    context = None
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(**launch_options)
            
            # 使用指纹配置创建上下文
            context_options = {
                "storage_state": account_file,
                **fingerprint_config
            }
            
            # 添加代理配置
            if proxy_config:
                context_options["proxy"] = proxy_config
                
            context = await browser.new_context(**context_options)
            context = await set_init_script(context, cookie_filename)
            
            # 创建一个新的页面
            page = await context.new_page()
            # 访问指定的 URL
            await page.goto("https://creator.douyin.com/creator-micro/content/upload")
            
            try:
                await page.wait_for_url("https://creator.douyin.com/creator-micro/content/upload", timeout=5000)
            except Exception as e:
                douyin_logger.warning(f"页面加载超时: {str(e)}")
                print("[+] 等待5秒 cookie 失效")
                return False
                
            # 2024.06.17 抖音创作者中心改版
            if await page.get_by_text('手机号登录').count():
                print("[+] cookie 失效 - 检测到登录页面")
                return False
            else:
                print("[+] cookie 有效")
                return True
                
    except Exception as e:
        douyin_logger.error(f"Cookie验证过程中发生错误: {str(e)}")
        return False
    finally:
        # 确保资源总是被释放
        if context:
            try:
                await context.close()
            except Exception as e:
                douyin_logger.warning(f"关闭浏览器上下文时出错: {str(e)}")
        if browser:
            try:
                await browser.close()
            except Exception as e:
                douyin_logger.warning(f"关闭浏览器时出错: {str(e)}")


async def douyin_setup(account_file, handle=False, use_websocket=False, websocket_callback=None):
    if not os.path.exists(account_file) or not await cookie_auth(account_file):
        if not handle:
            # Todo alert message
            return False
        douyin_logger.info('[+] cookie文件不存在或已失效，即将自动打开浏览器，请扫码登录，登陆后会自动生成cookie文件')
        
        if use_websocket and websocket_callback:
            # 使用WebSocket方式生成cookie，通过回调函数避免循环导入
            import time
            import uuid
            session_id = f"cookie_regen_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"
            await websocket_callback(account_file, session_id)
        else:
            # 使用传统方式生成cookie
            await douyin_cookie_gen(account_file)
    return True


async def douyin_cookie_gen(account_file):
    from utils.fingerprint_manager import fingerprint_manager
    
    cookie_filename = os.path.basename(account_file)
    proxy_config = proxy_manager.get_proxy_for_playwright(cookie_filename)
    
    # Docker环境检测
    is_in_docker = os.path.exists('/.dockerenv') or os.environ.get('DOCKER_ENV') == 'true'
    headless_mode = True if is_in_docker else False
    
    if is_in_docker:
        douyin_logger.info("🐳 检测到Docker环境，使用headless模式")
    
    options = get_browser_launch_options(headless=headless_mode, proxy_config=proxy_config)
    
    # 获取浏览器指纹配置
    fingerprint_config = fingerprint_manager.get_playwright_config(cookie_filename)

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(**options)
        
        # 使用指纹配置创建上下文
        context_options = {
            **fingerprint_config
        }
        
        # 添加代理配置
        if proxy_config:
            context_options["proxy"] = proxy_config
            
        context = await browser.new_context(**context_options)
        context = await set_init_script(context, cookie_filename)
        
        # Pause the page, and start recording manually.
        page = await context.new_page()
        await page.goto("https://creator.douyin.com/")
        await page.pause()
        # 点击调试器的继续，保存cookie
        await context.storage_state(path=account_file)


class DouYinVideo(object):
    def __init__(self, title, file_path, tags, publish_date: datetime, account_file, thumbnail_path=None):
        self.title = title  # 视频标题
        self.file_path = file_path
        self.tags = tags
        self.publish_date = publish_date
        self.account_file = account_file
        self.date_format = '%Y年%m月%d日 %H:%M'
        self.local_executable_path = LOCAL_CHROME_PATH
        self.thumbnail_path = thumbnail_path
        self.status_handler = None  # 添加状态处理器

    async def notify_status(self, event, message=""):
        """通知状态更新"""
        if self.status_handler:
            await self.status_handler.handle_event(event, message)

    async def set_schedule_time_douyin(self, page, publish_date):
        # 选择包含特定文本内容的 label 元素
        label_element = page.locator("[class^='radio']:has-text('定时发布')")
        # 在选中的 label 元素下点击 checkbox
        await label_element.click()
        await asyncio.sleep(1)
        publish_date_hour = publish_date.strftime("%Y-%m-%d %H:%M")

        await asyncio.sleep(1)
        await page.locator('.semi-input[placeholder="日期和时间"]').click()
        await page.keyboard.press("Control+KeyA")
        await page.keyboard.type(str(publish_date_hour))
        await page.keyboard.press("Enter")

        await asyncio.sleep(1)

    async def handle_upload_error(self, page):
        douyin_logger.info('视频出错了，重新上传中')
        await page.locator('div.progress-div [class^="upload-btn-input"]').set_input_files(self.file_path)

    async def upload(self, playwright: Playwright, location: str = "杭州市") -> None:
        from utils.fingerprint_manager import fingerprint_manager
        
        # 获取Cookie对应的代理配置
        cookie_filename = os.path.basename(self.account_file)
        proxy_config = proxy_manager.get_proxy_for_playwright(cookie_filename)
        
        # 获取浏览器指纹配置
        fingerprint_config = fingerprint_manager.get_playwright_config(cookie_filename)
        
        # Docker环境检测
        is_in_docker = os.path.exists('/.dockerenv') or os.environ.get('DOCKER_ENV') == 'true'
        headless_mode = True if is_in_docker else False
        
        if is_in_docker:
            douyin_logger.info("🐳 检测到Docker环境，视频上传使用headless模式")
        
        # 使用 Chromium 浏览器启动一个浏览器实例
        launch_options = get_browser_launch_options(headless=headless_mode, proxy_config=proxy_config)
            
        browser = await playwright.chromium.launch(**launch_options)
        
        # 创建浏览器上下文配置，集成指纹配置
        context_options = {
            "storage_state": f"{self.account_file}",
            **fingerprint_config
        }
        
        # 如果有代理配置，添加到上下文中
        if proxy_config:
            context_options["proxy"] = proxy_config
            douyin_logger.info(f"使用代理: {proxy_config['server']} for cookie: {cookie_filename}")
        else:
            douyin_logger.info(f"未配置代理，使用直连 for cookie: {cookie_filename}")
            
        # 创建一个浏览器上下文，使用指定的 cookie 文件、代理和指纹
        context = await browser.new_context(**context_options)
        context = await set_init_script(context, cookie_filename)

        # 创建一个新的页面
        page = await context.new_page()
        # 访问指定的 URL
        await page.goto("https://creator.douyin.com/creator-micro/content/upload")
        douyin_logger.info(f'[+]正在上传-------{self.title}.mp4')
        await self.notify_status("upload_start", "开始上传视频")
        # 等待页面跳转到指定的 URL，没进入，则自动等待到超时
        douyin_logger.info(f'[-] 正在打开主页...')
        await page.wait_for_url("https://creator.douyin.com/creator-micro/content/upload")
        # 点击 "上传视频" 按钮
        await page.locator("div[class^='container'] input").set_input_files(self.file_path)

        # 等待页面跳转到指定的 URL 2025.01.08修改在原有基础上兼容两种页面
        max_retries = 60  # 最多重试60次(30秒)
        retry_count = 0
        page_loaded = False
        
        while retry_count < max_retries and not page_loaded:
            try:
                # 尝试等待第一个 URL
                await page.wait_for_url(
                    "https://creator.douyin.com/creator-micro/content/publish?enter_from=publish_page", timeout=3)
                douyin_logger.info("[+] 成功进入version_1发布页面!")
                await self.notify_status("upload_progress", "成功进入发布页面")
                page_loaded = True
                break  # 成功进入页面后跳出循环
            except Exception:
                try:
                    # 如果第一个 URL 超时，再尝试等待第二个 URL
                    await page.wait_for_url(
                        "https://creator.douyin.com/creator-micro/content/post/video?enter_from=publish_page",
                        timeout=3)
                    douyin_logger.info("[+] 成功进入version_2发布页面!")
                    await self.notify_status("upload_progress", "成功进入发布页面")
                    page_loaded = True
                    break  # 成功进入页面后跳出循环
                except:
                    retry_count += 1
                    douyin_logger.info(f"  [-] 等待发布页面加载... 重试次数: {retry_count}/{max_retries}")
                    await self.notify_status("upload_progress", f"等待页面加载 ({retry_count}/{max_retries})")
                    await asyncio.sleep(0.5)  # 等待 0.5 秒后重新尝试
        
        if not page_loaded:
            raise Exception(f"页面加载超时，已重试{max_retries}次，请检查网络连接或抖音页面状态")
        # 填充标题和话题
        # 检查是否存在包含输入框的元素
        # 这里为了避免页面变化，故使用相对位置定位：作品标题父级右侧第一个元素的input子元素
        await asyncio.sleep(1)
        douyin_logger.info(f'  [-] 正在填充标题和话题...')
        await self.notify_status("upload_progress", "正在填充标题和话题")
        title_container = page.get_by_text('作品标题').locator("..").locator("xpath=following-sibling::div[1]").locator("input")
        if await title_container.count():
            await title_container.fill(self.title[:30])
        else:
            titlecontainer = page.locator(".notranslate")
            await titlecontainer.click()
            await page.keyboard.press("Backspace")
            await page.keyboard.press("Control+KeyA")
            await page.keyboard.press("Delete")
            await page.keyboard.type(self.title)
            await page.keyboard.press("Enter")
        css_selector = ".zone-container"
        for index, tag in enumerate(self.tags, start=1):
            await page.type(css_selector, "#" + tag)
            await page.press(css_selector, "Space")
        douyin_logger.info(f'总共添加{len(self.tags)}个话题')
        await self.notify_status("upload_progress", f"已添加{len(self.tags)}个话题")

        upload_progress = 0
        upload_timeout = 600  # 上传超时时间：10分钟
        upload_start_time = asyncio.get_event_loop().time()
        upload_completed = False
        
        while not upload_completed:
            # 检查是否超时
            current_time = asyncio.get_event_loop().time()
            if current_time - upload_start_time > upload_timeout:
                raise Exception(f"视频上传超时，已等待{upload_timeout//60}分钟")
            
            # 判断重新上传按钮是否存在，如果不存在，代表视频正在上传，则等待
            try:
                #  新版：定位重新上传
                number = await page.locator('[class^="long-card"] div:has-text("重新上传")').count()
                if number > 0:
                    douyin_logger.success("  [-]视频上传完毕")
                    await self.notify_status("upload_complete", "视频文件上传完毕")
                    upload_completed = True
                    break
                else:
                    upload_progress += 5
                    if upload_progress > 90:
                        upload_progress = 90
                    elapsed_time = int(current_time - upload_start_time)
                    douyin_logger.info(f"  [-] 正在上传视频中... 已用时{elapsed_time}秒")
                    await self.notify_status("upload_progress", f"上传进度约{upload_progress}% (已用时{elapsed_time}s)")
                    await asyncio.sleep(2)

                    if await page.locator('div.progress-div > div:has-text("上传失败")').count():
                        douyin_logger.error("  [-] 发现上传出错了... 准备重试")
                        await self.notify_status("upload_progress", "上传失败，准备重试...")
                        await self.handle_upload_error(page)
                        # 重置计时器
                        upload_start_time = asyncio.get_event_loop().time()
                        upload_progress = 0
            except Exception as e:
                elapsed_time = int(current_time - upload_start_time)
                douyin_logger.info(f"  [-] 正在上传视频中... 已用时{elapsed_time}秒")
                await self.notify_status("upload_progress", f"视频处理中... (已用时{elapsed_time}s)")
                await asyncio.sleep(2)
        
        #上传视频封面
        await self.notify_status("upload_progress", "处理视频封面...")
        await self.set_thumbnail(page, self.thumbnail_path)

        # 更换可见元素
        await self.notify_status("upload_progress", "设置发布位置...")
        await self.set_location(page, location)

        # 頭條/西瓜
        third_part_element = '[class^="info"] > [class^="first-part"] div div.semi-switch'
        # 定位是否有第三方平台
        if await page.locator(third_part_element).count():
            # 检测是否是已选中状态
            if 'semi-switch-checked' not in await page.eval_on_selector(third_part_element, 'div => div.className'):
                await page.locator(third_part_element).locator('input.semi-switch-native-control').click()
                await self.notify_status("upload_progress", "开启分发至其他平台")

        if self.publish_date != 0:
            await self.notify_status("upload_progress", "设置定时发布时间...")
            await self.set_schedule_time_douyin(page, self.publish_date)

        # 判断视频是否发布成功
        await self.notify_status("publish_start", "准备发布视频...")
        publish_timeout = 120  # 发布超时时间：2分钟
        publish_start_time = asyncio.get_event_loop().time()
        publish_completed = False
        publish_button_clicked = False
        
        while not publish_completed:
            # 检查是否超时
            current_time = asyncio.get_event_loop().time()
            if current_time - publish_start_time > publish_timeout:
                raise Exception(f"视频发布超时，已等待{publish_timeout}秒")
            
            # 判断视频是否发布成功
            try:
                # 如果还没点击发布按钮，先尝试点击
                if not publish_button_clicked:
                    publish_button = page.get_by_role('button', name="发布", exact=True)
                    if await publish_button.count():
                        await self.notify_status("upload_progress", "点击发布按钮...")
                        await publish_button.click()
                        publish_button_clicked = True
                        douyin_logger.info("  [-] 已点击发布按钮")
                
                # 等待跳转到管理页面
                await page.wait_for_url("https://creator.douyin.com/creator-micro/content/manage**",
                                        timeout=3000)  # 如果自动跳转到作品页面，则代表发布成功
                douyin_logger.success("  [-]视频发布成功")
                await self.notify_status("publish_complete", "视频发布成功")
                publish_completed = True
                break
            except Exception as e:
                elapsed_time = int(current_time - publish_start_time)
                douyin_logger.info(f"  [-] 视频正在发布中... 已用时{elapsed_time}秒")
                await self.notify_status("upload_progress", f"视频正在发布中... (已用时{elapsed_time}s)")
                try:
                    # 明确指定PNG截图参数，避免质量参数错误
                    await page.screenshot(full_page=True, type='png')
                except Exception as e:
                    # 忽略quality参数相关的错误，不影响主流程
                    if "quality is unsupported" not in str(e):
                        douyin_logger.debug(f"截图失败: {str(e)}")
                    pass
                await asyncio.sleep(0.5)

        await context.storage_state(path=self.account_file)  # 保存cookie
        douyin_logger.success('  [-]cookie更新完毕！')
        await self.notify_status("upload_progress", "更新Cookie信息...")
        await asyncio.sleep(2)  # 这里延迟是为了方便眼睛直观的观看
        # 关闭浏览器上下文和浏览器实例
        await context.close()
        await browser.close()
    
    async def set_thumbnail(self, page: Page, thumbnail_path: str):
        if thumbnail_path:
            await page.click('text="选择封面"')
            await page.wait_for_selector("div.semi-modal-content:visible")
            await page.click('text="设置竖封面"')
            await page.wait_for_timeout(2000)  # 等待2秒
            # 定位到上传区域并点击
            await page.locator("div[class^='semi-upload upload'] >> input.semi-upload-hidden-input").set_input_files(thumbnail_path)
            await page.wait_for_timeout(2000)  # 等待2秒
            await page.locator("div[class^='extractFooter'] button:visible:has-text('完成')").click()
            # finish_confirm_element = page.locator("div[class^='confirmBtn'] >> div:has-text('完成')")
            # if await finish_confirm_element.count():
            #     await finish_confirm_element.click()
            # await page.locator("div[class^='footer'] button:has-text('完成')").click()

    async def set_location(self, page: Page, location: str = "杭州市"):
        # todo supoort location later
        # await page.get_by_text('添加标签').locator("..").locator("..").locator("xpath=following-sibling::div").locator(
        #     "div.semi-select-single").nth(0).click()
        await page.locator('div.semi-select span:has-text("输入地理位置")').click()
        await page.keyboard.press("Backspace")
        await page.wait_for_timeout(2000)
        await page.keyboard.type(location)
        await page.wait_for_selector('div[role="listbox"] [role="option"]', timeout=5000)
        await page.locator('div[role="listbox"] [role="option"]').first.click()

    async def main(self):
        async with async_playwright() as playwright:
            await self.upload(playwright)


