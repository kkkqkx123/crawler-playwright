import asyncio
import random
import os
import re
import httpx
from typing import Tuple, List
import cv2
import numpy as np
from PIL import Image
from playwright.async_api import async_playwright, Page, Frame
import io


class FrameManager:
    """管理多层 iframe 的工具类"""
    
    def __init__(self, page: Page):
        self.page = page
    
    async def get_all_frames(self) -> List[Frame]:
        """获取所有框架（包括嵌套 iframe）"""
        frames = []
        stack = list(self.page.frames)
        
        while stack:
            frame = stack.pop()
            frames.append(frame)
            # 递归添加子框架
            child_frames = frame.child_frames
            stack.extend(child_frames)
        return frames
    
    async def find_frame_by_url(self, url_pattern: str) -> Frame:
        """根据 URL 模式查找框架"""
        frames = await self.get_all_frames()
        for frame in frames:
            if url_pattern in frame.url:
                return frame
        raise Exception(f"未找到匹配 {url_pattern} 的框架")
    
    async def find_frame_by_selector(self, selector: str, timeout: int = 5000) -> Frame:
        """查找包含特定选择器的框架"""
        frames = await self.get_all_frames()
        
        for frame in frames:
            try:
                element = await frame.wait_for_selector(selector, timeout=1000)
                if element:
                    return frame
            except:
                continue
        
        raise Exception(f"未找到包含选择器 {selector} 的框架")
    
    async def wait_for_frame_load(self, frame: Frame, timeout: int = 10000):
        """等待框架完全加载"""
        try:
            await frame.wait_for_load_state("networkidle", timeout=timeout)
        except:
            # 如果 networkidle 失败，至少等待 domcontentloaded
            await frame.wait_for_load_state("domcontentloaded", timeout=timeout)


