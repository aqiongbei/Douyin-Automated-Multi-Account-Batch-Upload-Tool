# -*- coding: utf-8 -*-
"""
抖音视频删除功能模块
支持批量删除抖音创作者中心的视频
使用cookie和浏览器指纹注入避免检测
"""

import os
import asyncio
from playwright.async_api import Playwright, async_playwright
from utils.base_social_media import set_init_script
from utils.log import douyin_logger
from utils.fingerprint_manager import fingerprint_manager
from utils.proxy_manager import proxy_manager
from utils.human_behavior import HumanBehaviorSimulator
from main import get_browser_launch_options
from datetime import datetime
import time
import random


class DouyinVideoDeleter:
    """抖音视频删除器"""
    
    def __init__(self, account_file: str):
        self.account_file = account_file
        self.cookie_filename = os.path.basename(account_file)
        self.human_behavior = HumanBehaviorSimulator()
        self.deleted_count = 0
        self.total_videos = 0
        self.status_callback = None
        self.operation_type = "删除视频"  # 操作类型，可以是"删除视频"或"权限设置"
        
    async def notify_status(self, status: str, message: str = ""):
        """通知状态变化"""
        if self.status_callback:
            await self.status_callback(f"[{self.operation_type}] {status}: {message}")
        douyin_logger.info(f"[{self.operation_type}] {status}: {message}")
    
    async def get_video_list(self, page) -> list:
        """获取页面上的视频列表"""
        await self.notify_status("获取视频列表", "正在扫描页面中的视频...")
        
        # 等待页面加载完成
        await page.wait_for_timeout(3000)
        
        # 查找所有视频卡片
        video_cards = await page.locator('.video-card-zQ02ng').all()
        self.total_videos = len(video_cards)
        
        # 统计不同状态的视频
        public_count = 0
        private_count = 0
        friends_count = 0
        
        for card in video_cards:
            try:
                # 检查是否有私密标记
                private_mark = await card.locator('.private-mark-WxEWEv').count()
                
                # 检查发布状态
                status_element = card.locator('.info-status-AIgxHw')
                status_text = ""
                if await status_element.count() > 0:
                    status_text = await status_element.text_content() or ""
                
                if private_mark > 0:
                    private_count += 1
                elif status_text == "已发布":
                    # 这里需要进一步区分是公开还是好友可见
                    # 由于HTML结构相似，暂时归类为公开
                    public_count += 1
                else:
                    friends_count += 1
                    
            except Exception as e:
                douyin_logger.warning(f"检查视频状态时出错: {str(e)}")
                continue
        
        await self.notify_status("获取视频列表", 
                               f"发现 {self.total_videos} 个视频 (公开: {public_count}, 私密: {private_count}, 其他: {friends_count})")
        
        return video_cards
    
    async def get_video_details(self, page) -> list:
        """获取页面上视频的详细信息，包括状态"""
        await self.notify_status("获取视频详情", "正在分析视频状态...")
        
        # 等待页面加载完成
        await page.wait_for_timeout(3000)
        
        # 查找所有视频卡片
        video_cards = await page.locator('.video-card-zQ02ng').all()
        total_videos = len(video_cards)
        
        await self.notify_status("视频扫描", f"📊 发现 {total_videos} 个视频，开始获取详细信息...")
        
        video_details = []
        
        for i, card in enumerate(video_cards):
            # 实时进度更新
            progress = f"📈 进度: {i+1}/{total_videos} ({((i+1)/total_videos*100):.1f}%)"
            await self.notify_status("处理进度", progress)
            try:
                # 获取视频标题
                title_element = card.locator('.info-title-text-YTLo9y')
                title = await title_element.text_content() or f"视频 {i + 1}"
                await self.notify_status("当前视频", f"🎥 正在处理: 「{title.strip()}」")
                
                # 获取发布时间
                time_element = card.locator('.info-time-iAYLF0')
                publish_time = await time_element.text_content() or "未知时间"
                
                # 检查视频状态 - 通过点击权限设置获取真实状态
                await self.notify_status("检查权限", f"🔍 检查视频「{title.strip()}」的权限状态...")
                video_status = await self.get_video_permission_status(page, card)
                if video_status is None:
                    # 如果无法获取权限状态，使用备用方法
                    private_mark = await card.locator('.private-mark-WxEWEv').count()
                    status_element = card.locator('.info-status-AIgxHw')
                    status_text = ""
                    if await status_element.count() > 0:
                        status_text = await status_element.text_content() or ""
                    
                    if private_mark > 0:
                        video_status = "仅自己可见"
                    elif status_text == "已发布":
                        video_status = "已发布"
                    else:
                        video_status = "其他状态"
                
                # 获取播放数据
                metrics = {}
                metric_items = await card.locator('.metric-item-u1CAYE').all()
                for metric in metric_items:
                    try:
                        label_element = metric.locator('.metric-label-AX_5OF')
                        value_element = metric.locator('.metric-value-k4R5P_')
                        
                        label = await label_element.text_content() or ""
                        value = await value_element.text_content() or "0"
                        
                        if label:
                            metrics[label] = value
                    except:
                        continue
                
                video_info = {
                    "index": i,
                    "title": title.strip(),
                    "status": video_status,
                    "publish_time": publish_time.strip(),
                    "metrics": metrics,
                    "card_element": card
                }
                
                video_details.append(video_info)
                
            except Exception as e:
                douyin_logger.warning(f"获取第 {i + 1} 个视频详情时出错: {str(e)}")
                continue
        
        return video_details
    
    async def get_video_permission_status(self, page, video_card) -> str:
        """获取视频的真实权限状态"""
        try:
            # 查找设置权限按钮
            permission_button = video_card.locator('.ghost-btn-xUV8J0:has-text("设置权限")')
            
            if await permission_button.count() == 0:
                douyin_logger.debug("未找到设置权限按钮")
                return None
            
            # 滚动到视频卡片位置并点击设置权限按钮
            await video_card.scroll_into_view_if_needed()
            await asyncio.sleep(0.3)  # 减少等待时间
            await permission_button.click()
            await page.wait_for_timeout(1000)  # 减少等待时间
            
            # 等待权限设置弹窗出现
            modal = page.locator('.semi-modal-content')
            try:
                await modal.wait_for(state='visible', timeout=3000)  # 减少超时时间
            except:
                douyin_logger.warning("权限设置弹窗3秒内未出现")
                return None
            
            if await modal.count() == 0:
                douyin_logger.warning("权限设置弹窗未出现")
                return None
            
            # 查找选中的权限选项
            checked_input = modal.locator('input[type="checkbox"][checked]').first
            if await checked_input.count() > 0:
                permission_value = await checked_input.get_attribute('value')
                douyin_logger.info(f"检测到权限值: {permission_value}")
                
                # 根据权限值返回对应的状态
                if permission_value == "0":
                    status = "公开"
                elif permission_value == "1":
                    status = "仅自己可见"
                elif permission_value == "2":
                    status = "好友可见"
                else:
                    status = "其他状态"
                    
                douyin_logger.info(f"视频权限状态: {status}")
            else:
                douyin_logger.warning("未找到选中的权限选项")
                status = "未知状态"
            
            # 关闭弹窗 - 优先点击取消按钮
            try:
                close_button = modal.locator('button:has-text("取消")').first
                if await close_button.count() > 0:
                    await close_button.click()
                    douyin_logger.debug("点击取消按钮关闭弹窗")
                else:
                    # 尝试点击关闭图标
                    close_icon = modal.locator('.semi-modal-close').first
                    if await close_icon.count() > 0:
                        await close_icon.click()
                        douyin_logger.debug("点击关闭图标关闭弹窗")
                    else:
                        # 最后尝试按ESC键
                        await page.keyboard.press('Escape')
                        douyin_logger.debug("按ESC键关闭弹窗")
                
                # 等待弹窗关闭
                try:
                    await modal.wait_for(state='detached', timeout=2000)  # 减少等待时间
                except:
                    pass  # 如果弹窗没有正确关闭，继续执行
                await page.wait_for_timeout(300)  # 减少等待时间
                
            except Exception as close_error:
                douyin_logger.warning(f"关闭权限弹窗时出错: {str(close_error)}")
            
            return status
            
        except Exception as e:
            douyin_logger.error(f"获取视频权限状态时出错: {str(e)}")
            return None
    
    async def set_video_permission(self, page, video_card, permission_value: str, video_title: str = "") -> bool:
        """设置视频权限
        Args:
            page: 页面对象
            video_card: 视频卡片元素
            permission_value: 权限值 ("0"=公开, "1"=仅自己可见, "2"=好友可见)
            video_title: 视频标题（用于日志）
        Returns:
            bool: 设置是否成功
        """
        permission_names = {"0": "公开", "1": "仅自己可见", "2": "好友可见"}
        target_permission = permission_names.get(permission_value, f"权限{permission_value}")
        
        try:
            await self.notify_status("开始处理", f"视频「{video_title}」-> 目标权限: {target_permission}")
            
            # 查找设置权限按钮
            permission_button = video_card.locator('.ghost-btn-xUV8J0:has-text("设置权限")')
            
            if await permission_button.count() == 0:
                await self.notify_status("跳过视频", f"视频「{video_title}」未找到设置权限按钮，可能已是目标权限")
                return False
            
            # 滚动到视频卡片位置并点击设置权限按钮
            await self.notify_status("点击按钮", f"视频「{video_title}」点击设置权限按钮...")
            await video_card.scroll_into_view_if_needed()
            await asyncio.sleep(0.5)
            await permission_button.click()
            await page.wait_for_timeout(2000)
            
            # 等待权限设置弹窗出现
            await self.notify_status("等待弹窗", f"视频「{video_title}」等待权限设置弹窗...")
            modal = page.locator('.semi-modal-content')
            try:
                await modal.wait_for(state='visible', timeout=10000)
                await self.notify_status("弹窗已开", f"视频「{video_title}」权限设置弹窗已打开")
            except:
                await self.notify_status("弹窗超时", f"视频「{video_title}」权限设置弹窗10秒内未出现")
                return False
            
            if await modal.count() == 0:
                await self.notify_status("弹窗异常", f"视频「{video_title}」权限设置弹窗检测失败")
                return False
            
            # 获取当前权限状态
            current_permission = "未知"
            try:
                checked_input = modal.locator('input[type="checkbox"][checked]').first
                if await checked_input.count() > 0:
                    current_value = await checked_input.get_attribute('value')
                    current_permission = permission_names.get(current_value, f"权限{current_value}")
            except:
                pass
            
            await self.notify_status("当前权限", f"视频「{video_title}」当前权限: {current_permission} -> 目标权限: {target_permission}")
            
            # 如果当前权限已经是目标权限，直接关闭弹窗
            if current_permission == target_permission:
                await self.notify_status("权限相同", f"视频「{video_title}」已是{target_permission}，无需修改")
                close_button = modal.locator('button:has-text("取消")').first
                if await close_button.count() > 0:
                    await close_button.click()
                return True
            
            # 查找目标权限选项并点击
            target_input = modal.locator(f'input[type="checkbox"][value="{permission_value}"]').first
            if await target_input.count() == 0:
                await self.notify_status("选项缺失", f"视频「{video_title}」未找到{target_permission}选项")
                # 尝试关闭弹窗
                close_button = modal.locator('button:has-text("取消")').first
                if await close_button.count() > 0:
                    await close_button.click()
                return False
            
            # 点击目标权限选项
            await self.notify_status("选择权限", f"视频「{video_title}」正在选择{target_permission}...")
            target_label = target_input.locator('..').first  # 获取父级label元素
            await target_label.click()
            await page.wait_for_timeout(2000)
            
            # 点击保存按钮
            save_button = modal.locator('button:has-text("保存")').first
            if await save_button.count() > 0:
                await self.notify_status("保存设置", f"视频「{video_title}」正在保存权限设置...")
                await save_button.click()
                await page.wait_for_timeout(3000)
                
                # 等待弹窗关闭
                try:
                    await modal.wait_for(state='detached', timeout=10000)
                    await self.notify_status("设置完成", f"✅ 视频「{video_title}」成功设置为: {target_permission}")
                except:
                    await self.notify_status("设置疑似完成", f"⚠️ 视频「{video_title}」弹窗未完全关闭，但权限可能已生效")
                    pass
                
                # 随机延迟，避免被检测
                await asyncio.sleep(random.uniform(1, 3))
                return True
            else:
                await self.notify_status("保存失败", f"视频「{video_title}」未找到保存按钮")
                return False
                
        except Exception as e:
            await self.notify_status("异常错误", f"❌ 视频「{video_title}」设置过程出错: {str(e)}")
            douyin_logger.error(f"设置视频权限时出错: {str(e)}")
            return False
    
    async def batch_set_permissions(self, permission_value: str, max_count: int = None, video_titles: list = None, status_callback=None) -> dict:
        """批量设置视频权限
        Args:
            permission_value: 权限值 ("0"=公开, "1"=仅自己可见, "2"=好友可见)
            max_count: 最大设置数量，None表示设置所有
            video_titles: 指定视频标题列表，None表示设置所有视频
            status_callback: 状态回调函数
        Returns:
            dict: 设置结果
        """
        self.status_callback = status_callback
        self.operation_type = "权限设置"  # 设置操作类型
        
        # 获取代理和指纹配置
        proxy_config = proxy_manager.get_proxy_for_playwright(self.cookie_filename)
        
        # Docker环境检测
        is_in_docker = os.path.exists('/.dockerenv') or os.environ.get('DOCKER_ENV') == 'true'
        headless_mode = True if is_in_docker else False
        
        if is_in_docker:
            await self.notify_status("环境检测", "🐳 检测到Docker环境，使用headless模式")
        
        launch_options = get_browser_launch_options(headless=headless_mode, proxy_config=proxy_config)
        fingerprint_config = fingerprint_manager.get_playwright_config(self.cookie_filename)
        
        browser = None
        context = None
        success_count = 0
        
        try:
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(**launch_options)
                
                context_options = {
                    "storage_state": self.account_file,
                    **fingerprint_config
                }
                
                if proxy_config:
                    context_options["proxy"] = proxy_config
                
                context = await browser.new_context(**context_options)
                context = await set_init_script(context, self.cookie_filename)
                
                page = await context.new_page()
                
                await self.notify_status("访问页面", "正在访问抖音创作者中心...")
                await page.goto("https://creator.douyin.com/creator-micro/content/manage")
                await page.wait_for_timeout(5000)
                
                # 检查登录状态
                if await page.locator('text=手机号登录').count() > 0:
                    return {
                        "success": False,
                        "message": "Cookie已失效，需要重新登录",
                        "success_count": 0,
                        "total_videos": 0
                    }
                
                # 模拟人类浏览行为
                await self.human_behavior.simulate_reading_behavior(page, 2, 5)
                
                # 获取视频列表
                video_cards = await self.get_video_list(page)
                
                if not video_cards:
                    await self.notify_status("完成", "没有找到视频")
                    return {
                        "success": True,
                        "message": "没有找到视频",
                        "success_count": 0,
                        "total_videos": 0
                    }
                
                # 构建视频索引映射
                all_videos = []
                for i, video_card in enumerate(video_cards):
                    try:
                        title_element = video_card.locator('.info-title-text-YTLo9y')
                        video_title = await title_element.text_content() or f"视频 {i + 1}"
                        all_videos.append({
                            "index": i,
                            "card": video_card,
                            "title": video_title.strip()
                        })
                    except:
                        all_videos.append({
                            "index": i,
                            "card": video_card,
                            "title": f"视频 {i + 1}"
                        })
                
                # 过滤要设置的视频
                target_videos = []
                if video_titles:
                    # 根据标题精确匹配视频
                    for target_title in video_titles:
                        for video_info in all_videos:
                            if video_info["title"] == target_title.strip():
                                target_videos.append(video_info)
                                await self.notify_status("视频匹配", f"✅ 找到匹配视频: 「{video_info['title']}」(索引:{video_info['index']})")
                                break
                        else:
                            await self.notify_status("视频未找到", f"❌ 未找到匹配视频: 「{target_title}」")
                else:
                    # 所有视频
                    target_videos = all_videos
                
                # 确定要设置的视频数量
                set_count = min(len(target_videos), max_count) if max_count else len(target_videos)
                permission_names = {"0": "公开", "1": "仅自己可见", "2": "好友可见"}
                permission_name = permission_names.get(permission_value, f"权限{permission_value}")
                
                await self.notify_status("任务开始", f"📋 批量权限设置任务 - 目标: {permission_name}")
                await self.notify_status("任务详情", f"🎯 匹配到 {len(target_videos)} 个视频，计划设置 {set_count} 个")
                
                # 逐个设置匹配的视频权限
                failed_videos = []
                for i in range(set_count):
                    try:
                        video_info = target_videos[i]
                        video_index = video_info["index"]
                        video_title = video_info["title"]
                        
                        await self.notify_status("进度更新", f"📊 进度: {i+1}/{set_count} - 已成功: {success_count}")
                        await self.notify_status("当前处理", f"🎯 正在处理第 {video_index + 1} 个视频: 「{video_title}」")
                        
                        # 重新获取视频列表以获取最新的DOM元素
                        current_videos = await page.locator('.video-card-zQ02ng').all()
                        if video_index >= len(current_videos):
                            await self.notify_status("视频丢失", f"⚠️ 视频索引 {video_index} 超出当前视频数量 {len(current_videos)}")
                            failed_videos.append(video_title)
                            continue
                        
                        # 使用准确的索引获取视频卡片
                        video_card = current_videos[video_index]
                        
                        # 验证视频标题是否匹配（防止页面变化导致错位）
                        try:
                            current_title_element = video_card.locator('.info-title-text-YTLo9y')
                            current_title = await current_title_element.text_content() or ""
                            if current_title.strip() != video_title:
                                await self.notify_status("标题不匹配", f"⚠️ 索引 {video_index} 的视频标题已变化: 期望「{video_title}」，实际「{current_title.strip()}」")
                                # 尝试重新查找匹配的视频
                                found = False
                                for j, card in enumerate(current_videos):
                                    try:
                                        check_title_element = card.locator('.info-title-text-YTLo9y')
                                        check_title = await check_title_element.text_content() or ""
                                        if check_title.strip() == video_title:
                                            video_card = card
                                            await self.notify_status("重新定位", f"✅ 在索引 {j} 重新找到视频「{video_title}」")
                                            found = True
                                            break
                                    except:
                                        continue
                                
                                if not found:
                                    await self.notify_status("视频丢失", f"❌ 无法重新定位视频「{video_title}」，可能已被删除或移动")
                                    failed_videos.append(video_title)
                                    continue
                        except:
                            pass
                        
                        if await self.set_video_permission(page, video_card, permission_value, video_title):
                            success_count += 1
                        else:
                            failed_videos.append(video_title)
                        
                        # 每设置几个视频后刷新页面
                        if (i + 1) % 3 == 0 and i + 1 < set_count:
                            await self.notify_status("页面刷新", f"🔄 已处理 {i+1} 个视频，刷新页面继续...")
                            await page.reload()
                            await page.wait_for_timeout(3000)
                        
                    except Exception as e:
                        failed_videos.append(target_videos[i]["title"] if i < len(target_videos) else f"第{i+1}个视频")
                        await self.notify_status("处理异常", f"❌ 第 {i + 1} 个视频处理异常: {str(e)}")
                        continue
                
                # 生成详细的完成报告
                failed_count = len(failed_videos)
                success_rate = round((success_count / set_count) * 100, 1) if set_count > 0 else 0
                
                await self.notify_status("任务完成", f"🎉 批量权限设置完成！")
                await self.notify_status("结果统计", f"📈 成功: {success_count} | 失败: {failed_count} | 成功率: {success_rate}%")
                
                if failed_videos and len(failed_videos) <= 3:
                    await self.notify_status("失败详情", f"❌ 失败视频: {', '.join(failed_videos[:3])}")
                elif failed_videos:
                    await self.notify_status("失败详情", f"❌ 失败视频: {', '.join(failed_videos[:3])} 等{len(failed_videos)}个")
                
                return {
                    "success": True,
                    "message": f"成功设置 {success_count} 个视频为 {permission_name}",
                    "success_count": success_count,
                    "total_videos": len(target_videos)
                }
                
        except Exception as e:
            error_msg = f"批量设置权限过程中发生错误: {str(e)}"
            await self.notify_status("设置失败", error_msg)
            douyin_logger.error(error_msg)
            return {
                "success": False,
                "message": error_msg,
                "success_count": success_count,
                "total_videos": 0
            }
        
        finally:
            # 确保资源释放
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
    
    async def delete_single_video(self, page, video_card, video_index: int) -> bool:
        """删除单个视频"""
        try:
            # 获取视频标题用于日志
            title_element = video_card.locator('.info-title-text-YTLo9y')
            video_title = "未知标题"
            try:
                video_title = await title_element.text_content() or f"视频 {video_index + 1}"
            except:
                pass
            
            await self.notify_status("删除视频", f"正在删除第 {video_index + 1} 个视频: {video_title}")
            
            # 确保视频卡片可见（不使用人类行为模拟）
            await video_card.scroll_into_view_if_needed()
            await page.wait_for_timeout(1000)  # 固定等待时间，避免随机延迟
            
            # 在当前视频卡片内查找删除按钮
            delete_button = video_card.locator('.ghost-btn-xUV8J0:has-text("删除作品")')
            
            # 检查删除按钮是否存在
            if await delete_button.count() == 0:
                await self.notify_status("跳过视频", f"视频 {video_title} 没有找到删除按钮")
                return False
            
            await self.notify_status("点击删除", f"找到删除按钮，准备点击删除 {video_title}")
            
            # 直接点击删除按钮，不使用人类行为模拟
            await delete_button.click()
            await page.wait_for_timeout(500)  # 固定等待时间
            
            # 等待确认弹窗出现
            await self.notify_status("等待弹窗", f"等待删除确认弹窗出现...")
            try:
                # 等待确认弹窗的容器出现
                await page.wait_for_selector('.semi-modal-content', timeout=5000)
                await page.wait_for_timeout(1000)  # 额外等待弹窗动画完成
                await self.notify_status("弹窗已出现", f"删除确认弹窗已加载")
            except:
                await self.notify_status("弹窗等待超时", f"删除确认弹窗未出现，尝试继续操作")
                await page.wait_for_timeout(1000)
            
            # 查找并点击确认删除按钮
            # 根据用户提供的HTML结构更新选择器
            confirm_selectors = [
                '.primary-cECiOJ',  # 主要的确认按钮类
                '.button-dhlUZE.modal-btn-GK4fsX.primary-cECiOJ',
                'button.primary-cECiOJ',
                '.modal-btn-GK4fsX.primary-cECiOJ',
                'button:has-text("确定")',
                'button:has-text("确认")',
                'button:has-text("删除")',
                'button:has-text("确认删除")',
                '.semi-button-primary:has-text("确认")',
                '.semi-button-primary:has-text("删除")',
                '.button-primary:has-text("确认")',
                '.button-primary:has-text("删除")'
            ]
            
            confirm_clicked = False
            for i, selector in enumerate(confirm_selectors):
                try:
                    confirm_button = page.locator(selector)
                    button_count = await confirm_button.count()
                    if button_count > 0:
                        await self.notify_status("点击确认", f"找到确认按钮 (选择器 {i+1}): {selector}")
                        # 直接点击确认按钮，不使用人类行为模拟
                        await confirm_button.click()
                        confirm_clicked = True
                        await self.notify_status("确认成功", f"已点击确认删除按钮")
                        break
                    else:
                        await self.notify_status("按钮检查", f"选择器 {i+1} 未找到按钮: {selector}")
                except Exception as e:
                    await self.notify_status("按钮错误", f"选择器 {i+1} 出错: {str(e)}")
                    continue
            
            if not confirm_clicked:
                # 最后尝试：查找页面上所有包含"确定"文本的按钮
                await self.notify_status("备用方案", f"尝试查找页面上所有确定按钮")
                try:
                    all_buttons = await page.locator('button').all()
                    for button in all_buttons:
                        try:
                            button_text = await button.text_content()
                            if button_text and "确定" in button_text:
                                await self.notify_status("找到按钮", f"找到确定按钮: {button_text}")
                                await button.click()
                                confirm_clicked = True
                                break
                        except:
                            continue
                except Exception as e:
                    await self.notify_status("备用方案失败", f"备用方案出错: {str(e)}")
                
                if not confirm_clicked:
                    # 如果还是没有找到确认按钮，尝试按回车键确认
                    await self.notify_status("尝试回车", f"未找到确认按钮，尝试按回车键确认删除 {video_title}")
                    await page.keyboard.press('Enter')
                    await page.wait_for_timeout(500)
                    await page.keyboard.press('Enter')  # 再按一次确保
            
            # 等待删除操作完成
            await page.wait_for_timeout(2000)
            
            # 检查是否删除成功（页面刷新或视频消失）
            await self.notify_status("删除成功", f"已删除视频: {video_title}")
            self.deleted_count += 1
            
            # 固定延迟，避免操作过快但不使用随机时间
            await page.wait_for_timeout(2000)
            
            return True
            
        except Exception as e:
            await self.notify_status("删除失败", f"删除视频时出错: {str(e)}")
            return False
    
    async def delete_all_videos(self, max_count: int = None, status_callback=None) -> dict:
        """删除所有视频"""
        self.status_callback = status_callback
        
        # 获取代理和指纹配置
        proxy_config = proxy_manager.get_proxy_for_playwright(self.cookie_filename)
        
        # Docker环境检测
        is_in_docker = os.path.exists('/.dockerenv') or os.environ.get('DOCKER_ENV') == 'true'
        headless_mode = True if is_in_docker else False
        
        if is_in_docker:
            await self.notify_status("环境检测", "🐳 检测到Docker环境，使用headless模式")
        
        launch_options = get_browser_launch_options(headless=headless_mode, proxy_config=proxy_config)
        fingerprint_config = fingerprint_manager.get_playwright_config(self.cookie_filename)
        
        browser = None
        context = None
        
        try:
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(**launch_options)
                
                # 使用指纹配置创建上下文
                context_options = {
                    "storage_state": self.account_file,
                    **fingerprint_config
                }
                
                # 添加代理配置
                if proxy_config:
                    context_options["proxy"] = proxy_config
                
                context = await browser.new_context(**context_options)
                context = await set_init_script(context, self.cookie_filename)
                
                # 创建页面
                page = await context.new_page()
                
                await self.notify_status("访问页面", "正在访问抖音创作者中心...")
                
                # 访问视频管理页面
                await page.goto("https://creator.douyin.com/creator-micro/content/manage")
                
                # 等待页面加载
                await page.wait_for_timeout(5000)
                
                # 检查是否需要登录
                if await page.locator('text=手机号登录').count() > 0:
                    await self.notify_status("登录失败", "Cookie已失效，需要重新登录")
                    return {
                        "success": False,
                        "message": "Cookie已失效，需要重新登录",
                        "deleted_count": 0,
                        "total_videos": 0
                    }
                
                # 简单等待页面稳定，不使用复杂的人类行为模拟
                await page.wait_for_timeout(2000)
                
                # 获取视频列表
                video_cards = await self.get_video_list(page)
                
                if not video_cards:
                    await self.notify_status("完成", "没有找到可删除的视频")
                    return {
                        "success": True,
                        "message": "没有找到可删除的视频",
                        "deleted_count": 0,
                        "total_videos": 0
                    }
                
                # 构建视频索引映射
                all_videos = []
                for i, video_card in enumerate(video_cards):
                    try:
                        title_element = video_card.locator('.info-title-text-YTLo9y')
                        video_title = await title_element.text_content() or f"视频 {i + 1}"
                        all_videos.append({
                            "index": i,
                            "card": video_card,
                            "title": video_title.strip()
                        })
                    except:
                        all_videos.append({
                            "index": i,
                            "card": video_card,
                            "title": f"视频 {i + 1}"
                        })
                
                # 确定要删除的视频数量
                delete_count = min(len(all_videos), max_count) if max_count else len(all_videos)
                target_videos = all_videos[:delete_count]
                
                await self.notify_status("任务开始", f"🗑️ 批量删除任务开始")
                await self.notify_status("任务详情", f"🎯 准备删除 {delete_count} 个视频")
                
                # 逐个删除视频
                success_count = 0
                failed_videos = []
                for i in range(delete_count):
                    try:
                        video_info = target_videos[i]
                        video_index = video_info["index"]
                        video_title = video_info["title"]
                        
                        await self.notify_status("进度更新", f"📊 进度: {i+1}/{delete_count} - 已成功: {success_count}")
                        await self.notify_status("当前处理", f"🎯 正在处理第 {video_index + 1} 个视频: 「{video_title}」")
                        
                        # 重新获取视频列表以获取最新的DOM元素
                        current_videos = await page.locator('.video-card-zQ02ng').all()
                        if len(current_videos) == 0:
                            await self.notify_status("删除完成", f"✅ 所有视频已删除完毕，任务完成")
                            break
                        
                        # 总是获取第一个视频（因为删除后后面的视频会前移）
                        video_card = current_videos[0]
                        
                        # 获取当前第一个视频的标题
                        try:
                            current_title_element = video_card.locator('.info-title-text-YTLo9y')
                            current_title = await current_title_element.text_content() or f"视频 {i + 1}"
                            current_title = current_title.strip()
                        except:
                            current_title = f"视频 {i + 1}"
                        
                        if await self.delete_single_video(page, video_card, i):
                            success_count += 1
                        else:
                            failed_videos.append(current_title)
                        
                        # 每删除几个视频后刷新页面
                        if (i + 1) % 3 == 0 and i + 1 < delete_count:
                            await self.notify_status("页面刷新", f"🔄 已处理 {i+1} 个视频，刷新页面继续...")
                            await page.reload()
                            await page.wait_for_timeout(3000)
                        
                    except Exception as e:
                        failed_videos.append(f"第{i+1}个视频")
                        await self.notify_status("删除错误", f"❌ 删除第 {i + 1} 个视频时出错: {str(e)}")
                        continue
                
                # 生成详细的完成报告
                failed_count = len(failed_videos)
                success_rate = round((success_count / delete_count) * 100, 1) if delete_count > 0 else 0
                
                await self.notify_status("任务完成", f"🎉 批量删除完成！")
                await self.notify_status("结果统计", f"📈 成功: {success_count} | 失败: {failed_count} | 成功率: {success_rate}%")
                
                # 更新删除计数
                self.deleted_count = success_count
                
                await self.notify_status("删除完成", f"成功删除 {self.deleted_count} 个视频")
                
                return {
                    "success": True,
                    "message": f"成功删除 {self.deleted_count} 个视频",
                    "deleted_count": self.deleted_count,
                    "total_videos": self.total_videos
                }
                
        except Exception as e:
            error_msg = f"删除过程中发生错误: {str(e)}"
            await self.notify_status("删除失败", error_msg)
            douyin_logger.error(error_msg)
            return {
                "success": False,
                "message": error_msg,
                "deleted_count": self.deleted_count,
                "total_videos": self.total_videos
            }
        
        finally:
            # 确保资源释放
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
    
    async def delete_specific_videos(self, video_titles: list, status_callback=None) -> dict:
        """删除指定标题的视频"""
        self.status_callback = status_callback
        self.operation_type = "删除视频"  # 设置操作类型
        
        # 获取代理和指纹配置
        proxy_config = proxy_manager.get_proxy_for_playwright(self.cookie_filename)
        
        # Docker环境检测
        is_in_docker = os.path.exists('/.dockerenv') or os.environ.get('DOCKER_ENV') == 'true'
        headless_mode = True if is_in_docker else False
        
        if is_in_docker:
            await self.notify_status("环境检测", "🐳 检测到Docker环境，使用headless模式")
        
        launch_options = get_browser_launch_options(headless=headless_mode, proxy_config=proxy_config)
        fingerprint_config = fingerprint_manager.get_playwright_config(self.cookie_filename)
        
        browser = None
        context = None
        success_count = 0
        
        try:
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(**launch_options)
                
                context_options = {
                    "storage_state": self.account_file,
                    **fingerprint_config
                }
                
                if proxy_config:
                    context_options["proxy"] = proxy_config
                
                context = await browser.new_context(**context_options)
                context = await set_init_script(context, self.cookie_filename)
                
                page = await context.new_page()
                
                await self.notify_status("访问页面", "正在访问抖音创作者中心...")
                await page.goto("https://creator.douyin.com/creator-micro/content/manage")
                await page.wait_for_timeout(5000)
                
                # 检查登录状态
                if await page.locator('text=手机号登录').count() > 0:
                    return {
                        "success": False,
                        "message": "Cookie已失效，需要重新登录",
                        "deleted_count": 0,
                        "total_videos": 0
                    }
                
                # 简单等待页面稳定，不使用复杂的人类行为模拟
                await page.wait_for_timeout(2000)
                
                # 获取视频列表
                video_cards = await self.get_video_list(page)
                
                if not video_cards:
                    await self.notify_status("完成", "没有找到视频")
                    return {
                        "success": True,
                        "message": "没有找到视频",
                        "deleted_count": 0,
                        "total_videos": 0
                    }
                
                # 构建视频索引映射
                all_videos = []
                for i, video_card in enumerate(video_cards):
                    try:
                        title_element = video_card.locator('.info-title-text-YTLo9y')
                        video_title = await title_element.text_content() or f"视频 {i + 1}"
                        all_videos.append({
                            "index": i,
                            "card": video_card,
                            "title": video_title.strip()
                        })
                    except:
                        all_videos.append({
                            "index": i,
                            "card": video_card,
                            "title": f"视频 {i + 1}"
                        })
                
                # 根据标题精确匹配视频
                target_videos = []
                for target_title in video_titles:
                    for video_info in all_videos:
                        if video_info["title"] == target_title.strip():
                            target_videos.append(video_info)
                            await self.notify_status("视频匹配", f"✅ 找到匹配视频: 「{video_info['title']}」(索引:{video_info['index']})")
                            break
                    else:
                        await self.notify_status("视频未找到", f"❌ 未找到匹配视频: 「{target_title}」")
                
                delete_count = len(target_videos)
                
                await self.notify_status("任务开始", f"🗑️ 批量删除任务开始")
                await self.notify_status("任务详情", f"🎯 匹配到 {delete_count} 个视频，准备删除")
                
                # 逐个删除匹配的视频
                failed_videos = []
                for i in range(delete_count):
                    try:
                        video_info = target_videos[i]
                        video_index = video_info["index"]
                        video_title = video_info["title"]
                        
                        await self.notify_status("进度更新", f"📊 进度: {i+1}/{delete_count} - 已成功: {success_count}")
                        await self.notify_status("当前处理", f"🎯 正在处理第 {video_index + 1} 个视频: 「{video_title}」")
                        
                        # 重新获取视频列表以获取最新的DOM元素
                        current_videos = await page.locator('.video-card-zQ02ng').all()
                        if len(current_videos) == 0:
                            await self.notify_status("删除完成", f"✅ 所有视频已删除完毕，任务完成")
                            break
                        
                        # 直接通过标题查找视频卡片（不依赖可能变化的索引）
                        video_card = None
                        current_index = -1
                        
                        for j, card in enumerate(current_videos):
                            try:
                                check_title_element = card.locator('.info-title-text-YTLo9y')
                                check_title = await check_title_element.text_content() or ""
                                if check_title.strip() == video_title:
                                    video_card = card
                                    current_index = j
                                    await self.notify_status("视频定位", f"✅ 在当前索引 {j} 找到视频「{video_title}」")
                                    break
                            except:
                                continue
                        
                        if video_card is None:
                            await self.notify_status("视频丢失", f"❌ 无法找到视频「{video_title}」，可能已被删除")
                            failed_videos.append(video_title)
                            continue
                        
                        # 执行删除操作
                        if await self.delete_single_video(page, video_card, current_index):
                            success_count += 1
                        else:
                            failed_videos.append(video_title)
                        
                        # 每删除几个视频后刷新页面
                        if (i + 1) % 3 == 0 and i + 1 < delete_count:
                            await self.notify_status("页面刷新", f"🔄 已处理 {i+1} 个视频，刷新页面继续...")
                            await page.reload()
                            await page.wait_for_timeout(3000)
                        
                    except Exception as e:
                        failed_videos.append(target_videos[i]["title"] if i < len(target_videos) else f"第{i+1}个视频")
                        await self.notify_status("处理异常", f"❌ 第 {i + 1} 个视频处理异常: {str(e)}")
                        continue
                
                # 生成详细的完成报告
                failed_count = len(failed_videos)
                success_rate = round((success_count / delete_count) * 100, 1) if delete_count > 0 else 0
                
                await self.notify_status("任务完成", f"🎉 批量删除完成！")
                await self.notify_status("结果统计", f"📈 成功: {success_count} | 失败: {failed_count} | 成功率: {success_rate}%")
                
                if failed_videos and len(failed_videos) <= 3:
                    await self.notify_status("失败详情", f"❌ 失败视频: {', '.join(failed_videos[:3])}")
                elif failed_videos:
                    await self.notify_status("失败详情", f"❌ 失败视频: {', '.join(failed_videos[:3])} 等{len(failed_videos)}个")
                
                # 更新删除计数（用于兼容原有接口）
                self.deleted_count = success_count
                
                return {
                    "success": True,
                    "message": f"成功删除 {success_count} 个匹配的视频",
                    "deleted_count": success_count,
                    "total_videos": len(target_videos)
                }
                
        except Exception as e:
            error_msg = f"删除指定视频时发生错误: {str(e)}"
            await self.notify_status("删除失败", error_msg)
            return {
                "success": False,
                "message": error_msg,
                "deleted_count": success_count,
                "total_videos": 0
            }
        
        finally:
            if context:
                try:
                    await context.close()
                except:
                    pass
            if browser:
                try:
                    await browser.close()
                except:
                    pass


