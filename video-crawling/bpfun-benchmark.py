"""
性能基准测试
对比多进程和协程下载视频片段的性能差异和资源占用
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


class PerformanceBenchmark:
    def __init__(self, page_url: str, output_dir: str = r"D:\项目\crawler\py-playwright\video-crawling\output"):
        """
        初始化性能测试
        
        Args:
            page_url: 视频页面URL
            output_dir: 输出目录
        """
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
        # 创建输出目录
        self.output_dir.mkdir(parents=True, exist_ok=True)
        # 输出文件路径
        self.log_file = None
        self.log_path = None
        # 资源监控
        self.process = psutil.Process(os.getpid())
    
    def log_print(self, message: str):
        """
        同时输出到控制台和文件
        
        Args:
            message: 要输出的消息
        """
        print(message)
        if self.log_file:
            self.log_file.write(message + '\n')
            self.log_file.flush()
    
    def start_logging(self):
        """开始记录日志到文件"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_path = self.output_dir / f"benchmark_{timestamp}.txt"
        self.log_file = open(self.log_path, 'w', encoding='utf-8')
        self.log_print(f"日志文件: {self.log_path}")
    
    def stop_logging(self):
        """停止记录日志"""
        if self.log_file:
            self.log_file.close()
            self.log_file = None
    
    def get_resource_usage(self) -> dict:
        """获取当前资源使用情况"""
        cpu_percent = self.process.cpu_percent(interval=0.1)
        memory_info = self.process.memory_info()
        
        return {
            'cpu_percent': cpu_percent,
            'memory_mb': memory_info.rss / 1024 / 1024,  # MB
        }
        
    def get_m3u8_url_from_page(self) -> str:
        """从页面源码中提取m3u8地址"""
        self.log_print(f"正在获取页面: {self.page_url}")
        
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
            r'"url"\s*:\s*"(https?://[^"]+\.m3u8[^"]*)"',
            r'videoUrl\s*=\s*["\'](https?://[^"\']+\.m3u8[^"\']*)["\']',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, html_content)
            if matches:
                m3u8_url = matches[0]
                m3u8_url = m3u8_url.replace('\\/', '/')
                self.log_print(f"找到m3u8地址: {m3u8_url}")
                return m3u8_url
        
        raise ValueError("未能从页面中提取到m3u8地址")
    
    def fetch_m3u8_content(self, m3u8_url: str) -> str:
        """获取m3u8文件内容"""
        self.log_print(f"正在获取m3u8文件: {m3u8_url}")
        response = requests.get(m3u8_url, headers=self.headers, timeout=30)
        response.raise_for_status()
        return response.text
    
    def parse_m3u8(self, m3u8_content: str, m3u8_url: str) -> tuple[list[str], float]:
        """解析m3u8文件，提取ts片段URL和每个片段的时长"""
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
            self.log_print("检测到主m3u8文件，正在获取子m3u8...")
            for line in lines:
                if not line.startswith('#') and line.strip():
                    sub_m3u8_url = urljoin(m3u8_url, line.strip())
                    self.log_print(f"子m3u8地址: {sub_m3u8_url}")
                    sub_content = self.fetch_m3u8_content(sub_m3u8_url)
                    ts_urls, segment_duration = self.parse_m3u8(sub_content, sub_m3u8_url)
                    break
                
        return ts_urls, segment_duration
    
    def download_segment_to_memory(self, ts_url: str) -> bytes:
        """下载单个ts片段到内存（不存储到磁盘）"""
        response = requests.get(ts_url, headers=self.headers, timeout=60, stream=True)
        response.raise_for_status()
        
        data = b''
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                data += chunk
        
        return data
    
    def single_process_download(self, ts_urls: list[str]) -> dict:
        """单进程下载测试"""
        self.log_print(f"\n{'='*60}")
        self.log_print(f"单进程下载测试")
        self.log_print(f"{'='*60}")
        self.log_print(f"下载 {len(ts_urls)} 个片段...")
        
        start_time = time.time()
        start_resource = self.get_resource_usage()
        
        total_bytes = 0
        success_count = 0
        segment_times = []
        
        for i, url in enumerate(ts_urls):
            try:
                seg_start = time.time()
                data = self.download_segment_to_memory(url)
                seg_time = time.time() - seg_start
                
                total_bytes += len(data)
                success_count += 1
                segment_times.append(seg_time)
                self.log_print(f"[{i+1}/{len(ts_urls)}] 片段下载完成 ({len(data)/1024:.2f} KB, 用时: {seg_time:.2f}s)")
            except Exception as e:
                self.log_print(f"[{i+1}/{len(ts_urls)}] 片段下载失败: {e}")
        
        end_time = time.time()
        end_resource = self.get_resource_usage()
        elapsed_time = end_time - start_time
        
        return {
            'total_bytes': total_bytes,
            'elapsed_time': elapsed_time,
            'success_count': success_count,
            'total_count': len(ts_urls),
            'avg_speed': total_bytes / elapsed_time / 1024 if elapsed_time > 0 else 0,
            'avg_time_per_segment': elapsed_time / len(ts_urls),
            'segment_times': segment_times,
            'min_segment_time': min(segment_times) if segment_times else 0,
            'max_segment_time': max(segment_times) if segment_times else 0,
            'cpu_percent': (start_resource['cpu_percent'] + end_resource['cpu_percent']) / 2,
            'memory_mb': end_resource['memory_mb'],
            'method': '单进程',
            'workers': 1,
        }
    
    def multi_process_download(self, ts_urls: list[str], max_workers: int) -> dict:
        """多进程下载测试"""
        self.log_print(f"\n{'='*60}")
        self.log_print(f"多进程下载测试 ({max_workers} 个进程)")
        self.log_print(f"{'='*60}")
        self.log_print(f"下载 {len(ts_urls)} 个片段...")
        
        start_time = time.time()
        start_resource = self.get_resource_usage()
        
        def download_worker(url: str) -> tuple[bool, int, float]:
            try:
                seg_start = time.time()
                response = requests.get(url, headers=self.headers, timeout=60, stream=True)
                response.raise_for_status()
                
                data = b''
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        data += chunk
                
                seg_time = time.time() - seg_start
                return True, len(data), seg_time
            except Exception as e:
                return False, 0, 0
        
        with Pool(processes=max_workers) as pool:
            results = pool.map(download_worker, ts_urls)
        
        total_bytes = 0
        success_count = 0
        segment_times = []
        
        for i, (success, size, seg_time) in enumerate(results):
            if success:
                success_count += 1
                total_bytes += size
                segment_times.append(seg_time)
                self.log_print(f"[{success_count}/{len(ts_urls)}] 片段 {i} 下载完成 ({size/1024:.2f} KB, 用时: {seg_time:.2f}s)")
        
        end_time = time.time()
        end_resource = self.get_resource_usage()
        elapsed_time = end_time - start_time
        
        return {
            'total_bytes': total_bytes,
            'elapsed_time': elapsed_time,
            'success_count': success_count,
            'total_count': len(ts_urls),
            'avg_speed': total_bytes / elapsed_time / 1024 if elapsed_time > 0 else 0,
            'avg_time_per_segment': elapsed_time / len(ts_urls),
            'max_workers': max_workers,
            'segment_times': segment_times,
            'min_segment_time': min(segment_times) if segment_times else 0,
            'max_segment_time': max(segment_times) if segment_times else 0,
            'cpu_percent': (start_resource['cpu_percent'] + end_resource['cpu_percent']) / 2,
            'memory_mb': end_resource['memory_mb'],
            'method': f'多进程({max_workers})',
            'workers': max_workers,
        }
    
    async def coroutine_download_async(self, ts_urls: list[str], max_workers: int) -> dict:
        """协程下载测试（异步实现）"""
        self.log_print(f"\n{'='*60}")
        self.log_print(f"协程下载测试 ({max_workers} 个协程)")
        self.log_print(f"{'='*60}")
        self.log_print(f"下载 {len(ts_urls)} 个片段...")
        
        start_time = time.time()
        start_resource = self.get_resource_usage()
        
        async def download_worker(url: str, semaphore: asyncio.Semaphore) -> tuple[bool, int, float]:
            async with semaphore:
                try:
                    seg_start = time.time()
                    async with aiohttp.ClientSession() as session:
                        async with session.get(url, headers=self.headers, timeout=aiohttp.ClientTimeout(total=60)) as response:
                            data = await response.read()
                    
                    seg_time = time.time() - seg_start
                    return True, len(data), seg_time
                except Exception as e:
                    return False, 0, 0
        
        semaphore = asyncio.Semaphore(max_workers)
        tasks = [download_worker(url, semaphore) for url in ts_urls]
        results = await asyncio.gather(*tasks)
        
        total_bytes = 0
        success_count = 0
        segment_times = []
        
        for i, (success, size, seg_time) in enumerate(results):
            if success:
                success_count += 1
                total_bytes += size
                segment_times.append(seg_time)
                self.log_print(f"[{success_count}/{len(ts_urls)}] 片段 {i} 下载完成 ({size/1024:.2f} KB, 用时: {seg_time:.2f}s)")
        
        end_time = time.time()
        end_resource = self.get_resource_usage()
        elapsed_time = end_time - start_time
        
        return {
            'total_bytes': total_bytes,
            'elapsed_time': elapsed_time,
            'success_count': success_count,
            'total_count': len(ts_urls),
            'avg_speed': total_bytes / elapsed_time / 1024 if elapsed_time > 0 else 0,
            'avg_time_per_segment': elapsed_time / len(ts_urls),
            'max_workers': max_workers,
            'segment_times': segment_times,
            'min_segment_time': min(segment_times) if segment_times else 0,
            'max_segment_time': max(segment_times) if segment_times else 0,
            'cpu_percent': (start_resource['cpu_percent'] + end_resource['cpu_percent']) / 2,
            'memory_mb': end_resource['memory_mb'],
            'method': f'协程({max_workers})',
            'workers': max_workers,
        }
    
    def coroutine_download(self, ts_urls: list[str], max_workers: int) -> dict:
        """协程下载测试（同步接口）"""
        return asyncio.run(self.coroutine_download_async(ts_urls, max_workers))
    
    def run_benchmark(self, target_duration: float = 300.0, worker_counts: Optional[list[int]] = None):
        """运行性能基准测试"""
        if worker_counts is None:
            worker_counts = [5, 10, 20]
        
        self.start_logging()
        
        self.log_print("=" * 60)
        self.log_print("视频下载性能基准测试")
        self.log_print("对比多进程和协程的性能差异")
        self.log_print("=" * 60)
        
        # 1. 获取m3u8地址
        m3u8_url = self.get_m3u8_url_from_page()
        
        # 2. 获取并解析m3u8文件
        m3u8_content = self.fetch_m3u8_content(m3u8_url)
        ts_urls, segment_duration = self.parse_m3u8(m3u8_content, m3u8_url)
        
        if not ts_urls:
            raise ValueError("未能从m3u8文件中提取到任何ts片段")
        
        self.log_print(f"\n共找到 {len(ts_urls)} 个视频片段")
        self.log_print(f"每个片段时长: {segment_duration:.2f}秒")
        self.log_print(f"目标时长: {target_duration:.2f}秒 (约{target_duration/60:.1f}分钟)")
        
        # 3. 计算需要下载的片段
        if segment_duration <= 0:
            segment_duration = 5.0
        segments_needed = int(target_duration / segment_duration)
        segments_needed = min(segments_needed, len(ts_urls))
        ts_urls_to_download = ts_urls[:segments_needed]
        
        self.log_print(f"需要下载 {segments_needed} 个片段")
        
        # 4. 运行不同方法的测试
        results = []
        
        # 单进程测试
        self.log_print(f"\n{'='*60}")
        self.log_print("开始单进程测试...")
        result = self.single_process_download(ts_urls_to_download)
        results.append(result)
        
        # 多进程测试
        for worker_count in worker_counts:
            self.log_print(f"\n{'='*60}")
            self.log_print(f"开始多进程测试 ({worker_count} 个进程)...")
            result = self.multi_process_download(ts_urls_to_download, worker_count)
            results.append(result)
        
        # 协程测试
        for worker_count in worker_counts:
            self.log_print(f"\n{'='*60}")
            self.log_print(f"开始协程测试 ({worker_count} 个协程)...")
            result = self.coroutine_download(ts_urls_to_download, worker_count)
            results.append(result)
        
        # 5. 输出对比结果
        self.print_comparison(results)
        
        self.stop_logging()
        self.log_print(f"\n完整日志已保存到: {self.log_path}")
        
    def print_comparison(self, results: list[dict]):
        """打印性能对比结果"""
        self.log_print(f"\n{'='*60}")
        self.log_print("性能对比结果")
        self.log_print(f"{'='*60}")
        
        # 表头
        self.log_print(f"\n{'方法':<15} {'总耗时(秒)':<12} {'速度(KB/s)':<15} {'加速比':<10} {'CPU(%)':<10} {'内存(MB)':<10}")
        self.log_print("-" * 80)
        
        baseline_time = results[0]['elapsed_time']
        
        for result in results:
            elapsed_time = result['elapsed_time']
            avg_speed = result['avg_speed']
            speedup = baseline_time / elapsed_time if elapsed_time > 0 else 0
            cpu_percent = result['cpu_percent']
            memory_mb = result['memory_mb']
            method = result['method']
            
            self.log_print(f"{method:<15} {elapsed_time:<12.2f} {avg_speed:<15.2f} {speedup:<10.2f}x {cpu_percent:<10.1f} {memory_mb:<10.1f}")
        
        self.log_print(f"\n{'='*60}")
        self.log_print("详细统计")
        self.log_print(f"{'='*60}")
        
        for result in results:
            method = result['method']
            self.log_print(f"\n{method}:")
            self.log_print(f"  成功下载: {result['success_count']}/{result['total_count']} 个片段")
            self.log_print(f"  总下载量: {result['total_bytes']/1024/1024:.2f} MB")
            self.log_print(f"  总耗时: {result['elapsed_time']:.2f} 秒")
            self.log_print(f"  平均速度: {result['avg_speed']:.2f} KB/s ({result['avg_speed']/1024:.2f} MB/s)")
            self.log_print(f"  平均每个片段耗时: {result['avg_time_per_segment']:.2f} 秒")
            self.log_print(f"  片段下载用时范围: {result['min_segment_time']:.2f}s ~ {result['max_segment_time']:.2f}s")
            self.log_print(f"  CPU使用率: {result['cpu_percent']:.1f}%")
            self.log_print(f"  内存占用: {result['memory_mb']:.1f} MB")
            
            if result != results[0]:
                speedup = results[0]['elapsed_time'] / result['elapsed_time']
                self.log_print(f"  相比单进程加速: {speedup:.2f}x")
        
        self.log_print(f"\n{'='*60}")
        self.log_print("结论:")
        self.log_print(f"{'='*60}")
        
        # 找出最佳多进程和协程结果
        multi_process_results = [r for r in results if '多进程' in r['method']]
        coroutine_results = [r for r in results if '协程' in r['method']]
        
        if multi_process_results:
            best_mp = max(multi_process_results, key=lambda x: results[0]['elapsed_time'] / x['elapsed_time'])
            mp_speedup = results[0]['elapsed_time'] / best_mp['elapsed_time']
            self.log_print(f"1. 最佳多进程: {best_mp['workers']} 个进程, 加速比 {mp_speedup:.2f}x")
        
        if coroutine_results:
            best_coro = max(coroutine_results, key=lambda x: results[0]['elapsed_time'] / x['elapsed_time'])
            coro_speedup = results[0]['elapsed_time'] / best_coro['elapsed_time']
            self.log_print(f"2. 最佳协程: {best_coro['workers']} 个协程, 加速比 {coro_speedup:.2f}x")
        
        if multi_process_results and coroutine_results:
            best_mp = max(multi_process_results, key=lambda x: results[0]['elapsed_time'] / x['elapsed_time'])
            best_coro = max(coroutine_results, key=lambda x: results[0]['elapsed_time'] / x['elapsed_time'])
            
            self.log_print(f"3. 多进程 vs 协程:")
            self.log_print(f"   - 多进程内存占用: {best_mp['memory_mb']:.1f} MB")
            self.log_print(f"   - 协程内存占用: {best_coro['memory_mb']:.1f} MB")
            self.log_print(f"   - 内存节省: {(1 - best_coro['memory_mb']/best_mp['memory_mb'])*100:.1f}%")
            self.log_print(f"   - 多进程CPU使用: {best_mp['cpu_percent']:.1f}%")
            self.log_print(f"   - 协程CPU使用: {best_coro['cpu_percent']:.1f}%")
        
        self.log_print(f"4. 多进程适合CPU密集型任务，协程适合IO密集型任务")
        self.log_print(f"5. 对于网络下载，协程资源占用更低，性能相当")


def main():
    # Bpfun视频页面URL
    page_url = "https://m.bpfun.com/play/31226-0-0.html"
    
    # 创建性能测试实例
    benchmark = PerformanceBenchmark(
        page_url=page_url,
        output_dir=r"D:\项目\crawler\py-playwright\video-crawling\output"
    )
    
    # 测试不同的并发数: 5, 10, 20
    worker_counts = [5, 10, 20]
    
    # 运行基准测试: 下载前5分钟(300秒)
    print("\n" + "=" * 60)
    print("测试场景: 5分钟视频")
    print("对比单进程、多进程、协程的性能")
    print("=" * 60)
    benchmark.run_benchmark(
        target_duration=300.0,
        worker_counts=worker_counts
    )


if __name__ == "__main__":
    main()
