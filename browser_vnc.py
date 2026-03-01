"""
================================================================================
浏览器 VNC 服务模块
通过 VNC 协议将浏览器画面传输到前端
================================================================================

【功能说明】
1. 启动 VNC 服务器
2. 在 VNC 会话中启动浏览器
3. 通过 WebSocket 将 VNC 画面传输到前端

【依赖安装】
pip install websockify pyvnc
================================================================================
"""

import asyncio
import subprocess
import os
import signal
from typing import Optional
from pathlib import Path


class BrowserVNCService:
    """
    浏览器 VNC 服务
    
    管理 VNC 服务器和浏览器实例
    """
    
    def __init__(self, vnc_port: int = 5900, websocket_port: int = 6080):
        self.vnc_port = vnc_port
        self.websocket_port = websocket_port
        self.vnc_process: Optional[subprocess.Popen] = None
        self.browser_process: Optional[subprocess.Popen] = None
        self.websockify_process: Optional[subprocess.Popen] = None
        self.display_num = 99
        
    async def start(self) -> bool:
        """
        启动 VNC 服务和浏览器
        
        Returns:
            bool: 是否启动成功
        """
        try:
            # 1. 启动 Xvfb（虚拟显示）
            xvfb_cmd = [
                'Xvfb',
                f':{self.display_num}',
                '-screen', '0', '1280x720x24',
                '-ac',
                '+extension', 'RANDR'
            ]
            
            # 检查 Xvfb 是否已存在
            try:
                subprocess.run(['pgrep', '-f', f'Xvfb :{self.display_num}'], 
                             check=True, capture_output=True)
                print(f"Xvfb :{self.display_num} already running")
            except subprocess.CalledProcessError:
                self.xvfb_process = subprocess.Popen(
                    xvfb_cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                await asyncio.sleep(1)
                print(f"Xvfb started on display :{self.display_num}")
            
            # 2. 启动 VNC 服务器
            vnc_cmd = [
                'x11vnc',
                '-display', f':{self.display_num}',
                '-rfbport', str(self.vnc_port),
                '-forever',
                '-shared',
                '-nopw',  # 无密码（仅开发环境）
                '-noxdamage',
                '-noxfixes',
                '-noxrecord',
                '-xkb'
            ]
            
            self.vnc_process = subprocess.Popen(
                vnc_cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            await asyncio.sleep(1)
            print(f"VNC server started on port {self.vnc_port}")
            
            # 3. 启动 websockify（WebSocket 代理）
            websockify_cmd = [
                'python', '-m', 'websockify',
                str(self.websocket_port),
                f'localhost:{self.vnc_port}'
            ]
            
            self.websockify_process = subprocess.Popen(
                websockify_cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            await asyncio.sleep(1)
            print(f"WebSocket proxy started on port {self.websocket_port}")
            
            # 4. 在 VNC 会话中启动 Chrome 浏览器
            env = os.environ.copy()
            env['DISPLAY'] = f':{self.display_num}'
            
            chrome_cmd = [
                'google-chrome',
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-accelerated-2d-canvas',
                '--no-first-run',
                '--no-zygote',
                '--single-process',
                '--disable-gpu',
                '--window-size=1280,720',
                '--window-position=0,0',
                '--app=https://www.google.com'
            ]
            
            # 尝试查找 Chrome
            chrome_paths = [
                'google-chrome',
                'google-chrome-stable',
                'chromium',
                'chromium-browser',
                r'C:\Program Files\Google\Chrome\Application\chrome.exe',
                r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
            ]
            
            chrome_found = False
            for chrome_path in chrome_paths:
                try:
                    subprocess.run([chrome_path, '--version'], 
                                 capture_output=True, check=True)
                    chrome_cmd[0] = chrome_path
                    chrome_found = True
                    break
                except (subprocess.CalledProcessError, FileNotFoundError):
                    continue
            
            if not chrome_found:
                print("Chrome not found, trying default")
                chrome_cmd[0] = 'chrome'
            
            self.browser_process = subprocess.Popen(
                chrome_cmd,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            await asyncio.sleep(2)
            print(f"Chrome browser started in VNC session")
            
            return True
            
        except Exception as e:
            print(f"Failed to start VNC service: {e}")
            await self.stop()
            return False
    
    async def stop(self):
        """停止所有服务"""
        # 停止浏览器
        if self.browser_process:
            try:
                self.browser_process.terminate()
                self.browser_process.wait(timeout=5)
            except:
                self.browser_process.kill()
            self.browser_process = None
            print("Browser stopped")
        
        # 停止 websockify
        if self.websockify_process:
            try:
                self.websockify_process.terminate()
                self.websockify_process.wait(timeout=5)
            except:
                self.websockify_process.kill()
            self.websockify_process = None
            print("WebSocket proxy stopped")
        
        # 停止 VNC
        if self.vnc_process:
            try:
                self.vnc_process.terminate()
                self.vnc_process.wait(timeout=5)
            except:
                self.vnc_process.kill()
            self.vnc_process = None
            print("VNC server stopped")
    
    def get_websocket_url(self) -> str:
        """获取 WebSocket URL"""
        return f"ws://localhost:{self.websocket_port}"
    
    async def navigate(self, url: str):
        """导航到指定 URL"""
        if self.browser_process:
            # 使用 xdotool 发送按键
            env = os.environ.copy()
            env['DISPLAY'] = f':{self.display_num}'
            
            # 点击地址栏 (Ctrl+L)
            subprocess.run(
                ['xdotool', 'key', 'ctrl+l'],
                env=env,
                capture_output=True
            )
            
            # 输入 URL
            subprocess.run(
                ['xdotool', 'type', url],
                env=env,
                capture_output=True
            )
            
            # 按回车
            subprocess.run(
                ['xdotool', 'key', 'Return'],
                env=env,
                capture_output=True
            )
    
    async def click(self, x: int, y: int):
        """在指定位置点击"""
        env = os.environ.copy()
        env['DISPLAY'] = f':{self.display_num}'
        subprocess.run(
            ['xdotool', 'mousemove', str(x), str(y), 'click', '1'],
            env=env,
            capture_output=True
        )
    
    async def type_text(self, text: str):
        """输入文本"""
        env = os.environ.copy()
        env['DISPLAY'] = f':{self.display_num}'
        subprocess.run(
            ['xdotool', 'type', text],
            env=env,
            capture_output=True
        )


# 全局实例
browser_vnc = BrowserVNCService()


if __name__ == "__main__":
    # 测试
    async def test():
        service = BrowserVNCService()
        success = await service.start()
        if success:
            print(f"\nVNC WebSocket URL: {service.get_websocket_url()}")
            print("Press Ctrl+C to stop")
            try:
                while True:
                    await asyncio.sleep(1)
            except KeyboardInterrupt:
                pass
        await service.stop()
    
    asyncio.run(test())