class TencentSliderCaptcha:
    def __init__(self, frame: Frame | Page):
        """初始化，支持 Page 或 Frame"""
        self.frame = frame
    
    def _get_mouse(self):
        """获取 mouse 对象（Frame 需要通过 page 获取，Page 直接有 mouse）"""
        frame = self.frame
        # Page 有 mouse 属性，Frame 没有需要通过 page 获取
        if hasattr(frame, 'page'):
            return frame.page.mouse  # type: ignore
        return frame.mouse  # type: ignore
        
    async def get_slider_position(self) -> Tuple[int, int, int, int]:
        """获取滑块元素的位置和大小"""
        slider = await self.frame.query_selector(".tc-fg-item.tc-slider-normal")
        if not slider:
            raise Exception("未找到滑块元素")
        
        box = await slider.bounding_box()
        if box is None:
            raise Exception("无法获取滑块边界框")
        return (int(box['x']), int(box['y']), int(box['width']), int(box['height']))
    
    async def get_background_image_url(self) -> str:
        """从 CSS 样式中提取背景图的原始 URL"""
        bg_element = await self.frame.query_selector("#slideBg")
        if not bg_element:
            raise Exception("未找到背景图元素")

        # 获取 style 属性
        style = await bg_element.get_attribute("style")
        if not style:
            raise Exception("未找到 style 属性")

        print(f"背景图元素 style: {style[:200]}...")

        # 提取 background-image URL
        # 格式: background-image: url("https://...")
        # 注意：HTML 中 & 可能被转义为 &amp;
        match = re.search(r'background-image:\s*url\(["\']([^"\']+)["\']\)', style)
        if match:
            url = match.group(1)
            # 处理 HTML 实体转义
            url = url.replace('&amp;', '&')
            return url

        raise Exception(f"无法从 style 中提取背景图 URL")

    async def get_slider_template_url(self) -> Tuple[str, dict]:
        """
        从 CSS 样式中提取缺口模板图的原始 URL 和位置信息
        返回: (url, position_info)
        """
        slider_items = await self.frame.query_selector_all(".tc-fg-item")
        for item in slider_items:
            class_name = await item.get_attribute("class")
            if class_name and "tc-slider-normal" not in class_name:
                style = await item.get_attribute("style")
                if not style:
                    continue

                print(f"待滑动块元素 style: {style[:300]}...")

                # 提取 URL
                url_match = re.search(r'background-image:\s*url\(["\']([^"\']+)["\']\)', style)
                if not url_match:
                    continue

                url = url_match.group(1)
                # 处理 HTML 实体转义
                url = url.replace('&amp;', '&')

                # 提取 background-position (裁剪位置)
                pos_match = re.search(r'background-position:\s*(-?[\d.]+)px\s+(-?[\d.]+)px', style)
                # 提取 background-size (大图显示尺寸)
                size_match = re.search(r'background-size:\s*([\d.]+)px\s+([\d.]+)px', style)
                # 提取元素显示尺寸
                width_match = re.search(r'width:\s*([\d.]+)px', style)
                height_match = re.search(r'height:\s*([\d.]+)px', style)
                # 提取元素位置
                left_match = re.search(r'left:\s*([\d.]+)px', style)

                position_info = {
                    'bg_position_x': float(pos_match.group(1)) if pos_match else 0,
                    'bg_position_y': float(pos_match.group(2)) if pos_match else 0,
                    'bg_size_w': float(size_match.group(1)) if size_match else 0,
                    'bg_size_h': float(size_match.group(2)) if size_match else 0,
                    'display_w': float(width_match.group(1)) if width_match else 0,
                    'display_h': float(height_match.group(1)) if height_match else 0,
                    'left': float(left_match.group(1)) if left_match else 0,
                }

                return url, position_info

        raise Exception("未找到缺口模板元素")

    async def download_image(self, url: str) -> np.ndarray:
        """下载图片并转换为 OpenCV 格式（保留透明通道）"""
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(url)
            if response.status_code != 200:
                raise Exception(f"下载图片失败: {response.status_code}")

            image = Image.open(io.BytesIO(response.content))

            # 检查是否有透明通道
            if image.mode == 'RGBA':
                # 保留透明通道
                return cv2.cvtColor(np.array(image), cv2.COLOR_RGBA2BGRA)
            else:
                # 无透明通道
                return cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)

    async def get_background_image(self, save_debug: bool = False) -> np.ndarray:
        """获取背景图（下载原始图片）"""
        url = await self.get_background_image_url()
        print(f"背景图 URL: {url[:80]}...")

        image = await self.download_image(url)

        if save_debug:
            cv2.imwrite("debug_background.png", image)
            print(f"背景图已保存: debug_background.png, 尺寸: {image.shape[:2]}")

        return image

    async def get_slider_image(self, save_debug: bool = False) -> Tuple[np.ndarray, dict]:
        """
        获取缺口模板图（从大图裁剪正确区域）
        返回: (缺口模板图, 位置信息)
        """
        url, pos_info = await self.get_slider_template_url()
        print(f"缺口模板 URL: {url[:80]}...")
        print(f"位置信息: {pos_info}")

        # 下载原始大图
        full_image = await self.download_image(url)

        if save_debug:
            cv2.imwrite("debug_slider_full.png", full_image)
            print(f"缺口模板大图已保存: debug_slider_full.png, 尺寸: {full_image.shape[:2]}")

        h_full, w_full = full_image.shape[:2]

        # 计算缩放比例: 原图尺寸 / CSS background-size
        # background-size 是大图在 CSS 中的显示尺寸
        scale_x = w_full / pos_info['bg_size_w'] if pos_info['bg_size_w'] > 0 else 1
        scale_y = h_full / pos_info['bg_size_h'] if pos_info['bg_size_h'] > 0 else 1

        print(f"大图原始尺寸: {w_full}x{h_full}")
        print(f"CSS background-size: {pos_info['bg_size_w']}x{pos_info['bg_size_h']}")
        print(f"缩放比例: x={scale_x:.4f}, y={scale_y:.4f}")

        # background-position 是负值，表示从大图的该位置开始显示
        # 转换为原图坐标
        crop_x = int(abs(pos_info['bg_position_x']) * scale_x)
        crop_y = int(abs(pos_info['bg_position_y']) * scale_y)
        crop_w = int(pos_info['display_w'] * scale_x)
        crop_h = int(pos_info['display_h'] * scale_y)

        print(f"裁剪区域: x={crop_x}, y={crop_y}, w={crop_w}, h={crop_h}")

        # 确保不越界
        crop_x = min(crop_x, w_full - 1)
        crop_y = min(crop_y, h_full - 1)
        crop_w = min(crop_w, w_full - crop_x)
        crop_h = min(crop_h, h_full - crop_y)

        if crop_w > 0 and crop_h > 0:
            template = full_image[crop_y:crop_y+crop_h, crop_x:crop_x+crop_w]
        else:
            raise Exception(f"裁剪区域无效: crop_x={crop_x}, crop_y={crop_y}, crop_w={crop_w}, crop_h={crop_h}")

        if save_debug:
            cv2.imwrite("debug_slider_template.png", template)
            print(f"缺口模板已保存: debug_slider_template.png, 尺寸: {template.shape[:2]}")

        return template, pos_info

    def find_gap_position(self, background: np.ndarray, slider: np.ndarray) -> int:
        """
        找到缺口位置
        优先使用边缘检测法，模板匹配作为备选
        """
        # 方法一：边缘检测法（更可靠）
        gap_x = self._find_gap_by_edge(background, slider)
        if gap_x > 0:
            return gap_x

        # 方法二：模板匹配法（备选）
        return self._find_gap_by_template(background, slider)

    def _find_gap_by_edge(self, background: np.ndarray, slider: np.ndarray) -> int:
        """
        通过边缘检测找到缺口位置
        原理：背景图中的缺口有明显的边缘特征
        """
        # 转换为灰度图
        if len(background.shape) == 3 and background.shape[2] == 4:
            bg_gray = cv2.cvtColor(background, cv2.COLOR_BGRA2GRAY)
        else:
            bg_gray = cv2.cvtColor(background, cv2.COLOR_BGR2GRAY)

        # 高斯模糊去噪
        blurred = cv2.GaussianBlur(bg_gray, (5, 5), 0)

        # Canny 边缘检测 - 调整阈值
        edges = cv2.Canny(blurred, 30, 100)

        # 膨胀操作，连接断开的边缘
        kernel = np.ones((5, 5), np.uint8)
        dilated = cv2.dilate(edges, kernel, iterations=3)

        # 查找轮廓
        contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # 获取模板尺寸作为参考
        slider_h, slider_w = slider.shape[:2]
        height, width = background.shape[:2]

        print(f"边缘检测: 背景图 {width}x{height}, 模板参考尺寸 {slider_w}x{slider_h}")
        print(f"边缘检测: 找到 {len(contours)} 个轮廓")

        candidates = []

        for i, contour in enumerate(contours):
            x, y, w, h = cv2.boundingRect(contour)
            area = cv2.contourArea(contour)
            aspect_ratio = w / h if h > 0 else 0

            # 计算尺寸比例
            w_ratio = w / slider_w if slider_w > 0 else 0
            h_ratio = h / slider_h if slider_h > 0 else 0

            # 打印所有轮廓信息（调试）
            if area > 100:
                print(f"  轮廓 {i}: x={x}, y={y}, w={w}, h={h}, area={area:.0f}, w_ratio={w_ratio:.2f}, h_ratio={h_ratio:.2f}")

            # 放宽过滤条件
            if (0.3 < w_ratio < 3.0 and  # 宽度范围放宽
                0.3 < h_ratio < 3.0 and  # 高度范围放宽
                x > width * 0.05 and  # 不在最左边（放宽）
                x < width * 0.95 and  # 不在最右边（放宽）
                area > 200 and  # 面积阈值降低
                0.3 < aspect_ratio < 3.0):  # 宽高比放宽
                candidates.append((x, area, w, h))

        if candidates:
            # 选择面积最大的作为缺口
            candidates.sort(key=lambda c: c[1], reverse=True)
            print(f"边缘检测找到 {len(candidates)} 个候选，选择: x={candidates[0][0]}, w={candidates[0][2]}, h={candidates[0][3]}")
            return candidates[0][0]

        print("边缘检测未找到合适的缺口")
        return 0

    def _find_gap_by_template(self, background: np.ndarray, slider: np.ndarray) -> int:
        """
        通过模板匹配找到缺口位置
        """
        # 检查是否有透明通道
        has_alpha = slider.shape[2] == 4 if len(slider.shape) == 3 else False

        print(f"模板匹配: 背景图形状 {background.shape}, 模板形状 {slider.shape}, 有透明通道: {has_alpha}")

        # 转换为灰度图
        if len(background.shape) == 3 and background.shape[2] == 4:
            bg_gray = cv2.cvtColor(background, cv2.COLOR_BGRA2GRAY)
        else:
            bg_gray = cv2.cvtColor(background, cv2.COLOR_BGR2GRAY)

        if has_alpha:
            slider_gray = cv2.cvtColor(slider, cv2.COLOR_BGRA2GRAY)
            # 提取透明通道作为掩码
            slider_alpha = slider[:, :, 3]
            # 创建掩码：透明区域为0，非透明区域为1
            mask = (slider_alpha > 10).astype(np.uint8)
        else:
            slider_gray = cv2.cvtColor(slider, cv2.COLOR_BGR2GRAY)
            mask = None

        # 检查尺寸
        bg_h, bg_w = bg_gray.shape
        slider_h, slider_w = slider_gray.shape

        print(f"模板匹配: 背景图尺寸 {bg_w}x{bg_h}, 模板尺寸 {slider_w}x{slider_h}")

        if slider_w > bg_w or slider_h > bg_h:
            print(f"模板尺寸大于背景图，跳过模板匹配")
            return 0

        # 使用模板匹配
        if mask is not None:
            # 使用掩码进行模板匹配（忽略透明区域）
            result = cv2.matchTemplate(bg_gray, slider_gray, cv2.TM_CCORR_NORMED, mask=mask)
        else:
            result = cv2.matchTemplate(bg_gray, slider_gray, cv2.TM_CCOEFF_NORMED)

        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

        print(f"模板匹配结果: 匹配度={max_val:.4f}, 位置=({max_loc[0]}, {max_loc[1]})")

        return max_loc[0]

    def generate_track(self, distance: int) -> List[int]:
        """
        生成模拟人类拖动的轨迹
        使用更合理的物理模型，确保轨迹能够正确移动
        """
        if distance <= 0:
            return []

        track = []
        current = 0

        # 使用更简单直接的轨迹生成方式
        # 将距离分成多个小段，模拟人类的加速-匀速-减速过程

        # 加速阶段：前 1/3 距离
        # 匀速阶段：中间 1/3 距离
        # 减速阶段：后 1/3 距离

        accel_dist = distance / 3
        const_dist = distance / 3
        decel_dist = distance / 3

        # 加速阶段：步长逐渐增大
        step = 1
        while current < accel_dist:
            move = min(step, accel_dist - current)
            track.append(int(move))
            current += move
            step += random.uniform(0.5, 1.5)

        # 匀速阶段：固定步长
        avg_step = 3
        while current < accel_dist + const_dist:
            move = min(avg_step + random.uniform(-0.5, 0.5),
                      accel_dist + const_dist - current)
            if move > 0:
                track.append(int(move))
                current += move

        # 减速阶段：步长逐渐减小
        step = 3
        while current < distance:
            move = min(step, distance - current)
            track.append(int(move))
            current += move
            step = max(1, step - random.uniform(0.3, 0.8))

        # 打印轨迹信息用于调试
        total = sum(track)
        print(f"轨迹生成: 目标距离={distance}px, 轨迹步数={len(track)}, 总移动={total}px")

        return track
    
    async def drag_slider(self, distance: int):
        """
        执行拖动操作
        """
        # 获取滑块元素
        slider = await self.frame.query_selector(".tc-fg-item.tc-slider-normal")
        if not slider:
            raise Exception("未找到滑块元素")
        
        # 获取滑块位置
        box = await slider.bounding_box()
        if box is None:
            raise Exception("无法获取滑块边界框")
        
        mouse = self._get_mouse()
        
        # 鼠标移动到滑块中心
        await mouse.move(box['x'] + box['width'] / 2, 
                        box['y'] + box['height'] / 2)
        
        # 按下鼠标
        await mouse.down()
        
        # 生成拖动轨迹
        track = self.generate_track(distance)
        
        # 执行拖动
        current_x = box['x'] + box['width'] / 2
        for move in track:
            current_x += move
            await mouse.move(current_x, box['y'] + box['height'] / 2)
            await asyncio.sleep(random.uniform(0.005, 0.02))
        
        # 释放鼠标
        await mouse.up()
        
        # 等待验证结果
        await asyncio.sleep(1)
    
    async def is_verified(self) -> bool:
        """
        检查是否验证成功
        使用多种方式检测验证结果
        """
        # 等待验证结果返回
        await asyncio.sleep(0.5)

        # 方法一：检查滑块是否消失或隐藏
        try:
            slider = await self.frame.query_selector(".tc-fg-item.tc-slider-normal")
            if slider:
                is_visible = await slider.is_visible()
                if not is_visible:
                    print("验证成功检测: 滑块已隐藏")
                    return True
            else:
                print("验证成功检测: 滑块元素已消失")
                return True
        except Exception as e:
            print(f"检查滑块状态出错: {e}")

        # 方法二：检查验证成功提示
        try:
            # 检查是否有成功提示元素
            success_indicators = [
                ".tc-success",  # 成功提示
                ".tc-verify-success",  # 验证成功
                "[class*='success']",  # 包含 success 的类名
            ]
            for selector in success_indicators:
                try:
                    element = await self.frame.query_selector(selector)
                    if element:
                        is_visible = await element.is_visible()
                        if is_visible:
                            print(f"验证成功检测: 发现成功提示元素 {selector}")
                            return True
                except:
                    pass
        except Exception as e:
            print(f"检查成功提示出错: {e}")

        # 方法三：检查验证码容器是否消失
        try:
            # 检查整个验证码容器
            captcha_container = await self.frame.query_selector("#tcOperation")
            if captcha_container:
                is_visible = await captcha_container.is_visible()
                if not is_visible:
                    print("验证成功检测: 验证码容器已隐藏")
                    return True
            else:
                print("验证成功检测: 验证码容器已消失")
                return True
        except Exception as e:
            print(f"检查验证码容器出错: {e}")

        # 方法四：检查是否有错误提示（如果出现错误提示，说明验证失败）
        try:
            error_indicators = [
                ".tc-error",
                ".tc-verify-fail",
                "[class*='error']",
            ]
            for selector in error_indicators:
                try:
                    element = await self.frame.query_selector(selector)
                    if element:
                        is_visible = await element.is_visible()
                        if is_visible:
                            print(f"验证失败检测: 发现错误提示元素 {selector}")
                            return False
                except:
                    pass
        except:
            pass

        print("验证结果检测: 未确定状态，默认失败")
        return False
    
    async def solve(self, max_retries: int = 3, debug: bool = True) -> bool:
        """
        执行滑块验证
        """
        for attempt in range(max_retries):
            try:
                print(f"\n========== 第 {attempt + 1} 次尝试 ==========")

                # 等待验证码加载
                await self.frame.wait_for_selector(".tc-fg-item.tc-slider-normal",
                                                 timeout=5000)
                await asyncio.sleep(0.5)

                # 获取背景图（原始图片）
                bg_img = await self.get_background_image(save_debug=debug)

                # 获取缺口模板图（从大图裁剪）和位置信息
                slider_img, pos_info = await self.get_slider_image(save_debug=debug)

                # 计算缺口在背景图中的位置
                gap_x = self.find_gap_position(bg_img, slider_img)
                print(f"缺口在背景图中的位置: {gap_x}px")

                # 计算滑动距离
                # gap_x 是缺口在原始背景图中的 X 坐标
                # pos_info['left'] 是待滑动块在页面中的初始位置
                # 需要计算：滑动距离 = 缺口位置 - 待滑动块初始位置

                # 但还需要考虑背景图在页面中的位置和原始图片的缩放比例
                bg_element = await self.frame.query_selector("#slideBg")
                if bg_element:
                    bg_box = await bg_element.bounding_box()
                    if bg_box:
                        # 背景图在页面中的显示尺寸
                        display_w = bg_box['width']
                        # 原始背景图的尺寸
                        original_w = bg_img.shape[1]

                        # 缩放比例
                        scale = original_w / display_w
                        print(f"背景图显示尺寸: {display_w}px, 原始尺寸: {original_w}px, 缩放比例: {scale:.4f}")

                        # 将缺口位置从原始图片坐标转换为页面坐标
                        gap_x_display = gap_x / scale

                        # 待滑动块的初始位置（页面坐标）
                        template_initial_x = pos_info['left']

                        # 滑动距离 = 缺口位置 - 待滑动块初始位置
                        distance = gap_x_display - template_initial_x

                        print(f"待滑动块初始位置: {template_initial_x}px")
                        print(f"缺口页面位置: {gap_x_display:.2f}px")
                        print(f"需要滑动距离: {distance:.2f}px")
                    else:
                        distance = gap_x
                else:
                    distance = gap_x

                # 执行拖动
                await self.drag_slider(max(0, int(distance)))
                
                # 检查验证结果
                if await self.is_verified():
                    print("验证成功！")
                    return True
                else:
                    print("验证失败，准备重试...")
                    # 刷新验证码
                    refresh_btn = await self.frame.query_selector(".tc-refresh")
                    if refresh_btn:
                        await refresh_btn.click()
                        await asyncio.sleep(1)
                        
            except Exception as e:
                print(f"验证过程中出现错误: {e}")
                continue
        
        return False


