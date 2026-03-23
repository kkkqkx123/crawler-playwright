import asyncio
import random
import time
import os
from typing import Tuple, List
import cv2
import numpy as np
from PIL import Image
from playwright.async_api import async_playwright
import io


class TencentSliderCaptcha:
    def __init__(self, page):
        self.page = page
        
    async def get_slider_position(self) -> Tuple[int, int, int, int]:
        """获取滑块元素的位置和大小"""
        slider = await self.page.query_selector(".tc-fg-item.tc-slider-normal")
        if not slider:
            raise Exception("未找到滑块元素")
        
        box = await slider.bounding_box()
        return (box['x'], box['y'], box['width'], box['height'])
    
    async def get_background_image(self) -> np.ndarray:
        """获取背景图并转换为OpenCV格式"""
        bg_element = await self.page.query_selector("#slideBg")
        if not bg_element:
            raise Exception("未找到背景图元素")
        
        # 获取背景图的截图
        screenshot = await bg_element.screenshot()
        image = Image.open(io.BytesIO(screenshot))
        return cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
    
    async def get_slider_image(self) -> np.ndarray:
        """获取滑块图并转换为OpenCV格式"""
        slider = await self.page.query_selector(".tc-fg-item")
        if not slider:
            raise Exception("未找到滑块元素")
        
        # 获取滑块的截图
        screenshot = await slider.screenshot()
        image = Image.open(io.BytesIO(screenshot))
        return cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
    
    def find_gap_position(self, background: np.ndarray, slider: np.ndarray) -> int:
        """
        通过模板匹配找到缺口位置
        返回需要滑动的距离（像素）
        """
        # 转换为灰度图
        bg_gray = cv2.cvtColor(background, cv2.COLOR_BGR2GRAY)
        slider_gray = cv2.cvtColor(slider, cv2.COLOR_BGR2GRAY)
        
        # 使用模板匹配
        result = cv2.matchTemplate(bg_gray, slider_gray, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
        
        # 返回匹配位置的X坐标
        return max_loc[0]
    
    def generate_track(self, distance: int) -> List[int]:
        """
        生成模拟人类拖动的轨迹
        包含加速、减速和微小抖动
        """
        track = []
        current = 0
        # 加速阶段占总距离的70%
        mid = distance * 0.7
        # 时间间隔（秒）
        t = 0.1
        # 初始速度
        v = 0
        
        while current < distance:
            if current < mid:
                # 加速阶段
                a = random.uniform(1.5, 3.0)
            else:
                # 减速阶段
                a = -random.uniform(1.5, 3.0)
            
            # 速度变化
            v0 = v
            v = v0 + a * t
            
            # 位移变化
            move = v0 * t + 0.5 * a * t * t
            
            # 确保不超过目标距离
            if current + move > distance:
                move = distance - current
            
            current += move
            track.append(round(move))
            
            # 添加随机暂停时间
            time.sleep(random.uniform(0.005, 0.02))
        
        return track
    
    async def drag_slider(self, distance: int):
        """
        执行拖动操作
        """
        # 获取滑块元素
        slider = await self.page.query_selector(".tc-fg-item.tc-slider-normal")
        if not slider:
            raise Exception("未找到滑块元素")
        
        # 获取滑块位置
        box = await slider.bounding_box()
        
        # 鼠标移动到滑块中心
        await self.page.mouse.move(box['x'] + box['width'] / 2, 
                                   box['y'] + box['height'] / 2)
        
        # 按下鼠标
        await self.page.mouse.down()
        
        # 生成拖动轨迹
        track = self.generate_track(distance)
        
        # 执行拖动
        current_x = box['x'] + box['width'] / 2
        for move in track:
            current_x += move
            await self.page.mouse.move(current_x, box['y'] + box['height'] / 2)
            await asyncio.sleep(random.uniform(0.005, 0.02))
        
        # 释放鼠标
        await self.page.mouse.up()
        
        # 等待验证结果
        await asyncio.sleep(1)
    
    async def is_verified(self) -> bool:
        """
        检查是否验证成功
        """
        # 检查滑块是否消失或隐藏
        slider = await self.page.query_selector(".tc-fg-item.tc-slider-normal")
        if not slider:
            return True
        
        # 检查是否可见
        is_visible = await slider.is_visible()
        return not is_visible
    
    async def solve(self, max_retries: int = 3) -> bool:
        """
        执行滑块验证
        """
        for attempt in range(max_retries):
            try:
                print(f"第 {attempt + 1} 次尝试...")
                
                # 等待验证码加载
                await self.page.wait_for_selector(".tc-fg-item.tc-slider-normal", 
                                                 timeout=5000)
                await asyncio.sleep(0.5)
                
                # 获取背景图和滑块图
                bg_img = await self.get_background_image()
                slider_img = await self.get_slider_image()
                
                # 计算缺口距离
                distance = self.find_gap_position(bg_img, slider_img)
                print(f"检测到缺口距离: {distance}px")
                
                # 添加偏移修正（因为滑块本身有一定宽度）
                slider_box = await self.get_slider_position()
                distance = distance - slider_box[2] / 2
                
                # 执行拖动
                await self.drag_slider(max(0, int(distance)))
                
                # 检查验证结果
                if await self.is_verified():
                    print("验证成功！")
                    return True
                else:
                    print("验证失败，准备重试...")
                    # 刷新验证码
                    refresh_btn = await self.page.query_selector(".tc-refresh")
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
        
        try:
            # 访问豆瓣登录页面
            login_url = "https://www.douban.com/"
            print(f"正在访问豆瓣: {login_url}")
            await page.goto(login_url, timeout=30000)
            await asyncio.sleep(2)
            
      # 1. 点击密码登录控件（否则默认是手机激活码）
            print("点击密码登录控件...")
            password_login_tab = await page.query_selector("#app > div > div.account-body-tabs > ul.tab-start > li.account-tab-account.on")
            if password_login_tab:
                await password_login_tab.click()
            else:
                # 尝试使用xpath
                password_login_tab = await page.query_selector("xpath=//*[@id=\"app\"]/div/div[1]/ul[1]/li[2]")
                if password_login_tab:
                    await password_login_tab.click()
                else:
                    print("未找到密码登录控件，尝试直接输入")
            
            await asyncio.sleep(1)
            
            # 2. 输入账号
            print(f"输入账号: {username}")
            username_input = await page.query_selector("#app > div > div.account-tabcon-start > div.account-form > div:nth-child(3) > div > input")
            if username_input:
                await username_input.fill(username)
            else:
                # 尝试使用xpath
                username_input = await page.query_selector("xpath=//*[@id=\"app\"]/div/div[2]/div[1]/div[3]/div/input")
                if username_input:
                    await username_input.fill(username)
                else:
                    print("未找到账号输入框")
                    return False
            
            await asyncio.sleep(0.5)
            
            # 3. 输入密码
            print("输入密码...")
            password_input = await page.query_selector("#app > div > div.account-tabcon-start > div.account-form > div:nth-child(4) > div > input")
            if password_input:
                await password_input.fill(password)
            else:
                # 尝试使用xpath
                password_input = await page.query_selector("xpath=//*[@id=\"app\"]/div/div[2]/div[1]/div[4]/div/input")
                if password_input:
                    await password_input.fill(password)
                else:
                    print("未找到密码输入框")
                    return False
            
            await asyncio.sleep(0.5)
            
            # 4. 点击登录控件
            print("点击登录按钮...")
            login_button = await page.query_selector("#app > div > div.account-tabcon-start > div.account-form > div.account-form-field-submit > a")
            if login_button:
                await login_button.click()
            else:
                # 尝试使用xpath
                login_button = await page.query_selector("xpath=//*[@id=\"app\"]/div/div[2]/div[1]/div[5]/a")
                if login_button:
                    await login_button.click()
                else:
                    print("未找到登录按钮")
                    return False
            
            # 等待验证码出现
            print("等待滑块验证码出现...")
            try:
                await page.wait_for_selector(".tc-fg-item", timeout=10000)
                print("检测到滑块验证码")
                
                # 创建验证码处理器并解决
                captcha = TencentSliderCaptcha(page)
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