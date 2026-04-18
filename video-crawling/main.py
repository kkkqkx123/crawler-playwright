"""
多线程爬取IT之家直播视频
使用HLS流媒体协议下载m3u8视频片段
"""

import time
import requests
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin
from pathlib import Path


class VideoCrawler:
    def __init__(self, m3u8_url: str, output_dir: str = "output", max_workers: int = 10):
        """
        初始化视频爬虫
        
        Args:
            m3u8_url: m3u8播放列表URL
            output_dir: 输出目录
            max_workers: 最大线程数
        """
        self.m3u8_url = m3u8_url
        self.output_dir = Path(output_dir)
        self.max_workers = max_workers
        self.ts_dir = self.output_dir / "ts_files"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36 Edg/147.0.0.0',
            'Accept': '*/*',
            'Accept-Encoding': 'gzip, deflate, br, zstd',
            'Accept-Language': 'zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7',
            'Cache-Control': 'no-cache',
            'Origin': 'https://live.ithome.com',
            'Referer': 'https://live.ithome.com/',
        }
        self.lock = threading.Lock()
        self.downloaded_count = 0
        self.total_count = 0
        self.total_bytes = 0  # 总下载字节数
        self.start_time = 0  # 开始时间
        self.end_time = 0  # 结束时间
        
    def create_directories(self):
        """创建必要的目录"""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.ts_dir.mkdir(parents=True, exist_ok=True)
        
    def fetch_m3u8_content(self) -> str:
        """获取m3u8文件内容"""
        print(f"正在获取m3u8文件: {self.m3u8_url}")
        response = requests.get(self.m3u8_url, headers=self.headers, timeout=30)
        response.raise_for_status()
        return response.text
    
    def parse_m3u8(self, m3u8_content: str) -> tuple[list[str], float]:
        """
        解析m3u8文件，提取ts片段URL和每个片段的时长
        
        Args:
            m3u8_content: m3u8文件内容
            
        Returns:
            (ts_urls, segment_duration): ts片段URL列表和每个片段的时长(秒)
        """
        lines = m3u8_content.strip().split('\n')
        ts_urls = []
        segment_duration = 0.0
        
        # 解析EXT-X-TARGETDURATION获取目标时长
        for line in lines:
            if line.startswith('#EXT-X-TARGETDURATION:'):
                segment_duration = float(line.split(':')[1])
                break
        
        # 解析ts片段
        for i, line in enumerate(lines):
            if line.startswith('#EXTINF:'):
                # 获取实际片段时长
                duration = float(line.split(':')[1].split(',')[0])
                if segment_duration == 0:
                    segment_duration = duration
            elif not line.startswith('#') and line.strip():
                # 这是ts片段URL
                ts_url = urljoin(self.m3u8_url, line.strip())
                ts_urls.append(ts_url)
                
        return ts_urls, segment_duration
    
    def calculate_segments_for_duration(self, ts_urls: list[str], segment_duration: float, 
                                       target_duration: float = 300.0) -> list[str]:
        """
        计算需要下载的片段数量以达到目标时长
        
        Args:
            ts_urls: 所有ts片段URL
            segment_duration: 每个片段的时长(秒)
            target_duration: 目标时长(秒)，默认5分钟(300秒)
            
        Returns:
            需要下载的ts片段URL列表
        """
        if segment_duration <= 0:
            segment_duration = 5.0  # 默认假设每个片段5秒
            
        segments_needed = int(target_duration / segment_duration)
        segments_needed = min(segments_needed, len(ts_urls))
        
        print(f"每个片段时长: {segment_duration:.2f}秒")
        print(f"目标时长: {target_duration:.2f}秒 (约{target_duration/60:.1f}分钟)")
        print(f"需要下载 {segments_needed} 个片段 (共{len(ts_urls)}个片段)")
        
        return ts_urls[:segments_needed]
    
    def download_ts_segment(self, ts_url: str, index: int) -> bool:
        """
        下载单个ts片段
        
        Args:
            ts_url: ts片段URL
            index: 片段索引
            
        Returns:
            是否下载成功
        """
        try:
            output_file = self.ts_dir / f"segment_{index:04d}.ts"
            
            # 如果文件已存在且大小大于0，跳过下载
            if output_file.exists() and output_file.stat().st_size > 0:
                file_size = output_file.stat().st_size
                with self.lock:
                    self.downloaded_count += 1
                    self.total_bytes += file_size
                    print(f"[{self.downloaded_count}/{self.total_count}] 片段 {index} 已存在，跳过")
                return True
            
            response = requests.get(ts_url, headers=self.headers, timeout=60, stream=True)
            response.raise_for_status()
            
            downloaded_bytes = 0
            with open(output_file, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded_bytes += len(chunk)
            
            with self.lock:
                self.downloaded_count += 1
                self.total_bytes += downloaded_bytes
                print(f"[{self.downloaded_count}/{self.total_count}] 片段 {index} 下载完成 ({downloaded_bytes/1024:.2f} KB)")
            
            return True
            
        except Exception as e:
            print(f"片段 {index} 下载失败: {e}")
            return False
    
    def download_all_segments(self, ts_urls: list[str]) -> bool:
        """
        使用多线程下载所有ts片段
        
        Args:
            ts_urls: ts片段URL列表
            
        Returns:
            是否全部下载成功
        """
        self.total_count = len(ts_urls)
        self.downloaded_count = 0
        self.total_bytes = 0
        self.start_time = time.time()
        
        print(f"\n开始下载 {self.total_count} 个视频片段，使用 {self.max_workers} 个线程...")
        
        success_count = 0
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # 提交所有下载任务
            future_to_index = {
                executor.submit(self.download_ts_segment, url, idx): idx 
                for idx, url in enumerate(ts_urls)
            }
            
            # 等待所有任务完成
            for future in as_completed(future_to_index):
                if future.result():
                    success_count += 1
        
        self.end_time = time.time()
        elapsed_time = self.end_time - self.start_time
        
        # 计算性能指标
        avg_speed = self.total_bytes / elapsed_time / 1024  # KB/s
        avg_time_per_segment = elapsed_time / self.total_count
        
        print(f"\n下载完成: {success_count}/{self.total_count} 个片段")
        print(f"\n{'='*60}")
        print("性能指标:")
        print(f"  总下载量: {self.total_bytes/1024/1024:.2f} MB")
        print(f"  总耗时: {elapsed_time:.2f} 秒")
        print(f"  平均速度: {avg_speed:.2f} KB/s ({avg_speed/1024:.2f} MB/s)")
        print(f"  平均每个片段耗时: {avg_time_per_segment:.2f} 秒")
        print(f"  并发线程数: {self.max_workers}")
        print(f"  理论加速比: ~{self.max_workers}x (相比单线程)")
        print(f"{'='*60}")
        
        return success_count == self.total_count
    
    def merge_segments(self, output_filename: str = "output.mp4") -> str:
        """
        合并所有ts片段为一个视频文件
        
        Args:
            output_filename: 输出文件名
            
        Returns:
            输出文件路径
        """
        output_path = self.output_dir / output_filename
        
        print(f"\n正在合并视频片段...")
        
        # 获取所有ts文件并按顺序排序
        ts_files = sorted(self.ts_dir.glob("segment_*.ts"))
        
        if not ts_files:
            raise ValueError("没有找到任何ts片段文件")
        
        # 使用二进制方式合并文件
        with open(output_path, 'wb') as outfile:
            for i, ts_file in enumerate(ts_files, 1):
                with open(ts_file, 'rb') as infile:
                    outfile.write(infile.read())
                print(f"已合并 {i}/{len(ts_files)} 个片段")
        
        print(f"\n视频合并完成: {output_path}")
        print(f"文件大小: {output_path.stat().st_size / 1024 / 1024:.2f} MB")
        
        return str(output_path)
    
    def run(self, target_duration: float = 300.0):
        """
        运行爬虫
        
        Args:
            target_duration: 目标时长(秒)，默认5分钟(300秒)
        """
        print("=" * 60)
        print("IT之家直播视频爬虫")
        print("=" * 60)
        
        # 1. 创建目录
        self.create_directories()
        
        # 2. 获取并解析m3u8文件
        m3u8_content = self.fetch_m3u8_content()
        ts_urls, segment_duration = self.parse_m3u8(m3u8_content)
        
        if not ts_urls:
            raise ValueError("未能从m3u8文件中提取到任何ts片段")
        
        print(f"共找到 {len(ts_urls)} 个视频片段")
        
        # 3. 计算需要下载的片段
        ts_urls_to_download = self.calculate_segments_for_duration(
            ts_urls, segment_duration, target_duration
        )
        
        # 4. 多线程下载片段
        if not self.download_all_segments(ts_urls_to_download):
            print("警告: 部分片段下载失败")
        
        # 5. 合并视频
        output_path = self.merge_segments()
        
        print("\n" + "=" * 60)
        print("爬取完成!")
        print(f"输出文件: {output_path}")
        print("=" * 60)


def main():
    # IT之家直播视频的m3u8地址
    m3u8_url = "https://live.video.weibocdn.com/eafd7d09-01fe-4dc9-924d-b127fefc0bbd_index.m3u8"
    
    # 创建爬虫实例
    crawler = VideoCrawler(
        m3u8_url=m3u8_url,
        output_dir="output/m9",  # 输出到output/m9目录
        max_workers=10  # 使用10个线程并发下载
    )
    
    # 运行爬虫，只下载前5分钟(300秒)
    crawler.run(target_duration=300.0)


if __name__ == "__main__":
    main()
