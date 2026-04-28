"""
多进程爬取bpfun视频
使用requests获取m3u8地址，多进程下载ts片段
"""

import time
import requests
import multiprocessing
from multiprocessing import Pool
from urllib.parse import urljoin
from pathlib import Path
import re


class BpfunVideoCrawler:
    def __init__(self, page_url: str, output_dir: str = r"D:\项目\crawler\py-playwright\video-crawling\output\bpfun1", max_workers: int = 10):
        """
        初始化视频爬虫
        
        Args:
            page_url: 视频页面URL
            output_dir: 输出目录
            max_workers: 最大进程数
        """
        self.page_url = page_url
        self.output_dir = Path(output_dir)
        self.max_workers = max_workers
        self.ts_dir = self.output_dir / "ts_files"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36 Edg/147.0.0.0',
            'Accept': '*/*',
            'Accept-Encoding': 'identity;q=1, *;q=0',
            'Accept-Language': 'zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7,en-GB;q=0.6',
            'Cache-Control': 'no-cache',
            'Origin': 'https://m.bpfun.com',
            'Referer': 'https://m.bpfun.com/',
            'sec-ch-ua': '"Microsoft Edge";v="147", "Not.A/Brand";v="8", "Chromium";v="147"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'video',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'cross-site',
        }
        
    def create_directories(self):
        """创建必要的目录"""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.ts_dir.mkdir(parents=True, exist_ok=True)
        
    def get_m3u8_url_from_page(self) -> str:
        """
        从页面源码中提取m3u8地址
        
        Returns:
            m3u8播放列表URL
        """
        print(f"正在获取页面: {self.page_url}")
        
        page_headers = {
            'User-Agent': self.headers['User-Agent'],
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': self.headers['Accept-Language'],
        }
        
        response = requests.get(self.page_url, headers=page_headers, timeout=30)
        response.raise_for_status()
        
        html_content = response.text
        
        # 尝试多种正则模式匹配m3u8地址
        patterns = [
            r'https?://[^\s\'"<>]+\.m3u8[^\s\'"<>]*',
            r'"url"\s*:\s*"(https?://[^"]+\.m3u8[^"]*)"',
            r'videoUrl\s*=\s*["\'](https?://[^"\']+\.m3u8[^"\']*)["\']',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, html_content)
            if matches:
                m3u8_url = matches[0]
                # 清理URL中的转义字符
                m3u8_url = m3u8_url.replace('\\/', '/')
                print(f"找到m3u8地址: {m3u8_url}")
                return m3u8_url
        
        raise ValueError("未能从页面中提取到m3u8地址")
    
    def fetch_m3u8_content(self, m3u8_url: str) -> str:
        """获取m3u8文件内容"""
        print(f"正在获取m3u8文件: {m3u8_url}")
        response = requests.get(m3u8_url, headers=self.headers, timeout=30)
        response.raise_for_status()
        return response.text
    
    def parse_m3u8(self, m3u8_content: str, m3u8_url: str) -> tuple[list[str], float]:
        """
        解析m3u8文件，提取ts片段URL和每个片段的时长
        支持主m3u8和子m3u8的解析
        
        Args:
            m3u8_content: m3u8文件内容
            m3u8_url: m3u8文件URL
            
        Returns:
            (ts_urls, segment_duration): ts片段URL列表和每个片段的时长(秒)
        """
        lines = m3u8_content.strip().split('\n')
        ts_urls = []
        segment_duration = 0.0
        has_ts = False
        
        # 检查是否包含ts片段
        for line in lines:
            if not line.startswith('#') and line.strip() and '.ts' in line:
                has_ts = True
                break
        
        if has_ts:
            # 直接包含ts片段
            # 解析EXT-X-TARGETDURATION获取目标时长
            for line in lines:
                if line.startswith('#EXT-X-TARGETDURATION:'):
                    segment_duration = float(line.split(':')[1])
                    break
            
            # 解析ts片段
            for line in lines:
                if not line.startswith('#') and line.strip() and '.ts' in line:
                    ts_url = urljoin(m3u8_url, line.strip())
                    ts_urls.append(ts_url)
        else:
            # 主m3u8，需要获取子m3u8
            print("检测到主m3u8文件，正在获取子m3u8...")
            for line in lines:
                if not line.startswith('#') and line.strip():
                    sub_m3u8_url = urljoin(m3u8_url, line.strip())
                    print(f"子m3u8地址: {sub_m3u8_url}")
                    
                    # 获取子m3u8内容
                    sub_content = self.fetch_m3u8_content(sub_m3u8_url)
                    # 递归解析子m3u8
                    ts_urls, segment_duration = self.parse_m3u8(sub_content, sub_m3u8_url)
                    break
                
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
    
    @staticmethod
    def download_ts_segment_worker(args):
        """
        下载单个ts片段的工作函数（用于多进程）
        
        Args:
            args: (ts_url, index, ts_dir, headers) 元组
            
        Returns:
            (index, success, file_size) 元组
        """
        ts_url, index, ts_dir, headers = args
        ts_dir = Path(ts_dir)
        
        try:
            output_file = ts_dir / f"segment_{index:04d}.ts"
            
            # 如果文件已存在且大小大于0，跳过下载
            if output_file.exists() and output_file.stat().st_size > 0:
                file_size = output_file.stat().st_size
                return (index, True, file_size)
            
            response = requests.get(ts_url, headers=headers, timeout=60, stream=True)
            response.raise_for_status()
            
            downloaded_bytes = 0
            with open(output_file, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded_bytes += len(chunk)
            
            return (index, True, downloaded_bytes)
            
        except Exception as e:
            print(f"片段 {index} 下载失败: {e}")
            return (index, False, 0)
    
    def download_all_segments(self, ts_urls: list[str]) -> bool:
        """
        使用多进程下载所有ts片段
        
        Args:
            ts_urls: ts片段URL列表
            
        Returns:
            是否全部下载成功
        """
        total_count = len(ts_urls)
        print(f"\n开始下载 {total_count} 个视频片段，使用 {self.max_workers} 个进程...")
        
        start_time = time.time()
        
        # 准备参数
        args_list = [
            (url, idx, str(self.ts_dir), self.headers)
            for idx, url in enumerate(ts_urls)
        ]
        
        # 使用进程池下载
        with Pool(processes=self.max_workers) as pool:
            results = pool.map(self.download_ts_segment_worker, args_list)
        
        # 统计结果
        success_count = 0
        total_bytes = 0
        for index, success, file_size in results:
            if success:
                success_count += 1
                total_bytes += file_size
                print(f"[{success_count}/{total_count}] 片段 {index} 下载完成 ({file_size/1024:.2f} KB)")
        
        end_time = time.time()
        elapsed_time = end_time - start_time
        
        # 计算性能指标
        if elapsed_time > 0:
            avg_speed = total_bytes / elapsed_time / 1024  # KB/s
        else:
            avg_speed = 0
        avg_time_per_segment = elapsed_time / total_count if total_count > 0 else 0
        
        print(f"\n下载完成: {success_count}/{total_count} 个片段")
        print(f"\n{'='*60}")
        print("性能指标:")
        print(f"  总下载量: {total_bytes/1024/1024:.2f} MB")
        print(f"  总耗时: {elapsed_time:.2f} 秒")
        print(f"  平均速度: {avg_speed:.2f} KB/s ({avg_speed/1024:.2f} MB/s)")
        print(f"  平均每个片段耗时: {avg_time_per_segment:.2f} 秒")
        print(f"  并发进程数: {self.max_workers}")
        print(f"  理论加速比: ~{self.max_workers}x (相比单进程)")
        print(f"{'='*60}")
        
        return success_count == total_count
    
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
        print("Bpfun视频爬虫 (多进程版)")
        print("=" * 60)
        
        # 1. 创建目录
        self.create_directories()
        
        # 2. 从页面获取m3u8地址
        m3u8_url = self.get_m3u8_url_from_page()
        
        # 3. 获取并解析m3u8文件
        m3u8_content = self.fetch_m3u8_content(m3u8_url)
        ts_urls, segment_duration = self.parse_m3u8(m3u8_content, m3u8_url)
        
        if not ts_urls:
            raise ValueError("未能从m3u8文件中提取到任何ts片段")
        
        print(f"共找到 {len(ts_urls)} 个视频片段")
        
        # 4. 计算需要下载的片段
        ts_urls_to_download = self.calculate_segments_for_duration(
            ts_urls, segment_duration, target_duration
        )
        
        # 5. 多进程下载片段
        if not self.download_all_segments(ts_urls_to_download):
            print("警告: 部分片段下载失败")
        
        # 6. 合并视频
        output_path = self.merge_segments()
        
        print("\n" + "=" * 60)
        print("爬取完成!")
        print(f"输出文件: {output_path}")
        print("=" * 60)


def main():
    # Bpfun视频页面URL
    page_url = "https://m.bpfun.com/play/31226-0-0.html"
    
    # 创建爬虫实例
    crawler = BpfunVideoCrawler(
        page_url=page_url,
        output_dir=r"D:\项目\crawler\py-playwright\video-crawling\output\bpfun1",  # 输出到video-crawling/output/bpfun1目录
        max_workers=10  # 使用10个进程并发下载
    )
    
    # 运行爬虫，只下载前5分钟(300秒)
    crawler.run(target_duration=300.0)


if __name__ == "__main__":
    main()