async def douban_login_with_captcha(username: str, password: str):
    """
    豆瓣带滑块验证的登录流程
    """
    async with async_playwright() as p:
        # 启动浏览器（使用无头模式可能会被检测，建议使用有头模式）
        browser = await p.chromium.launch(
            headless=False,  # 使用有头模式更容易通过验证
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-web-security',
            ]
        )
        
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 720},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        
        page = await context.new_page()
        frame_manager = FrameManager(page)
        
        try:
            # 访问豆瓣登录页面 - 直接访问登录弹窗页面
            login_url = "https://accounts.douban.com/passport/login_popup?login_source=anony"
            print(f"正在访问豆瓣登录页面: {login_url}")
            await page.goto(login_url, timeout=30000)
            await page.wait_for_load_state("networkidle")
            
            # 调试：打印所有 frame
            frames = await frame_manager.get_all_frames()
            print(f"找到 {len(frames)} 个框架:")
            for i, frame in enumerate(frames):
                print(f"  [{i}] {frame.url}")
            
      # 1. 点击密码登录控件（否则默认是手机激活码）
            print("点击密码登录控件...")
            try:
                password_login_tab = await page.wait_for_selector("#app > div > div.account-body-tabs > ul.tab-start > li.account-tab-account", timeout=10000)
                if password_login_tab:
                    await password_login_tab.click()
            except:
                # 尝试使用xpath
                try:
                    password_login_tab = await page.wait_for_selector("xpath=//*[@id=\"app\"]/div/div[1]/ul[1]/li[2]", timeout=5000)
                    if password_login_tab:
                        await password_login_tab.click()
                except:
                    print("未找到密码登录控件，尝试直接输入")
            
            # 2. 输入账号
            print(f"输入账号: {username}")
            try:
                username_input = await page.wait_for_selector("#app > div > div.account-tabcon-start > div.account-form > div:nth-child(3) > div > input", timeout=5000)
                if username_input:
                    await username_input.fill(username)
            except:
                # 尝试使用xpath
                try:
                    username_input = await page.wait_for_selector("xpath=//*[@id=\"app\"]/div/div[2]/div[1]/div[3]/div/input", timeout=5000)
                    if username_input:
                        await username_input.fill(username)
                except:
                    print("未找到账号输入框")
                    return False
            
            # 3. 输入密码
            print("输入密码...")
            try:
                password_input = await page.wait_for_selector("#app > div > div.account-tabcon-start > div.account-form > div:nth-child(4) > div > input", timeout=5000)
                if password_input:
                    await password_input.fill(password)
            except:
                # 尝试使用xpath
                try:
                    password_input = await page.wait_for_selector("xpath=//*[@id=\"app\"]/div/div[2]/div[1]/div[4]/div/input", timeout=5000)
                    if password_input:
                        await password_input.fill(password)
                except:
                    print("未找到密码输入框")
                    return False
            
            # 4. 点击登录控件
            print("点击登录按钮...")
            try:
                login_button = await page.wait_for_selector("#app > div > div.account-tabcon-start > div.account-form > div.account-form-field-submit > a", timeout=5000)
                if login_button:
                    await login_button.click()
            except:
                # 尝试使用xpath
                try:
                    login_button = await page.wait_for_selector("xpath=//*[@id=\"app\"]/div/div[2]/div[1]/div[5]/a", timeout=5000)
                    if login_button:
                        await login_button.click()
                except:
                    print("未找到登录按钮")
                    return False
            
            # 等待验证码出现
            print("等待滑块验证码出现...")
            try:
                # 点击登录后，需要等待 iframe 加载
                # 先等待一段时间让 iframe 有机会被创建
                await asyncio.sleep(1)
                
                # 使用 FrameManager 查找验证码 frame
                captcha_frame = None
                
                # 多次尝试查找验证码 frame（因为 iframe 可能需要时间加载）
                for retry in range(5):
                    print(f"第 {retry + 1} 次尝试查找验证码 frame...")
                    
                    # 刷新 frame 列表
                    frames = await frame_manager.get_all_frames()
                    print(f"  当前共有 {len(frames)} 个 frame")
                    for i, frame in enumerate(frames):
                        print(f"    [{i}] {frame.url}")
                    
                    # 先检查主页面是否有验证码
                    captcha_element = await page.query_selector(".tc-fg-item")
                    if captcha_element:
                        print("检测到滑块验证码（主页面）")
                        captcha = TencentSliderCaptcha(page)
                        break
                    
                    # 使用 FrameManager 查找验证码 iframe
                    try:
                        captcha_frame = await frame_manager.find_frame_by_url("captcha")
                        print(f"  找到验证码 frame: {captcha_frame.url}")
                        break
                    except:
                        try:
                            captcha_frame = await frame_manager.find_frame_by_url("turing")
                            print(f"  找到验证码 frame: {captcha_frame.url}")
                            break
                        except:
                            pass
                    
                    # 等待后重试
                    await asyncio.sleep(1)
                
                # 初始化 captcha 变量，确保在所有路径下都有定义
                captcha = None
                
                if captcha_frame:
                    # 等待 iframe 中的验证码加载
                    await frame_manager.wait_for_frame_load(captcha_frame)
                    await captcha_frame.wait_for_selector(".tc-fg-item", timeout=10000)
                    print("检测到滑块验证码（iframe）")
                    captcha = TencentSliderCaptcha(captcha_frame)
                
                # 如果没有找到 iframe 验证码，检查主页面是否有验证码
                if captcha is None:
                    # 等待主页面验证码出现
                    try:
                        await page.wait_for_selector(".tc-fg-item", timeout=10000)
                        print("检测到滑块验证码（主页面）")
                        captcha = TencentSliderCaptcha(page)
                    except:
                        pass
                
                if captcha is None:
                    raise Exception("未找到任何验证码元素")
                
                success = await captcha.solve()
                
                if success:
                    print("验证码验证成功，继续登录...")
                    # 等待登录完成
                    await page.wait_for_load_state("networkidle", timeout=10000)
                    print("登录完成！")
                    
                    # 检查是否登录成功
                    await asyncio.sleep(2)
                    current_url = page.url
                    if "douban.com" in current_url and "login" not in current_url:
                        print(f"登录成功！当前页面: {current_url}")
                        return True
                    else:
                        print(f"可能登录失败，当前页面: {current_url}")
                        return False
                else:
                    print("验证码验证失败")
                    return False
                    
            except Exception as e:
                print(f"等待验证码时出错: {e}")
                # 可能不需要验证码，直接登录成功
                await asyncio.sleep(2)
                current_url = page.url
                if "douban.com" in current_url and "login" not in current_url:
                    print(f"直接登录成功！当前页面: {current_url}")
                    return True
                else:
                    print(f"登录失败，当前页面: {current_url}")
                    return False
                
        except Exception as e:
            print(f"登录过程出错: {e}")
            return False
            
        finally:
            # 保持浏览器打开以便查看结果
            input("按回车键关闭浏览器...")
            await browser.close()


async def main():
    """
    主函数
    """
    from dotenv import load_dotenv
    
    # 加载环境变量
    load_dotenv()
    
    # 从环境变量读取豆瓣用户名和密码
    username = os.getenv("DOUBAN_USERNAME", "your_douban_username")
    password = os.getenv("DOUBAN_PASSWORD", "your_douban_password")
    
    if username == "your_douban_username" or password == "your_douban_password":
        print("警告：请先在.env文件中设置DOUBAN_USERNAME和DOUBAN_PASSWORD")
        print("当前使用默认值，登录可能会失败")
    
    print(f"使用账号: {username}")
    
    # 执行豆瓣登录
    await douban_login_with_captcha(username, password)


if __name__ == "__main__":
    asyncio.run(main())