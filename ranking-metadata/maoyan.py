import asyncio
import json
import os
import re
from datetime import datetime
from typing import List, Dict

from playwright.async_api import async_playwright


async def extract_movie_info(dd_element) -> Dict:
    """从单个 <dd> 元素中提取电影信息"""
    info = {}
    
    # 排名
    index_elem = await dd_element.query_selector(".board-index")
    if index_elem:
        index_text = await index_elem.inner_text()
        info["rank"] = int(index_text.strip())
    
    # 电影名称
    name_elem = await dd_element.query_selector(".name a")
    if name_elem:
        info["title"] = (await name_elem.inner_text()).strip()
        # 提取电影详情页链接
        href = await name_elem.get_attribute("href")
        if href:
            info["detail_url"] = f"https://www.maoyan.com{href}"
    
    # 主演
    star_elem = await dd_element.query_selector(".star")
    if star_elem:
        star_text = await star_elem.inner_text()
        # 去除"主演："前缀
        info["actors"] = star_text.replace("主演：", "").strip()
    
    # 上映时间
    release_elem = await dd_element.query_selector(".releasetime")
    if release_elem:
        release_text = await release_elem.inner_text()
        # 去除"上映时间："前缀
        info["release_date"] = release_text.replace("上映时间：", "").strip()
    
    # 评分
    integer_elem = await dd_element.query_selector(".integer")
    fraction_elem = await dd_element.query_selector(".fraction")
    if integer_elem and fraction_elem:
        integer_part = await integer_elem.inner_text()
        fraction_part = await fraction_elem.inner_text()
        info["score"] = float(f"{integer_part}{fraction_part}")
    
    return info


async def fetch_page(page, url: str) -> List[Dict]:
    """抓取单页电影数据（每页10条）"""
    print(f"正在请求: {url}")
    await page.goto(url, wait_until="domcontentloaded")
    
    # 等待电影列表加载（等待 .board-wrapper dd 出现）
    try:
        await page.wait_for_selector(".board-wrapper dd", timeout=10000)
    except Exception as e:
        print(f"页面加载超时或未找到电影列表: {e}")
        return []
    
    # 获取所有电影条目
    dd_elements = await page.query_selector_all(".board-wrapper dd")
    movies = []
    
    for dd in dd_elements:
        movie_info = await extract_movie_info(dd)
        if movie_info:  # 只添加有效数据
            movies.append(movie_info)
    
    print(f"本页抓取到 {len(movies)} 条电影数据")
    return movies


async def save_page_data(movies: List[Dict], page_num: int):
    """保存单页数据到独立文件"""
    page_file = f"maoyan_top100_page_{page_num}.json"
    try:
        with open(page_file, "w", encoding="utf-8") as f:
            json.dump(movies, f, ensure_ascii=False, indent=2)
        print(f"第 {page_num} 页已保存到 {page_file}")
    except IOError as e:
        print(f"保存第 {page_num} 页失败: {e}")


async def main():
    base_url = "https://www.maoyan.com/board/4"
    all_movies = []
    
    async with async_playwright() as p:
        # 启动浏览器（使用无头模式，但添加更真实的浏览器指纹）
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )
        page = await context.new_page()
        
        # 猫眼TOP100共10页，每页10条，offset参数从0开始，步长10
        for offset in range(0, 100, 10):
            url = f"{base_url}?offset={offset}"
            page_num = offset // 10 + 1
            
            movies = await fetch_page(page, url)
            if not movies:
                print(f"第 {page_num} 页未抓取到数据，停止爬取")
                break
            
            all_movies.extend(movies)
            
            # 保存单页数据（增量保存）
            await save_page_data(movies, page_num)
            
            # 随机延迟，避免请求过快（1-3秒）
            await asyncio.sleep(2)
        
        await browser.close()
    
    # 输出最终结果统计
    print(f"\n共抓取 {len(all_movies)} 条电影数据（目标100条）")
    
    # 备份现有完整文件（如果存在）
    full_file = "maoyan_top100.json"
    if os.path.exists(full_file):
        backup_name = f"maoyan_top100_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        os.rename(full_file, backup_name)
        print(f"已备份原文件为: {backup_name}")
    
    # 保存完整数据（带异常处理）
    try:
        with open(full_file, "w", encoding="utf-8") as f:
            json.dump(all_movies, f, ensure_ascii=False, indent=2)
        print(f"完整数据已保存到 {full_file}")
    except IOError as e:
        print(f"保存完整文件失败: {e}")
    
    # 打印前3条示例
    print("\n前3条数据示例：")
    for movie in all_movies[:3]:
        print(json.dumps(movie, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())