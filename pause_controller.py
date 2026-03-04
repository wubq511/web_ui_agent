"""
================================================================================
暂停控制器模块 - 实现Agent的暂停/继续功能
================================================================================

【模块概述】
通过文件系统实现进程间通信（IPC），让Web服务器能够控制Agent子进程的暂停状态。

【设计思路】
1. 使用JSON文件存储暂停状态，实现进程间通信
2. 后端API写入状态文件，Agent子进程读取状态文件
3. Agent在每个步骤开始时检查状态，如果暂停则阻塞等待
4. 支持超时自动恢复，防止永久阻塞

【使用示例】
```python
# 在后端API中
from pause_controller import PauseController
controller = PauseController()
controller.pause()  # 暂停
controller.resume() # 继续

# 在Agent中
from pause_controller import PauseController
controller = PauseController()
controller.check_and_wait()  # 检查并等待
```
================================================================================
"""

import os
import json
import time
from pathlib import Path
from typing import Optional
from datetime import datetime


class PauseController:
    """
    暂停控制器 - 管理Agent的暂停状态
    
    【工作原理】
    1. 使用JSON文件存储状态，文件路径固定
    2. 后端通过 pause()/resume() 方法修改状态
    3. Agent通过 check_and_wait() 方法检查状态并等待
    4. 状态文件包含：是否暂停、暂停时间戳、超时设置
    """
    
    # 状态文件路径（固定位置，确保进程间可访问）
    STATE_FILE = Path(__file__).parent / ".pause_state.json"
    
    # 默认超时时间（秒）- 防止永久阻塞
    DEFAULT_TIMEOUT = 3600  # 1小时
    
    # 检查间隔（秒）- 轮询频率
    CHECK_INTERVAL = 0.5
    
    def __init__(self):
        """初始化暂停控制器"""
        # 确保状态文件存在
        self._ensure_state_file()
    
    def _ensure_state_file(self):
        """确保状态文件存在，不存在则创建"""
        if not self.STATE_FILE.exists():
            self._write_state(is_paused=False, timestamp=time.time())
    
    def _read_state(self) -> dict:
        """
        读取状态文件
        
        Returns:
            dict: 状态字典，包含 is_paused, timestamp, timeout
        """
        try:
            with open(self.STATE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            # 文件不存在或损坏，返回默认状态
            return {
                "is_paused": False,
                "timestamp": time.time(),
                "timeout": self.DEFAULT_TIMEOUT
            }
    
    def _write_state(self, is_paused: bool, timestamp: float, timeout: float = None):
        """
        写入状态文件
        
        Args:
            is_paused: 是否暂停
            timestamp: 时间戳
            timeout: 超时时间（可选）
        """
        state = {
            "is_paused": is_paused,
            "timestamp": timestamp,
            "timeout": timeout or self.DEFAULT_TIMEOUT,
            "updated_at": datetime.now().isoformat()
        }
        
        # 使用原子写入，避免读写冲突
        temp_file = self.STATE_FILE.with_suffix('.tmp')
        try:
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(state, f, indent=2)
            
            # 原子替换
            temp_file.replace(self.STATE_FILE)
        except Exception as e:
            # 清理临时文件
            if temp_file.exists():
                try:
                    temp_file.unlink()
                except:
                    pass
            raise e
    
    def is_paused(self) -> bool:
        """
        检查是否处于暂停状态
        
        Returns:
            bool: True表示暂停中，False表示运行中
        """
        state = self._read_state()
        return state.get("is_paused", False)
    
    def pause(self) -> bool:
        """
        暂停Agent执行
        
        Returns:
            bool: 操作是否成功
        """
        try:
            self._write_state(is_paused=True, timestamp=time.time())
            print(f"[PauseController] Agent已暂停 - {datetime.now().strftime('%H:%M:%S')}")
            return True
        except Exception as e:
            print(f"[PauseController] 暂停失败: {e}")
            return False
    
    def resume(self) -> bool:
        """
        继续Agent执行
        
        Returns:
            bool: 操作是否成功
        """
        try:
            self._write_state(is_paused=False, timestamp=time.time())
            print(f"[PauseController] Agent已继续 - {datetime.now().strftime('%H:%M:%S')}")
            return True
        except Exception as e:
            print(f"[PauseController] 继续失败: {e}")
            return False
    
    def check_and_wait(self, context: str = "") -> bool:
        """
        检查暂停状态，如果暂停则阻塞等待
        
        【设计思路】
        1. 检查状态文件，判断是否暂停
        2. 如果暂停，进入等待循环
        3. 定期检查状态更新
        4. 支持超时自动恢复
        
        Args:
            context: 上下文信息（用于日志）
            
        Returns:
            bool: True表示正常继续，False表示超时或出错
        """
        state = self._read_state()
        
        if not state.get("is_paused", False):
            # 未暂停，直接返回
            return True
        
        # 记录暂停开始时间
        pause_start = time.time()
        pause_timestamp = state.get("timestamp", pause_start)
        timeout = state.get("timeout", self.DEFAULT_TIMEOUT)
        
        print(f"\n{'='*60}")
        print(f"⏸️  Agent已暂停 {context}")
        print(f"   等待继续信号... (超时: {timeout}秒)")
        print(f"{'='*60}")
        
        # 进入等待循环
        wait_count = 0
        while True:
            # 检查超时
            elapsed = time.time() - pause_timestamp
            if elapsed > timeout:
                print(f"\n⚠️ 暂停超时 ({elapsed:.1f}秒)，自动继续")
                self.resume()
                return False
            
            # 重新读取状态
            try:
                state = self._read_state()
                if not state.get("is_paused", False):
                    # 已恢复
                    print(f"\n{'='*60}")
                    print(f"▶️  Agent继续执行 {context}")
                    print(f"   暂停时长: {time.time() - pause_start:.1f}秒")
                    print(f"{'='*60}\n")
                    return True
            except Exception as e:
                print(f"[PauseController] 读取状态失败: {e}")
            
            # 等待一段时间后再次检查
            time.sleep(self.CHECK_INTERVAL)
            wait_count += 1
            
            # 每10秒输出一次等待状态
            if wait_count % 20 == 0:
                elapsed = time.time() - pause_start
                print(f"   等待中... ({elapsed:.0f}秒)")
    
    def get_status(self) -> dict:
        """
        获取当前状态信息
        
        Returns:
            dict: 状态信息字典
        """
        state = self._read_state()
        return {
            "is_paused": state.get("is_paused", False),
            "timestamp": state.get("timestamp", 0),
            "timeout": state.get("timeout", self.DEFAULT_TIMEOUT),
            "updated_at": state.get("updated_at", ""),
            "elapsed": time.time() - state.get("timestamp", time.time()) if state.get("is_paused") else 0
        }
    
    def reset(self):
        """重置状态（清除暂停）"""
        try:
            self._write_state(is_paused=False, timestamp=time.time())
            print("[PauseController] 状态已重置")
        except Exception as e:
            print(f"[PauseController] 重置失败: {e}")


# 全局单例实例
_controller_instance: Optional[PauseController] = None


def get_pause_controller() -> PauseController:
    """
    获取全局暂停控制器实例
    
    Returns:
        PauseController: 全局实例
    """
    global _controller_instance
    if _controller_instance is None:
        _controller_instance = PauseController()
    return _controller_instance


# 便捷函数
def is_paused() -> bool:
    """检查是否暂停"""
    return get_pause_controller().is_paused()


def pause() -> bool:
    """暂停Agent"""
    return get_pause_controller().pause()


def resume() -> bool:
    """继续Agent"""
    return get_pause_controller().resume()


def check_and_wait(context: str = "") -> bool:
    """检查并等待"""
    return get_pause_controller().check_and_wait(context)
