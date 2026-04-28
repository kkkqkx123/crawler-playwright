"""
简化版性能基准测试
快速对比多进程和协程的性能差异
"""

import time
import requests
import asyncio
import aiohttp
import psutil
import os
from multiprocessing import Pool
from urllib.parse import urljoin
from pathlib import Path
from datetime import datetime
from typing import Optional
import re


class QuickBenchmark:
    def __init__(self, page_url: str, output_dir: str = r"D:\项目\crawler\py-playwright\video-crawling\output"):
        self.page_url = page_url
        self.output_dir = Path(output_dir)
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36 Edg/147.0.0.0',
            'Accept': '*/*',
            'Accept-Encoding': 'identity;q=1, *;q=0',
            'Accept-Language': 'zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7,en-GB;q=0.6',
            'Cache-Control': 'no-cache',
            'Origin': 'https://m.bpfun.com',
            'Referer': 'https://m.bpfun.com/',
        }
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.process = psutil.Process(os.getpid())
    
    def get_resource_usage(self) -> dict:
        cpu_percent = self.process.cpu_percent(interval=0.1)
        memory_info = self.process.memory_info()
        return {
            'cpu_percent': cpu_percent,
            'memory_mb': memory_info.rss / 1024 / 1024,
        }
    
    def get_m3u8_url_from_page(self) -> str:
        page_headers = {
            'User-Agent': self.headers['User-Agent'],
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': self.headers['Accept-Language'],
        }
        response = requests.get(self.page_url, headers=page_headers, timeout=30)
        response.raise_for_status()
        html_content = response.text
        
        patterns = [
            r'https?://[^\s\'"<>]+\.m3u8[^\s\'"<>]*',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, html_content)
            if matches:
                m3u8_url = matches[0].replace('\\/', '/')
                return m3u8_url
        
        raise ValueError("未能从页面中提取到m3u8地址")
    
    def fetch_m3u8_content(self, m3u8_url: str) -> str:
        response = requests.get(m3u8_url, headers=self.headers, timeout=30)
        response.raise_for_status()
        return response.text
    
    def parse_m3u8(self, m3u8_content: str, m3u8_url: str) -> tuple[list[str], float]:
        lines = m3u8_content.strip().split('\n')
        ts_urls = []
        segment_duration = 0.0
        has_ts = False
        
        for line in lines:
            if not line.startswith('#') and line.strip() and '.ts' in line:
                has_ts = True
                break
        
        if has_ts:
            for line in lines:
                if line.startswith('#EXT-X-TARGETDURATION:'):
                    segment_duration = float(line.split(':')[1])
                    break
            
            for line in lines:
                if not line.startswith('#') and line.strip() and '.ts' in line:
                    ts_url = urljoin(m3u8_url, line.strip())
                    ts_urls.append(ts_url)
        else:
            for line in lines:
                if not line.startswith('#') and line.strip():
                    sub_m3u8_url = urljoin(m3u8_url, line.strip())
                    sub_content = self.fetch_m3u8_content(sub_m3u8_url)
                    ts_urls, segment_duration = self.parse_m3u8(sub_content, sub_m3u8_url)
                    break
                
        return ts_urls, segment_duration
    
    def download_segment_to_memory(self, ts_url: str) -> bytes:
        response = requests.get(ts_url, headers=self.headers, timeout=60, stream=True)
        response.raise_for_status()
        data = b''
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                data += chunk
        return data
    
    def multi_process_download(self, ts_urls: list[str], max_workers: int) -> dict:
        print(f"\n多进程下载测试 ({max_workers} 个进程)...")
        
        start_time = time.time()
        start_resource = self.get_resource_usage()
        
        def download_worker(url: str) -> tuple[bool, int]:
            try:
                response = requests.get(url, headers=self.headers, timeout=60, stream=True)
                response.raise_for_status()
                data = b''
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        data += chunk
                return True, len(data)
            except:
                return False, 0
        
        with Pool(processes=max_workers) as pool:
            results = pool.map(download_worker, ts_urls)
        
        total_bytes = sum(size for success, size in results if success)
        success_count = sum(1 for success, size in results if success)
        
        end_time = time.time()
        end_resource = self.get_resource_usage()
        elapsed_time = end_time - start_time
        
        return {
            'total_bytes': total_bytes,
            'elapsed_time': elapsed_time,
            'success_count': success_count,
            'avg_speed': total_bytes / elapsed_time / 1024 if elapsed_time > 0 else 0,
            'cpu_percent': (start_resource['cpu_percent'] + end_resource['cpu_percent']) / 2,
            'memory_mb': end_resource['memory_mb'],
            'method': f'多进程({max_workers})',
        }
    
    async def coroutine_download_async(self, ts_urls: list[str], max_workers: int) -> dict:
        print(f"\n协程下载测试 ({max_workers} 个协程)...")
        
        start_time = time.time()
        start_resource = self.get_resource_usage()
        
        async def download_worker(url: str, semaphore: asyncio.Semaphore) -> tuple[bool, int]:
            async with semaphore:
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(url, headers=self.headers, timeout=aiohttp.ClientTimeout(total=60)) as response:
                            data = await response.read()
                    return True, len(data)
                except:
                    return False, 0
        
        semaphore = asyncio.Semaphore(max_workers)
        tasks = [download_worker(url, semaphore) for url in ts_urls]
        results = await asyncio.gather(*tasks)
        
        total_bytes = sum(size for success, size in results if success)
        success_count = sum(1 for success, size in results if success)
        
        end_time = time.time()
        end_resource = self.get_resource_usage()
        elapsed_time = end_time - start_time
        
        return {
            'total_bytes': total_bytes,
            'elapsed_time': elapsed_time,
            'success_count': success_count,
            'avg_speed': total_bytes / elapsed_time / 1024 if elapsed_time > 0 else 0,
            'cpu_percent': (start_resource['cpu_percent'] + end_resource['cpu_percent']) / 2,
            'memory_mb': end_resource['memory_mb'],
            'method': f'协程({max_workers})',
        }
    
    def coroutine_download(self, ts_urls: list[str], max_workers: int) -> dict:
        return asyncio.run(self.coroutine_download_async(ts_urls, max_workers))
    
    def run_benchmark(self, target_duration: float = 60.0):
        print("=" * 60)
        print("快速性能基准测试")
        print("=" * 60)
        
        # 获取m3u8地址
        m3u8_url = self.get_m3u8_url_from_page()
        print(f"找到m3u8地址: {m3u8_url}")
        
        # 解析m3u8
        m3u8_content = self.fetch_m3u8_content(m3u8_url)
        ts_urls, segment_duration = self.parse_m3u8(m3u8_content, m3u8_url)
        
        if not ts_urls:
            raise ValueError("未能从m3u8文件中提取到任何ts片段")
        
        print(f"共找到 {len(ts_urls)} 个视频片段")
        
        # 计算需要下载的片段
        if segment_duration <= 0:
            segment_duration = 5.0
        segments_needed = int(target_duration / segment_duration)
        segments_needed = min(segments_needed, len(ts_urls))
        ts_urls_to_download = ts_urls[:segments_needed]
        
        print(f"需要下载 {segments_needed} 个片段 (约{target_duration}秒)")
        
        # 运行测试
        results = []
        
        # 多进程测试
        result = self.multi_process_download(ts_urls_to_download, 10)
        results.append(result)
        
        # 协程测试
        result = self.coroutine_download(ts_urls_to_download, 10)
        results.append(result)
        
        # 输出结果
        print(f"\n{'='*60}")
        print("性能对比结果")
        print(f"{'='*60}")
        print(f"\n{'方法':<15} {'耗时(秒)':<12} {'速度(KB/s)':<15} {'CPU(%)':<10} {'内存(MB)':<10}")
        print("-" * 70)
        
        for result in results:
            print(f"{result['method']:<15} {result['elapsed_time']:<12.2f} {result['avg_speed']:<15.2f} {result['cpu_percent']:<10.1f} {result['memory_mb']:<10.1f}")
        
        print(f"\n{'='*60}")
        print("结论:")
        if len(results) == 2:
            mp_result = results[0]
            coro_result = results[1]
            
            speedup = mp_result['elapsed_time'] / coro_result['elapsed_time']
            memory_diff = (1 - coro_result['memory_mb']/mp_result['memory_mb']) * 100
            
            print(f"1. 协程相比多进程速度: {speedup:.2f}x")
            print(f"2. 协程内存节省: {memory_diff:.1f}%")
            print(f"3. 协程CPU使用: {coro_result['cpu_percent']:.1f}%")
            print(f"4. 多进程CPU使用: {mp_result['cpu_percent']:.1f}%")
            print(f"5. 对于IO密集型任务，协程资源占用更低")


def main():
    page_url = "https://m.bpfun.com/play/31226-0-0.html"
    
    benchmark = QuickBenchmark(
        page_url=page_url,
        output_dir=r"D:\项目\crawler\py-playwright\video-crawling\output"
    )
    
    # 快速测试：只下载前1分钟
    benchmark.run_benchmark(target_duration=60.0)


if __name__ == "__main__":
    main()
