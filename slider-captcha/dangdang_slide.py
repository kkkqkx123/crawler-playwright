import random
import asyncio
import os
import cv2
import numpy as np
from PIL import Image
from playwright.async_api import async_playwright, Page, Frame
import io
import httpx


class DangdangSliderCaptcha:
    """当当滑块验证码处理类"""
    
    def __init__(self, page: Page | Frame):
        """初始化，支持 Page 或 Frame"""
        self.page = page
        self.save_dir = "slider-captcha/img"
        os.makedirs(self.save_dir, exist_ok=True)
    
    async def download_images(self) -> bool:
        """下载验证码图片"""
        try:
            # 获取主图和滑块图元素
            main_image = await self.page.query_selector("xpath://img[@id='bgImg']")
            slot_image = await self.page.query_selector("xpath://img[@id='simg']")

            if not main_image or not slot_image:
                print("未找到验证码图片元素")
                return False
            
            print("找到验证码图片元素")
            
            # 获取图片的src属性
            main_src = await main_image.get_attribute("src")
            slot_src = await slot_image.get_attribute("src")
            
            if not main_src or not slot_src:
                print("无法获取图片src属性")
                return False
            
            # 下载图片数据
            async with httpx.AsyncClient(timeout=10) as client:
                main_img_data = (await client.get(main_src)).content
                slot_img_data = (await client.get(slot_src)).content
            
            # 保存图片
            main_path = os.path.join(self.save_dir, "main_img.png")
            slot_path = os.path.join(self.save_dir, "slot_img.png")
            
            with open(main_path, "wb") as f:
                f.write(main_img_data)
            
            with open(slot_path, "wb") as f:
                f.write(slot_img_data)
            
            print("验证码图片下载完成")
            return True
            
        except Exception as e:
            print(f"下载图片失败: {e}")
            return False
    
    def recognize_captcha(self) -> int | None:
        """识别滑块缺口位置 (边缘检测 + 多尺度匹配 + 高斯模糊)"""
        try:
            bg_path = os.path.join(self.save_dir, "main_img.png")
            slider_path = os.path.join(self.save_dir, "slot_img.png")
            
            bg = cv2.imread(bg_path)
            tp = cv2.imread(slider_path)
            
            if bg is None or tp is None:
                print("图片读取失败")
                return None
            
            # 灰度化
            bg_gray = cv2.cvtColor(bg, cv2.COLOR_BGR2GRAY)
            tp_gray = cv2.cvtColor(tp, cv2.COLOR_BGR2GRAY)
            
            # 高斯模糊减少干扰
            bg_blur = cv2.GaussianBlur(bg_gray, (3, 3), 0)
            tp_blur = cv2.GaussianBlur(tp_gray, (3, 3), 0)
            
            # 边缘检测
            bg_edge = cv2.Canny(bg_blur, 100, 200)
            tp_edge = cv2.Canny(tp_blur, 100, 200)
            
            # 多尺度模板匹配
            scales = [0.8, 1.0, 1.2]
            best_score = -1
            best_loc = (0, 0)
            
            for scale in scales:
                tp_resized = cv2.resize(tp_edge, None, fx=scale, fy=scale)
                if tp_resized.shape[0] > bg_edge.shape[0] or tp_resized.shape[1] > bg_edge.shape[1]:
                    continue
                res = cv2.matchTemplate(bg_edge, tp_resized, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, max_loc = cv2.minMaxLoc(res)
                if max_val > best_score:
                    best_score = max_val
                    best_loc = max_loc
            
            distance = best_loc[0]
            adjusted_distance = int(distance * 350 / 408)  # 根据实际比例调整
            
            print(f"最佳匹配位置: {distance} -> {adjusted_distance}, 分数: {best_score:.3f}")
            
            # 调试：画出匹配位置并保存
            if best_score > 0.2:
                debug_img = bg_edge.copy()
                h, w = tp_edge.shape[:2]
                cv2.rectangle(debug_img, best_loc, (best_loc[0] + w, best_loc[1] + h), (255, 0, 0), 2)
                debug_path = os.path.join(self.save_dir, "debug_match.png")
                cv2.imwrite(debug_path, debug_img)
                print(f"调试图片保存到 {debug_path}")
            
            return adjusted_distance
            
        except Exception as e:
            print(f"识别失败: {e}")
            return None
    
    def generate_track(self, distance: int) -> list[int]:
        """生成更像真人的滑块轨迹：贝塞尔曲线模拟 + 随机停顿 + 加速减速"""

        # 生成贝塞尔曲线点
        def bezier_curve(p0, p1, p2, t):
            return (1-t)**2 * p0 + 2*(1-t)*t * p1 + t**2 * p2

        # 控制点
        p0 = 0
        p2 = distance
        p1 = distance * random.uniform(0.3, 0.7)  # 随机中间点

        track = []
        steps = random.randint(25, 35)  # 更多步骤
        for i in range(steps + 1):
            t = i / steps
            # 添加非线性时间分布，模拟加速减速
            t = t ** random.uniform(0.8, 1.2)  # 使轨迹更不均匀
            pos = bezier_curve(p0, p1, p2, t)
            track.append(int(pos))

            # 随机停顿
            if random.random() < 0.2:
                track.append(int(pos))  # 重复位置

        # 确保最后到达
        if track[-1] != distance:
            track[-1] = distance

        return track
    
    async def drag_slider(self, distance: int):
        """执行拖动操作"""
        # 获取滑块元素
        slider = await self.page.query_selector("xpath://div[@id='sliderBtn']")
        if not slider:
            raise Exception("未找到滑块元素")

        # 获取滑块位置
        box = await slider.bounding_box()
        if box is None:
            raise Exception("无法获取滑块边界框")

        # 获取鼠标对象（处理 Page 或 Frame 类型）
        page_obj = self.page if isinstance(self.page, Page) else self.page.page
        mouse = page_obj.mouse

        # 鼠标移到滑块上，模拟真人犹豫
        await mouse.move(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
        await asyncio.sleep(random.uniform(0.8, 2.0))  # 更长的停顿

        # 随机移动鼠标
        await mouse.move(box['x'] + box['width'] / 2 + random.randint(-5, 5),
                        box['y'] + box['height'] / 2 + random.randint(-5, 5))
        await asyncio.sleep(random.uniform(0.3, 0.8))

        # 按住滑块
        await mouse.down()
        await asyncio.sleep(random.uniform(0.3, 1.0))  # 更长的按住时间

        # 生成拖动轨迹
        tracks = self.generate_track(distance)

        # 根据轨迹拖动，添加更大随机y偏移和更慢duration
        prev_pos = 0
        current_x = box['x'] + box['width'] / 2
        current_y = box['y'] + box['height'] / 2

        for i, pos in enumerate(tracks):
            relative_move = pos - prev_pos
            y_offset = random.randint(-8, 8)  # 更大y偏移

            # 动态duration：开始慢，中间快，结束慢
            if i < len(tracks) // 4:
                duration = random.uniform(0.05, 0.12)  # 开始慢
            elif i > len(tracks) * 3 // 4:
                duration = random.uniform(0.05, 0.12)  # 结束慢
            else:
                duration = random.uniform(0.02, 0.06)  # 中间快

            current_x += relative_move
            await mouse.move(current_x, current_y + y_offset)
            prev_pos = pos

            # 随机小停顿
            if random.random() < 0.15:
                await asyncio.sleep(random.uniform(0.02, 0.08))

        # 释放鼠标
        await mouse.up()
        await asyncio.sleep(random.uniform(0.2, 0.5))  # 随机释放后停顿

        # 释放后随机移动鼠标，模拟真人行为
        for _ in range(random.randint(2, 5)):
            await mouse.move(current_x + random.randint(-20, 20),
                           current_y + random.randint(-20, 20))
            await asyncio.sleep(random.uniform(0.1, 0.3))

        await asyncio.sleep(random.uniform(0.8, 1.5))
    
    async def is_verified(self) -> bool:
        """检查是否验证成功"""
        await asyncio.sleep(3)

        # 检查页面内容
        try:
            page_content = await self.page.content()
            if "用户名或密码输入错误，请核对后重新输入" in page_content:
                print("验证成功检测: 发现成功提示")
                return True
        except:
            pass

        # 检查URL变化（处理 Page 或 Frame 类型）
        page_obj = self.page if isinstance(self.page, Page) else self.page.page
        current_url = page_obj.url
        if 'login' not in current_url:
            print("验证成功检测: URL已变化")
            return True
        
        print("验证结果检测: 未确定状态，默认失败")
        return False
    
    async def solve(self, max_retries: int = 1) -> bool:
        """执行滑块验证"""
        for attempt in range(max_retries):
            try:
                print(f"\n========== 第 {attempt + 1} 次尝试 ==========")
                
                # 下载验证码图片
                if not await self.download_images():
                    await asyncio.sleep(1)
                    continue
                
                # 识别缺口位置
                distance = self.recognize_captcha()
                if distance is None:
                    print("无法识别缺口位置，使用随机距离")
                    distance = random.randint(100, 200)
                else:
                    # 添加随机偏移 ±5px
                    distance += random.randint(-5, 5)
                    distance = max(0, distance)
                
                # 执行拖动
                print(f"开始拖动滑块，距离: {distance}px")
                await self.drag_slider(distance)
                
                # 检查验证结果
                if await self.is_verified():
                    print("验证成功！")
                    return True
                else:
                    print("验证失败，准备重试...")
                    await asyncio.sleep(2)
                    
            except Exception as e:
                print(f"验证过程中出现错误: {e}")
                continue
        
        return False


async def dangdang_login_with_captcha(username: str, password: str):
    """
    当当带滑块验证的登录流程
    """
    async with async_playwright() as p:
        # 启动浏览器
        browser = await p.chromium.launch(
            headless=False,
            args=[
                '--disable-infobars',
                '--disable-gpu',
                '--disable-blink-features=AutomationControlled',
                '--window-size=1920,1080',
                '--disable-web-security',
                '--allow-running-insecure-content',
                '--disable-extensions',
                '--no-first-run',
                '--disable-default-apps',
                '--disable-sync',
                '--no-sandbox',
            ]
        )
        
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        
        page = await context.new_page()
        
        try:
            # 访问当当登录页面
            login_url = 'https://login.dangdang.com'
            print(f"正在访问当当登录页面: {login_url}")
            await page.goto(login_url, timeout=30000)
            await page.wait_for_load_state("networkidle")
            
            # 注入反检测脚本
            await page.evaluate('''
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
                window.navigator.chrome = { runtime: {} };
                delete navigator.__proto__.webdriver;
                
                // 模拟插件
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5]
                });
                
                // 模拟语言
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['zh-CN', 'zh', 'en']
                });
                
                // 覆盖webgl指纹
                const getParameter = WebGLRenderingContext.prototype.getParameter;
                WebGLRenderingContext.prototype.getParameter = function(parameter) {
                    if (parameter === 37445) return 'Intel Inc.';
                    if (parameter === 37446) return 'Intel(R) Iris(TM) Graphics 6100';
                    return getParameter.call(this, parameter);
                };
            ''')
            
            # 1. 输入用户名（模拟真人输入）
            print(f"输入用户名: {username}")
            username_field = await page.wait_for_selector('xpath://input[@type="text" and @autofocus="autofocus"]', timeout=10000)
            if username_field:
                await username_field.click()
                await asyncio.sleep(random.uniform(0.5, 1.0))
                for char in username:
                    await username_field.type(char, delay=random.uniform(100, 300))
            
            await asyncio.sleep(random.uniform(0.5, 1.5))
            
            # 2. 输入密码（模拟真人输入）
            print("输入密码...")
            password_field = await page.wait_for_selector('xpath://input[@type="password" and @autofocus="autofocus"]', timeout=10000)
            if password_field:
                await password_field.click()
                await asyncio.sleep(random.uniform(0.5, 1.0))
                for char in password:
                    await password_field.type(char, delay=random.uniform(100, 300))
            
            await asyncio.sleep(random.uniform(0.5, 1.5))
            
            # 3. 点击同意协议
            print("点击同意协议...")
            try:
                agreement = await page.query_selector('xpath://input[@type="radio" and @title="同意用户协议、隐私政策选择框"]')
                if agreement:
                    await agreement.click()
            except:
                print("未找到协议选项，可能已默认同意")
            
            # 4. 点击登录
            print("点击登录按钮...")
            login_button = await page.wait_for_selector('xpath://a[@class="btn"]', timeout=10000)
            if login_button:
                await login_button.click()
                await asyncio.sleep(3)
            
            # 5. 检查是否出现滑块验证
            print("检查是否出现滑块验证...")
            slider_element = await page.query_selector("xpath://img[@id='bgImg']")
            if not slider_element:
                print("没有检测到滑块，可能登录成功或失败")
                # 检查登录结果
                await asyncio.sleep(2)
                page_content = await page.content()
                if "用户名或密码输入错误，请核对后重新输入" in page_content:
                    print("登录成功！")
                    return True
                else:
                    print("登录失败")
                    return False
            
            print("检测到滑块验证，开始处理...")
            
            # 6. 创建验证码处理器并执行验证
            captcha = DangdangSliderCaptcha(page)
            success = await captcha.solve(max_retries=1)
            
            if success:
                print("验证码验证成功，继续登录...")
                # 等待登录完成
                await asyncio.sleep(3)
                page_content = await page.content()
                if "用户名或密码输入错误，请核对后重新输入" in page_content:
                    print("登录成功！")
                    return True
                else:
                    print("登录失败")
                    return False
            else:
                print("验证码验证失败")
                return False
                
        except Exception as e:
            print(f"登录过程出错: {e}")
            return False
            
        finally:
            # 保持浏览器打开以便查看结果
            print("按回车键关闭浏览器...")
            input()
            await browser.close()


async def main():
    """
    主函数
    """
    from dotenv import load_dotenv
    
    # 加载环境变量
    load_dotenv()
    
    # 从环境变量读取当当用户名和密码
    username = os.getenv("DANGDANG_USERNAME", "your_dangdang_username")
    password = os.getenv("DANGDANG_PASSWORD", "your_dangdang_password")
    
    if username == "your_dangdang_username" or password == "your_dangdang_password":
        print("警告：请先在.env文件中设置DANGDANG_USERNAME和DANGDANG_PASSWORD")
        print("当前使用默认值，登录可能会失败")
    
    print(f"使用账号: {username}")
    
    # 执行当当登录
    await dangdang_login_with_captcha(username, password)


if __name__ == "__main__":
    asyncio.run(main())
