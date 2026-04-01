import random
from DrissionPage import ChromiumPage, ChromiumOptions
import time
import base64
import cv2
import os

import requests

def download_img(page, save_dir="week_2/img"):
    """下载验证码图片"""
    try:  

        main_image = page.ele("xpath://img[@id='bgImg']", timeout=5)
        slot_image = page.ele("xpath://img[@id='simg']", timeout=5)
        print("找到验证码图片元素")
        
        main_src = main_image.attr("src")
        slot_src = slot_image.attr("src")
        
        main_img_data = requests.get(main_src).content
        slot_img_data = requests.get(slot_src).content
        
        main_path = os.path.join(str(save_dir), "main_img.png")
        slot_path = os.path.join(str(save_dir), "slot_img.png")
        
        with open(main_path, "wb") as f:
            f.write(main_img_data)
        
        with open(slot_path, "wb") as f:
            f.write(slot_img_data)
        
        
        print("验证码图片下载完成")
        return True
    except Exception as e:
        print(f"下载图片失败: {e}")
        return False 

def recognize_captcha(save_dir="week_2/img"):
    """识别滑块缺口位置 (进阶版：边缘检测 + 多尺度匹配 + 高斯模糊)"""
    try:
        bg_path = f"{save_dir}/main_img.png"
        slider_path = f"{save_dir}/slot_img.png"
        
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
        adjusted_distance = int(distance * 350 / 408) # 根据实际比例调整
        
        print(f"最佳匹配位置: {distance} -> {adjusted_distance}, 分数: {best_score:.3f}")
        
        # 调试：画出匹配位置并保存
        if best_score > 0.2:
            debug_img = bg_edge.copy()
            h, w = tp_edge.shape[:2]
            cv2.rectangle(debug_img, best_loc, (best_loc[0] + w, best_loc[1] + h), (255, 0, 0), 2)
            cv2.imwrite(f"{save_dir}/debug_match.png", debug_img)
            print(f"调试图片保存到 {save_dir}/debug_match.png")
        
        return adjusted_distance
    except Exception as e:
        print(f"识别失败: {e}")
        return None

def generate_track(distance):
   
    track = []
    current = 0
    
    # 匀速向前滑动
    while current < distance:
        # 每次移动 2-4 像素，非常平稳
        move = random.randint(2, 4)
        current += move
        track.append(current)
    
    # 最后精准到达目标位置
    if track[-1] != distance:
        track.append(distance)
    
    return track

def login(page):
    """完整的滑块登录流程"""
    username = "your_username"
    password = "your_password"
    
    login_url = 'https://login.dangdang.com'
    page.get(login_url)
    
    try:        
        # 2. 输入用户名和密码（模拟真人输入）
        username_field = page.ele('xpath://input[@type="text" and @autofocus="autofocus"]')
        username_field.click()
        time.sleep(random.uniform(0.5, 1.0))
        for char in username:
            username_field.input(char)
            time.sleep(random.uniform(0.1, 0.3))  # 逐字符随机延迟
        
        time.sleep(random.uniform(0.5, 1.5))
        
        password_field = page.ele('xpath://input[@type="password" and @autofocus="autofocus"]')
        password_field.click()
        time.sleep(random.uniform(0.5, 1.0))
        for char in password:
            password_field.input(char)
            time.sleep(random.uniform(0.1, 0.3))
        
        time.sleep(random.uniform(0.5, 1.5))
        
        # 3. 点击登录
        page.ele('xpath://input[@type="radio" and @title="同意用户协议、隐私政策选择框" ]').click()
        page.ele('xpath://a[@class="btn"]').click()
        time.sleep(3)
        
        # 最多尝试1次滑块
        for attempt in range(1):
            print(f"尝试第{attempt+1}次滑块验证")
            
            # 5. 下载验证码图片
            if not download_img(page):
                time.sleep(1)
                continue
            
            # 6. 识别缺口位置
            distance = recognize_captcha()
            if distance is None:
                print("无法识别缺口位置，使用随机距离")
                distance = random.randint(100, 200)
            else:
                # 添加随机偏移 ±5px
                distance += random.randint(-5, 5)
                distance = max(0, distance)  # 确保不负
            
            # 7. 生成拖动轨迹
            tracks = generate_track(distance)
            
            # 8. 执行拖动
            print("开始拖动滑块")
            slider = page.ele("xpath://div[@id='sliderBtn']", timeout=5)
            
            # 轻轻悬停
            slider.hover()
            time.sleep(0.5)

            # 按住滑块
            page.actions.hold(slider)
            time.sleep(0.3)

            prev_pos = 0
            # 平稳滑动，无上下乱飘、无随机停顿
            for pos in tracks:
                move_x = pos - prev_pos
                # Y 轴固定 0，不上下乱动
                page.actions.move(move_x, 0, duration=0.008)
                prev_pos = pos

            # 释放
            time.sleep(0.2)
            page.actions.release()
            time.sleep(2)
            
            # 9. 验证是否登录成功
            print("等待页面加载...")
            time.sleep(3)
            if "用户名或密码输入错误，请核对后重新输入 " in page.html:
                print("登录成功")
                return True
            
        
       
        return False
            
    except Exception as e:
        print(f"登录过程中出错: {e}")
        return False

if __name__ == "__main__":
    # 创建浏览器配置
    co = ChromiumOptions()
    
    # 指定 chromedriver 路径
    driver_path = r"C:\Program Files (x86)\Microsoft\Edge\Application\chromedriver.exe"
    chrome_path= r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
    co.set_paths(browser_path=chrome_path)
    
    co.set_argument("--disable-infobars")
    co.set_argument("--disable-gpu")
    co.set_argument("--disable-blink-features=AutomationControlled")
    co.set_argument("--window-size=1920,1080")
    co.set_pref("useAutomationExtension", False)
    co.set_user_agent("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    co.set_argument("--disable-web-security")
    co.set_argument("--allow-running-insecure-content")
    co.set_argument("--disable-extensions")
    co.set_argument("--no-first-run")
    co.set_argument("--disable-default-apps")
    co.set_argument("--disable-sync")
    co.set_argument("--incognito")
    
    # 初始化页面
    page = ChromiumPage(addr_or_opts=co)
    
    # 注入脚本，屏蔽webdriver特征并模拟真实行为
    page.run_js('''
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
    
    # 模拟页面滚动
    page.run_js('window.scrollTo(0, ' + str(random.randint(100, 300)) + ');')
    time.sleep(random.uniform(0.5, 1.0))
    page.run_js('window.scrollTo(0, 0);')
    time.sleep(random.uniform(0.5, 1.0))
    
    # 执行登录
    try:
        success = login(page)
        print(f"最终结果: {'成功' if success else '失败'}")
    except Exception as e:
        print(f"发生错误: {e}")
    finally:
        time.sleep(5)  # 保持浏览器打开几秒便于观察
        page.quit()