import asyncio
import json
import os
import re
from typing import List, Dict

from playwright.async_api import async_playwright


async def extract_movie_info(item) -> Dict:
    """从单个电影条目中提取所需字段"""
    info = {}

    # 电影名称（中文）
    title_elem = await item.query_selector(".hd .title")
    info["title"] = (await title_elem.inner_text()).strip() if title_elem else None

    # 评分
    rating_elem = await item.query_selector(".rating_num")
    info["rating"] = float(await rating_elem.inner_text()) if rating_elem else None

    # 剧情简介（可能不存在）
    quote_elem = await item.query_selector(".quote span")
    info["plot"] = (await quote_elem.inner_text()).strip() if quote_elem else None

    # 详细信息（导演、主演、年份、国别、类型）位于 .bd p 标签内
    detail_p = await item.query_selector(".bd p")
    if detail_p:
        detail_text = await detail_p.inner_text()
        # 使用正则或字符串解析
        # 格式示例："导演: 弗兰克·德拉邦特 Frank Darabont   主演: 蒂姆·罗宾斯 Tim Robbins /...\n1994 / 美国 / 犯罪 剧情"
        lines = detail_text.strip().split("\n")
        first_line = lines[0].strip() if lines else ""
        second_line = lines[1].strip() if len(lines) > 1 else ""

        # 解析导演和主演
        director_match = re.search(r"导演:\s*(.+?)(?:\s{2,}主演:|\s*$)", first_line)
        info["director"] = director_match.group(1).strip() if director_match else None

        actor_match = re.search(r"主演:\s*(.+)", first_line)
        info["actors"] = actor_match.group(1).strip() if actor_match else None

        # 解析年份、国别、类型（都在第二行）
        # 格式："1994 / 美国 / 犯罪 剧情"
        if second_line:
            parts = [p.strip() for p in second_line.split("/")]
            if len(parts) >= 1:
                info["year"] = parts[0]
            if len(parts) >= 2:
                info["country"] = parts[1]
            if len(parts) >= 3:
                info["genre"] = parts[2]

    return info


async def fetch_page(page, url: str) -> List[Dict]:
    """抓取单页电影数据"""
    await page.goto(url, wait_until="domcontentloaded")
    # 等待电影列表加载
    await page.wait_for_selector("ol.grid_view li", timeout=10000)

    items = await page.query_selector_all("ol.grid_view li")
    movies = []
    for item in items:
        movie_info = await extract_movie_info(item)
        movies.append(movie_info)
    
    # 每页抓取完成后立即保存（增量保存）
    page_num = int(url.split("start=")[1].split("&")[0]) // 25 + 1
    page_file = f"douban_top250_page_{page_num}.json"
    try:
        with open(page_file, "w", encoding="utf-8") as f:
            json.dump(movies, f, ensure_ascii=False, indent=2)
        print(f"第 {page_num} 页已保存到 {page_file}")
    except IOError as e:
        print(f"保存第 {page_num} 页失败: {e}")
    
    return movies


async def main():
    base_url = "https://movie.douban.com/top250"
    all_movies = []

    async with async_playwright() as p:
        # 启动浏览器（无头模式，可改为 headless=False 观察）
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        for start in range(0, 250, 25):
            url = f"{base_url}?start={start}&filter="
            print(f"正在抓取: {url}")
            movies = await fetch_page(page, url)
            all_movies.extend(movies)
            # 适当延迟，避免请求过快
            await asyncio.sleep(2)

        await browser.close()

    # 输出结果
    print(f"共抓取 {len(all_movies)} 条电影数据")
    
    # 1. 创建备份机制（如果已有文件）
    if os.path.exists("douban_top250.json"):
        from datetime import datetime
        backup_name = f"douban_top250_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        os.rename("douban_top250.json", backup_name)
        print(f"已备份原文件为: {backup_name}")
    
    # 2. 保存最终完整文件（带异常处理）
    try:
        with open("douban_top250.json", "w", encoding="utf-8") as f:
            json.dump(all_movies, f, ensure_ascii=False, indent=2)
        print("数据已保存到 douban_top250.json")
    except IOError as e:
        print(f"保存文件失败: {e}")
    
    # 3. 打印前两条示例
    for m in all_movies[:2]:
        print(json.dumps(m, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())