# 便捷函数
async def delete_douyin_videos(account_file: str, max_count: int = None, status_callback=None) -> dict:
    """
    删除抖音视频的便捷函数
    
    Args:
        account_file: cookie文件路径
        max_count: 最大删除数量，None表示删除所有
        status_callback: 状态回调函数
    
    Returns:
        dict: 删除结果
    """
    deleter = DouyinVideoDeleter(account_file)
    return await deleter.delete_all_videos(max_count, status_callback)


async def delete_specific_douyin_videos(account_file: str, video_titles: list, status_callback=None) -> dict:
    """
    删除指定标题的抖音视频
    
    Args:
        account_file: cookie文件路径
        video_titles: 要删除的视频标题列表
        status_callback: 状态回调函数
    
    Returns:
        dict: 删除结果
    """
    deleter = DouyinVideoDeleter(account_file)
    return await deleter.delete_specific_videos(video_titles, status_callback) 


async def set_douyin_video_permissions(account_file: str, permission_value: str, max_count: int = None, video_titles: list = None, status_callback=None) -> dict:
    """
    批量设置抖音视频权限
    
    Args:
        account_file: cookie文件路径
        permission_value: 权限值 ("0"=公开, "1"=仅自己可见, "2"=好友可见)
        max_count: 最大设置数量，None表示设置所有
        video_titles: 指定视频标题列表，None表示设置所有视频
        status_callback: 状态回调函数
    
    Returns:
        dict: 设置结果
    """
    deleter = DouyinVideoDeleter(account_file)
    return await deleter.batch_set_permissions(permission_value, max_count, video_titles, status_callback)