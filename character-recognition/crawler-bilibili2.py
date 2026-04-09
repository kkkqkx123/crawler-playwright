"""
B站验证码自动登录 v5
改进：
1. 强化prompt - 明确顺序+中心点要求
2. 坐标二次验证 - 裁剪VL给出的坐标区域，再次确认是否是目标字
3. 验证失败时微调坐标重试
"""

import time
import base64
import re
import io
import json
from PIL import Image
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from openai import OpenAI

# ========== 配置 ==========
BILIBILI_USERNAME = "xxx"
BILIBILI_PASSWORD = "xxx"
QWEN_API_KEY = "xxx"
# ==========================

def get_qwen_client():
    return OpenAI(
        api_key=QWEN_API_KEY,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
    )


def qwen_vl(image_bytes: bytes, prompt: str) -> str:
    b64 = base64.b64encode(image_bytes).decode()
    client = get_qwen_client()
    resp = client.chat.completions.create(
        model="qwen-vl-plus",
        messages=[{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
            {"type": "text", "text": prompt}
        ]}]
    )
    return resp.choices[0].message.content.strip()


def recognize_prompt_chars(tip_bytes: bytes) -> list:
    """识别题目图中需要依次点击的汉字列表"""
    raw = qwen_vl(tip_bytes,
        "这是验证码题目图片，图中显示了需要依次点击的汉字。"
        "请只输出这些汉字，按图中从左到右的顺序，用逗号分隔，不要其他任何内容。"
        "例如：烦,闷 或 冷,鲜,甜"
    )
    chars = [c.strip() for c in re.split(r"[,，、\s]+", raw) if c.strip()]
    print(f"[题目识别] 原始: {raw!r} → {chars}")
    return chars


def find_chars_coords(big_bytes: bytes, target_chars: list) -> dict:
    """
    发整张大图给VL，要求返回每个目标字的精确中心坐标
    强化prompt：强调艺术字、中心点、像素精度
    """
    chars_str = "、".join(target_chars)
    img = Image.open(io.BytesIO(big_bytes))
    w, h = img.size

    prompt = f"""这是一张文字点选验证码图片（尺寸{w}x{h}像素）。
图中散布着若干个带艺术效果的汉字图标（有描边、阴影或渐变色）。

请在图中找到以下汉字图标的精确位置：{chars_str}

要求：
1. 返回每个汉字图标的【中心点】像素坐标（不是文字周围空白区域的中心）
2. 坐标原点在图片左上角，x向右，y向下
3. 请仔细辨认每个图标，不要猜测
4. 严格按照如下JSON格式返回，不要有任何其他文字或解释

格式示例（假设目标是"冷"和"鲜"）：
{{"冷": {{"x": 153, "y": 87}}, "鲜": {{"x": 241, "y": 193}}}}

如果某个字确实找不到，设为null：
{{"冷": {{"x": 153, "y": 87}}, "鲜": null}}"""

    raw = qwen_vl(big_bytes, prompt)
    print(f"[VL坐标] 原始返回: {raw!r}")
    coords = parse_coords(raw, target_chars)
    print(f"[VL坐标] 解析结果: {coords}")
    return coords


def parse_coords(raw: str, target_chars: list) -> dict:
    """容错解析VL返回的JSON坐标"""
    clean = re.sub(r"```(?:json)?|```", "", raw).strip()
    try:
        data = json.loads(clean)
        result = {}
        for ch in target_chars:
            if ch in data and data[ch] is not None:
                v = data[ch]
                if isinstance(v, dict) and "x" in v and "y" in v:
                    result[ch] = {"x": int(v["x"]), "y": int(v["y"])}
        return result
    except Exception:
        pass
    # 正则兜底
    result = {}
    for ch in target_chars:
        pat = re.escape(ch) + r'["\s]*:\s*\{["\s]*x["\s]*:\s*(\d+)[^}]+y["\s]*:\s*(\d+)'
        m = re.search(pat, raw)
        if m:
            result[ch] = {"x": int(m.group(1)), "y": int(m.group(2))}
    return result


def verify_coord(big_bytes: bytes, ch: str, x: int, y: int, radius: int = 40) -> bool:
    """
    裁剪坐标附近 radius*2 x radius*2 的区域，
    让VL确认这里是否就是目标字符
    """
    img = Image.open(io.BytesIO(big_bytes))
    x1 = max(0, x - radius)
    y1 = max(0, y - radius)
    x2 = min(img.width,  x + radius)
    y2 = min(img.height, y + radius)
    crop = img.crop((x1, y1, x2, y2))

    buf = io.BytesIO()
    crop.save(buf, format="PNG")

    raw = qwen_vl(buf.getvalue(),
        f"这个图片中有一个汉字图标（有艺术效果），请问这个汉字是不是\"{ch}\"？"
        f"只回答\"是\"或\"否\"，不要其他内容。"
    )
    result = "是" in raw or ch in raw
    print(f"  [验证] {ch!r} 坐标({x},{y}) → VL回答: {raw!r} → {'✓通过' if result else '✗失败'}")
    return result


def js_click(driver, element, ox: int, oy: int):
    script = """
    var el = arguments[0];
    var rect = el.getBoundingClientRect();
    var cx = rect.left + arguments[1];
    var cy = rect.top  + arguments[2];
    ['mousemove','mousedown','mouseup','click'].forEach(function(t){
        el.dispatchEvent(new MouseEvent(t, {
            bubbles:true, cancelable:true, view:window,
            clientX:cx, clientY:cy
        }));
    });
    """
    driver.execute_script(script, element, ox, oy)


