import random
from DrissionPage import ChromiumPage, ChromiumOptions
import time
import base64
import cv2
import os

def download_img(page, save_dir="week_2/img"):
    """下载验证码图片"""
    try:  

        main_image = page.ele("#main_img", timeout=5)
        slot_image = page.ele("#slot_img", timeout=5)
        
        main_src = main_image.attr("src")
        slot_src = slot_image.attr("src")
        
        main_base64 = main_src.split(",")[1]
        slot_base64 = slot_src.split(",")[1]
        
        main_img_data = base64.b64decode(main_base64)
        slot_img_data = base64.b64decode(slot_base64)
        
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
        adjusted_distance = int(distance * 275 / 290) + 12  # 增加15px补偿
        
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
    """
    生成更像真人的滑块轨迹：贝塞尔曲线模拟 + 随机停顿 + 加速减速
    """
    
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

def login(page):
    """完整的滑块登录流程"""
    username = "your_username"
    password = "your_password"
    
    login_url = 'https://passport.jd.com/new/login.aspx'
    page.get(login_url)
    
    try:
        # 1. 点击密码登录
        page.ele("#pwd-login").click()
        time.sleep(2)
        
        # 2. 输入用户名和密码（模拟真人输入）
        username_field = page.ele("#loginname")
        username_field.click()
        time.sleep(random.uniform(0.5, 1.0))
        for char in username:
            username_field.input(char)
            time.sleep(random.uniform(0.1, 0.3))  # 逐字符随机延迟
        
        time.sleep(random.uniform(0.5, 1.5))
        
        password_field = page.ele("#nloginpwd")
        password_field.click()
        time.sleep(random.uniform(0.5, 1.0))
        for char in password:
            password_field.input(char)
            time.sleep(random.uniform(0.1, 0.3))
        
        time.sleep(random.uniform(0.5, 1.5))
        
        # 3. 点击登录
        page.ele("#loginsubmit").click()
        time.sleep(3)
        
        # 4. 检查是否出现滑块验证
        slider_element = page.ele("#main_img", timeout=5)
        if not slider_element:
            print("没有检测到滑块，登录可能已成功")
            return True
        
        print("检测到滑块验证，开始处理...")
        
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
            slider = page.ele(".move-img", timeout=5)
            
            # 鼠标移到滑块上，模拟真人犹豫
            slider.hover()
            time.sleep(random.uniform(0.8, 2.0))  # 更长的停顿
            # 随机移动鼠标
            page.actions.move(random.randint(-5, 5), random.randint(-5, 5), duration=0.1)
            time.sleep(random.uniform(0.3, 0.8))
            
            # 按住滑块
            page.actions.hold(slider)
            time.sleep(random.uniform(0.3, 1.0))  # 更长的按住时间
            
            # 根据轨迹拖动，添加更大随机y偏移和更慢duration
            prev_pos = 0
            for i, pos in enumerate(tracks):
                relative_move = pos - prev_pos
                y_offset = random.randint(-8, 8)  # 更大y偏移
                # 动态duration：开始慢，中間快，结束慢
                if i < len(tracks) // 4:
                    duration = random.uniform(0.05, 0.12)  # 开始慢
                elif i > len(tracks) * 3 // 4:
                    duration = random.uniform(0.05, 0.12)  # 结束慢
                else:
                    duration = random.uniform(0.02, 0.06)  # 中间快
                page.actions.move(relative_move, y_offset, duration=duration)
                prev_pos = pos
                # 随机小停顿
                if random.random() < 0.15:
                    time.sleep(random.uniform(0.02, 0.08))
            
            # 释放鼠标
            page.actions.release()
            time.sleep(random.uniform(0.2, 0.5))  # 随机释放后停顿
            
            # 释放后随机移动鼠标，模拟真人行为
            for _ in range(random.randint(2, 5)):
                page.actions.move(random.randint(-20, 20), random.randint(-20, 20), duration=random.uniform(0.1, 0.3))
                time.sleep(random.uniform(0.1, 0.3))
            time.sleep(random.uniform(0.8, 1.5))
            
            # 9. 验证是否登录成功
            print("等待页面加载...")
            time.sleep(3)
            
            # 检查是否登录成功（检查URL变化或元素）
            current_url = page.url
            if 'passport' not in current_url or page.ele("xpath://span[contains(text(), '用户中心')]", timeout=2) or page.ele("#user-name", timeout=2):
                print("登录成功！")
                return True
            elif page.ele("xpath://*[contains(text(), '安全验证')]", timeout=2) or page.ele("xpath://*[contains(text(), '短信验证')]", timeout=2) or page.ele("#sendSmsCode", timeout=2):
                print("检测到进一步安全验证，请手动完成")
                # 这里可以添加等待用户输入或自动处理短信，但由于是作业，建议手动
                return False  # 或返回部分成功
            else:
                print("滑块失败，重试")
                time.sleep(2)  # 等待页面重置
        
        print("尝试失败")
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