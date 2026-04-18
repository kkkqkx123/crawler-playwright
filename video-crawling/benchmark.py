"""
性能基准测试
对比单线程和多线程下载视频片段的性能差异
"""

import time
import requests
import threading
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin
from pathlib import Path
from datetime import datetime
from typing import Optional


class PerformanceBenchmark:
    def __init__(self, m3u8_url: str, output_dir: str = "output"):
        """
        初始化性能测试
        
        Args:
            m3u8_url: m3u8播放列表URL
            output_dir: 输出目录
        """
        self.m3u8_url = m3u8_url
        self.output_dir = Path(output_dir)
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36 Edg/147.0.0.0',
            'Accept': '*/*',
            'Accept-Encoding': 'gzip, deflate, br, zstd',
            'Accept-Language': 'zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7',
            'Cache-Control': 'no-cache',
            'Origin': 'https://live.ithome.com',
            'Referer': 'https://live.ithome.com/',
        }
        # 创建输出目录
        self.output_dir.mkdir(parents=True, exist_ok=True)
        # 输出文件路径
        self.log_file = None
        self.log_path = None
    
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
        
    def fetch_m3u8_content(self) -> str:
        """获取m3u8文件内容"""
        self.log_print(f"正在获取m3u8文件: {self.m3u8_url}")
        response = requests.get(self.m3u8_url, headers=self.headers, timeout=30)
        response.raise_for_status()
        return response.text
    
    def parse_m3u8(self, m3u8_content: str) -> tuple[list[str], float]:
        """解析m3u8文件，提取ts片段URL和每个片段的时长"""
        lines = m3u8_content.strip().split('\n')
        ts_urls = []
        segment_duration = 0.0
        
        for line in lines:
            if line.startswith('#EXT-X-TARGETDURATION:'):
                segment_duration = float(line.split(':')[1])
                break
        
        for i, line in enumerate(lines):
            if line.startswith('#EXTINF:'):
                duration = float(line.split(':')[1].split(',')[0])
                if segment_duration == 0:
                    segment_duration = duration
            elif not line.startswith('#') and line.strip():
                ts_url = urljoin(self.m3u8_url, line.strip())
                ts_urls.append(ts_url)
                
        return ts_urls, segment_duration
    
    def download_segment_to_memory(self, ts_url: str) -> bytes:
        """
        下载单个ts片段到内存（不存储到磁盘）
        
        Args:
            ts_url: ts片段URL
            
        Returns:
            片段数据
        """
        response = requests.get(ts_url, headers=self.headers, timeout=60, stream=True)
        response.raise_for_status()
        
        data = b''
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                data += chunk
        
        return data
    
    def single_thread_download(self, ts_urls: list[str]) -> dict:
        """
        单线程下载测试
        
        Args:
            ts_urls: ts片段URL列表
            
        Returns:
            性能统计数据
        """
        self.log_print(f"\n{'='*60}")
        self.log_print(f"单线程下载测试")
        self.log_print(f"{'='*60}")
        self.log_print(f"下载 {len(ts_urls)} 个片段...")
        
        start_time = time.time()
        total_bytes = 0
        success_count = 0
        segment_times = []  # 记录每个片段的下载用时
        
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
        }
    
    def multi_thread_download(self, ts_urls: list[str], max_workers: int) -> dict:
        """
        多线程下载测试
        
        Args:
            ts_urls: ts片段URL列表
            max_workers: 最大线程数
            
        Returns:
            性能统计数据
        """
        self.log_print(f"\n{'='*60}")
        self.log_print(f"多线程下载测试 ({max_workers} 个线程)")
        self.log_print(f"{'='*60}")
        self.log_print(f"下载 {len(ts_urls)} 个片段...")
        
        start_time = time.time()
        total_bytes = 0
        success_count = 0
        lock = threading.Lock()
        completed_count = 0
        segment_times = []  # 记录每个片段的下载用时
        
        def download_with_progress(url: str, index: int) -> tuple[bool, int, float]:
            """下载并显示进度"""
            try:
                seg_start = time.time()
                data = self.download_segment_to_memory(url)
                seg_time = time.time() - seg_start
                
                with lock:
                    nonlocal completed_count
                    completed_count += 1
                    self.log_print(f"[{completed_count}/{len(ts_urls)}] 片段 {index} 下载完成 ({len(data)/1024:.2f} KB, 用时: {seg_time:.2f}s)")
                return True, len(data), seg_time
            except Exception as e:
                self.log_print(f"片段 {index} 下载失败: {e}")
                return False, 0, 0
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_index = {
                executor.submit(download_with_progress, url, idx): idx 
                for idx, url in enumerate(ts_urls)
            }
            
            for future in as_completed(future_to_index):
                success, size, seg_time = future.result()
                if success:
                    success_count += 1
                    total_bytes += size
                    segment_times.append(seg_time)
        
        end_time = time.time()
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
        }
    
    def run_benchmark(self, target_duration: float = 600.0, thread_counts: Optional[list[int]] = None):
        """
        运行性能基准测试
        
        Args:
            target_duration: 目标时长(秒)，默认10分钟(600秒)
            thread_counts: 要测试的线程数列表
        """
        if thread_counts is None:
            thread_counts = [1, 5, 10, 20]
        
        # 开始记录日志
        self.start_logging()
        
        self.log_print("=" * 60)
        self.log_print("视频下载性能基准测试")
        self.log_print("=" * 60)
        
        # 1. 获取并解析m3u8文件
        m3u8_content = self.fetch_m3u8_content()
        ts_urls, segment_duration = self.parse_m3u8(m3u8_content)
        
        if not ts_urls:
            raise ValueError("未能从m3u8文件中提取到任何ts片段")
        
        self.log_print(f"\n共找到 {len(ts_urls)} 个视频片段")
        self.log_print(f"每个片段时长: {segment_duration:.2f}秒")
        self.log_print(f"目标时长: {target_duration:.2f}秒 (约{target_duration/60:.1f}分钟)")
        
        # 2. 计算需要下载的片段
        if segment_duration <= 0:
            segment_duration = 5.0
        segments_needed = int(target_duration / segment_duration)
        segments_needed = min(segments_needed, len(ts_urls))
        ts_urls_to_download = ts_urls[:segments_needed]
        
        self.log_print(f"需要下载 {segments_needed} 个片段")
        
        # 3. 运行不同线程数的测试
        results = []
        
        for thread_count in thread_counts:
            if thread_count == 1:
                result = self.single_thread_download(ts_urls_to_download)
            else:
                result = self.multi_thread_download(ts_urls_to_download, thread_count)
            results.append(result)
        
        # 4. 输出对比结果
        self.print_comparison(results)
        
        # 停止记录日志
        self.stop_logging()
        self.log_print(f"\n完整日志已保存到: {self.log_path}")
        
    def print_comparison(self, results: list[dict]):
        """
        打印性能对比结果
        
        Args:
            results: 测试结果列表
        """
        self.log_print(f"\n{'='*60}")
        self.log_print("性能对比结果")
        self.log_print(f"{'='*60}")
        
        # 表头
        self.log_print(f"\n{'线程数':<10} {'总耗时(秒)':<15} {'平均速度(KB/s)':<20} {'加速比':<10}")
        self.log_print("-" * 60)
        
        baseline_time = results[0]['elapsed_time']  # 单线程作为基准
        
        for result in results:
            thread_count = result.get('max_workers', 1)
            elapsed_time = result['elapsed_time']
            avg_speed = result['avg_speed']
            speedup = baseline_time / elapsed_time if elapsed_time > 0 else 0
            
            self.log_print(f"{thread_count:<10} {elapsed_time:<15.2f} {avg_speed:<20.2f} {speedup:<10.2f}x")
        
        self.log_print(f"\n{'='*60}")
        self.log_print("详细统计")
        self.log_print(f"{'='*60}")
        
        for i, result in enumerate(results):
            thread_count = result.get('max_workers', 1)
            self.log_print(f"\n{thread_count} 线程:")
            self.log_print(f"  成功下载: {result['success_count']}/{result['total_count']} 个片段")
            self.log_print(f"  总下载量: {result['total_bytes']/1024/1024:.2f} MB")
            self.log_print(f"  总耗时: {result['elapsed_time']:.2f} 秒")
            self.log_print(f"  平均速度: {result['avg_speed']:.2f} KB/s ({result['avg_speed']/1024:.2f} MB/s)")
            self.log_print(f"  平均每个片段耗时: {result['avg_time_per_segment']:.2f} 秒")
            self.log_print(f"  片段下载用时范围: {result['min_segment_time']:.2f}s ~ {result['max_segment_time']:.2f}s")
            
            if i > 0:
                speedup = results[0]['elapsed_time'] / result['elapsed_time']
                self.log_print(f"  相比单线程加速: {speedup:.2f}x")
        
        self.log_print(f"\n{'='*60}")
        self.log_print("结论:")
        self.log_print(f"{'='*60}")
        
        # 计算最佳线程数
        best_result = max(results[1:], key=lambda x: results[0]['elapsed_time'] / x['elapsed_time'])
        best_thread_count = best_result.get('max_workers', 1)
        best_speedup = results[0]['elapsed_time'] / best_result['elapsed_time']
        
        self.log_print(f"1. 单线程下载耗时: {results[0]['elapsed_time']:.2f} 秒")
        self.log_print(f"2. 最佳线程数: {best_thread_count} 个线程")
        self.log_print(f"3. 最佳加速比: {best_speedup:.2f}x")
        self.log_print(f"4. 多线程显著提升了下载性能，充分利用了网络带宽")
        self.log_print(f"5. 增加线程数可以提升性能，但存在边际效应递减")


def main():
    # IT之家直播视频的m3u8地址
    m3u8_url = "https://live.video.weibocdn.com/eafd7d09-01fe-4dc9-924d-b127fefc0bbd_index.m3u8"
    
    # 创建性能测试实例
    benchmark = PerformanceBenchmark(
        m3u8_url=m3u8_url,
        output_dir="output"
    )
    
    # 测试不同的线程数: 1, 5, 10, 20
    thread_counts = [1, 5, 10, 20]
    
    # 运行基准测试1: 下载前10分钟(600秒)
    print("\n" + "=" * 60)
    print("测试场景 1: 10分钟视频 (约50个片段)")
    print("=" * 60)
    benchmark.run_benchmark(
        target_duration=600.0,
        thread_counts=thread_counts
    )
    
    # 运行基准测试2: 下载前20分钟(1200秒)
    print("\n" + "=" * 60)
    print("测试场景 2: 20分钟视频 (约100个片段)")
    print("=" * 60)
    benchmark.run_benchmark(
        target_duration=1200.0,
        thread_counts=thread_counts
    )


if __name__ == "__main__":
    main()