def solve_captcha(driver, wait) -> bool:
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.geetest_panel_box")))
    time.sleep(1.5)

    tip_el  = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.geetest_tip_img")))
    wrap_el = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.geetest_item_wrap")))

    tip_bytes = tip_el.screenshot_as_png
    big_bytes = wrap_el.screenshot_as_png
    print(f"[截图] 题目 {len(tip_bytes)} bytes，大图 {len(big_bytes)} bytes")

    # 1. 识别题目
    target_chars = recognize_prompt_chars(tip_bytes)
    if not target_chars:
        print("[错误] 题目识别失败")
        return False

    # 2. VL定位坐标
    coords = find_chars_coords(big_bytes, target_chars)
    if not coords:
        print("[错误] VL未返回有效坐标")
        return False

    # 3. 坐标缩放
    big_img = Image.open(io.BytesIO(big_bytes))
    shot_w, shot_h = big_img.size
    css_w = wrap_el.size["width"]
    css_h = wrap_el.size["height"]
    scale_x = css_w / shot_w
    scale_y = css_h / shot_h

    # 4. 二次验证 + 点击
    clicked = []
    for ch in target_chars:
        if ch not in coords:
            print(f"[警告] VL未找到: {ch!r}")
            continue

        pos = coords[ch]
        x, y = pos["x"], pos["y"]

        # 坐标合理性检查（防止VL瞎返回边界外坐标）
        if not (5 < x < shot_w - 5 and 5 < y < shot_h - 5):
            print(f"[警告] {ch!r} 坐标({x},{y})超出图片范围，跳过")
            continue

        # 二次验证
        confirmed = verify_coord(big_bytes, ch, x, y)

        if not confirmed:
            # 验证失败：尝试重新问VL，换一个更精确的prompt
            print(f"  [重试] 坐标验证失败，向VL重新确认 {ch!r} 的位置...")
            retry_prompt = (
                f"这是一张验证码图片（{shot_w}x{shot_h}像素）。"
                f"请找到汉字\"{ch}\"图标的中心点坐标。"
                f"只返回JSON：{{\"x\": 数字, \"y\": 数字}}"
            )
            retry_raw = qwen_vl(big_bytes, retry_prompt)
            print(f"  [重试] VL返回: {retry_raw!r}")
            # 解析重试结果
            m = re.search(r'"?x"?\s*:\s*(\d+)[^}]+"?y"?\s*:\s*(\d+)', retry_raw)
            if m:
                x, y = int(m.group(1)), int(m.group(2))
                print(f"  [重试] 新坐标: ({x},{y})")

        ox = int(x * scale_x)
        oy = int(y * scale_y)
        print(f"[点击] {ch!r}  坐标=({x},{y})  CSS偏移=({ox},{oy})")
        js_click(driver, wrap_el, ox, oy)
        time.sleep(0.7)
        clicked.append(ch)

    print(f"[统计] 期望 {len(target_chars)} 个，点击了 {len(clicked)} 个: {clicked}")

    if not clicked:
        print("[错误] 没有成功点击任何字符")
        return False

    time.sleep(0.8)

    try:
        btn = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "a.geetest_commit")))
        driver.execute_script("arguments[0].click();", btn)
        print("[操作] 已点击确认")
    except Exception as e:
        print(f"[错误] 确认失败: {e}")
        return False

    return True


def login_bilibili():
    options = webdriver.EdgeOptions()
    driver  = webdriver.Edge(options=options)
    wait    = WebDriverWait(driver, 15)

    try:
        driver.get("https://passport.bilibili.com/login")
        time.sleep(2)

        wait.until(EC.presence_of_element_located(
            (By.CSS_SELECTOR, "input[placeholder='请输入账号']")
        )).send_keys(BILIBILI_USERNAME)
        time.sleep(0.3)

        driver.find_element(By.CSS_SELECTOR, "input[placeholder='请输入密码']"
                            ).send_keys(BILIBILI_PASSWORD)
        time.sleep(0.3)

        driver.find_element(By.CSS_SELECTOR, "div.btn_primary").click()
        print("[操作] 已点击登录，等待验证码...")
        time.sleep(2)

        for attempt in range(1, 6):
            print(f"\n===== 验证码尝试 第{attempt}次 =====")

            try:
                wait.until(EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "div.geetest_panel_box")))
            except Exception:
                print("[信息] 验证码消失，登录成功")
                break

            try:
                ok = solve_captcha(driver, wait)
            except Exception:
                import traceback; traceback.print_exc()
                ok = False

            time.sleep(2.5)

            try:
                driver.find_element(By.CSS_SELECTOR, "div.geetest_panel_box")
                print("[结果] 验证失败，刷新重试...")
                try:
                    driver.find_element(By.CSS_SELECTOR, "a.geetest_refresh").click()
                    time.sleep(1.5)
                except Exception:
                    pass
            except Exception:
                print("[结果] ✅ 验证码通过！")
                break

        print("\n保持30s")
        time.sleep(30)

    except Exception:
        import traceback; traceback.print_exc()
    finally:
        driver.quit()


if __name__ == "__main__":
    login_bilibili()