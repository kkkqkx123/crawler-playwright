import os
from dotenv import load_dotenv

# 加载 .env 文件中的环境变量
load_dotenv()
import os
import re
import base64

import httpx
import lxml.html
from openai import OpenAI
from openai import OpenAI  # type: ignore

# ---------- 配置 ----------
TARGET_URL = "https://spiderbuf.cn/web-scraping-practice/web-scraping-with-captcha"
LOGIN_URL = "https://spiderbuf.cn/web-scraping-practice/web-scraping-with-captcha/login"

# ModelScope API 配置（使用新的 API Key 和 Base URL）
MODELScope_API_KEY = os.environ["MODELScope_API_KEY"]
MODELScope_BASE_URL = "https://api-inference.modelscope.cn/v1"   # ModelScope 的 OpenAI 兼容端点
OCR_MODEL = "Qwen/Qwen3-VL-235B-A22B-Instruct"                    # 使用 Qwen 多模态模型进行 OCR

# 登录凭据
USERNAME = "admin"
PASSWORD = "123456"

# 请求头（模拟浏览器）
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36 Edg/145.0.0.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "Origin": "https://spiderbuf.cn",
    "Referer": TARGET_URL,
}
# ---------- 配置结束 ----------


def get_page_and_extract_data(client: httpx.Client):
    """访问目标页面，提取验证码图片 URL 和 captchaId"""
    resp = client.get(TARGET_URL, headers=HEADERS)
    resp.raise_for_status()
    html = lxml.html.fromstring(resp.text)

    # 图片元素
    img_src = html.xpath('//img[@id="image"]/@src')
    if not img_src:
        raise RuntimeError("未找到验证码图片元素")
    img_url = httpx.URL(TARGET_URL).join(img_src[0])   # 拼接为绝对 URL
    print(f"[DEBUG] 图片 URL: {img_url}")

    # 隐藏字段 captchaId
    captcha_id = html.xpath('//input[@name="captchaId"]/@value')
    if not captcha_id:
        raise RuntimeError("未找到 captchaId 隐藏字段")
    captcha_id = captcha_id[0]
    print(f"[DEBUG] captchaId: {captcha_id}")

    return img_url, captcha_id


def download_image_as_base64(client: httpx.Client, img_url: str) -> str:
    """下载图片并转换为 base64 数据 URI"""
    resp = client.get(img_url, headers=HEADERS)
    resp.raise_for_status()
    img_data = resp.content
    b64 = base64.b64encode(img_data).decode("utf-8")
    # 根据实际图片类型（网站返回的是 PNG）构造 data URI
    return f"data:image/png;base64,{b64}"


def ocr_captcha(image_data_uri: str) -> str:
    """调用 ModelScope Qwen-VL 模型识别验证码，返回 6 位数字"""
    # 初始化 OpenAI 客户端（指向 ModelScope）
    client = OpenAI(api_key=MODELScope_API_KEY, base_url=MODELScope_BASE_URL)

    try:
        response = client.chat.completions.create(
            model=OCR_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "请识别图片中的6位数字验证码，只输出数字，不要有任何额外文字。"},
                        {"type": "image_url", "image_url": {"url": image_data_uri}}
                    ]
                }
            ],
            max_tokens=128,
            temperature=0.0
        )
        if not response.choices or not response.choices[0].message.content:
            raise RuntimeError("OCR API 返回空结果")
        ocr_text = response.choices[0].message.content.strip()
        print(f"[DEBUG] OCR 原始输出: {ocr_text}")

        # 提取连续的 6 位数字
        match = re.search(r"\d{6}", ocr_text)
        if not match:
            raise RuntimeError(f"OCR 结果中未找到 6 位数字: {ocr_text}")
        return match.group(0)
    except Exception as e:
        raise RuntimeError(f"OCR 调用失败: {e}")


def login(client: httpx.Client, captcha_id: str, captcha_solution: str) -> httpx.Response:
    """提交登录表单，返回响应（自动跟随重定向）"""
    data = {
        "username": USERNAME,
        "password": PASSWORD,
        "captchaSolution": captcha_solution,
        "captchaId": captcha_id,
    }
    # 注意：POST 请求需要 Content-Type: application/x-www-form-urlencoded，httpx 自动处理
    resp = client.post(LOGIN_URL, data=data, headers=HEADERS, follow_redirects=True)
    resp.raise_for_status()
    return resp


def main():
    with httpx.Client() as client:
        # 1. 获取页面，提取图片 URL 和 captchaId
        img_url, captcha_id = get_page_and_extract_data(client)

        # 2. 下载图片并转为 base64
        image_data_uri = download_image_as_base64(client, str(img_url))

        # 3. OCR 识别
        captcha_solution = ocr_captcha(image_data_uri)
        print(f"[INFO] 识别出的验证码: {captcha_solution}")

        # 4. 登录
        login_resp = login(client, captcha_id, captcha_solution)

        # 5. 输出登录后的页面内容（或检查是否成功）
        print("\n[INFO] 登录成功，返回页面预览：")
        # 提取 body 文本前 500 字符作为预览
        # 由于是测试网站，返回原页面是符合预期的
        body_text = login_resp.text
        preview = body_text[:500] + ("..." if len(body_text) > 500 else "")
        print(preview)


if __name__ == "__main__":
    main()