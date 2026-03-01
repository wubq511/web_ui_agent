"""
================================================================================
检查点模块 - 任务状态保存与恢复功能
================================================================================

【模块概述】
实现任务状态保存与恢复功能，支持复杂任务的断点续接。

【核心功能】
1. 任务状态序列化与反序列化
2. 检查点自动保存
3. 断点恢复执行
4. 多检查点管理
================================================================================
"""

import os
import json
import hashlib
import time
from typing import Optional
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path

from config import CHECKPOINT_DIR, CHECKPOINT_INTERVAL


@dataclass
class CheckpointMetadata:
    """检查点元数据"""
    checkpoint_id: str
    objective: str
    step_count: int
    timestamp: float
    is_complete: bool
    error_count: int
    progress_ratio: float
    description: str = ""


@dataclass
class CheckpointData:
    """检查点完整数据"""
    metadata: CheckpointMetadata
    state: dict
    step_manager: dict
    completion_evaluator: dict
    termination_manager: dict
    user_interaction: dict
    storage_state: dict = field(default_factory=dict)
    version: str = "1.1"


class CheckpointManager:
    """
    检查点管理器 - 任务状态保存与恢复
    
    【设计思路】
    提供完整的检查点管理功能：
    1. 定期自动保存检查点
    2. 手动保存检查点
    3. 从检查点恢复任务
    4. 检查点列表管理
    5. 过期检查点清理
    """
    
    def __init__(self, checkpoint_dir: str = CHECKPOINT_DIR):
        self.checkpoint_dir = Path(checkpoint_dir)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        
        self._last_checkpoint_step = 0
        self._checkpoint_interval = CHECKPOINT_INTERVAL
        self._checkpoints: list[CheckpointMetadata] = []
        
        self._load_checkpoint_list()
    
    def _load_checkpoint_list(self):
        """加载检查点列表"""
        list_file = self.checkpoint_dir / "checkpoint_list.json"
        if list_file.exists():
            try:
                with open(list_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self._checkpoints = [
                        CheckpointMetadata(**item) for item in data
                    ]
            except Exception as e:
                print(f"⚠️ 加载检查点列表失败: {e}")
                self._checkpoints = []
    
    def _save_checkpoint_list(self):
        """保存检查点列表"""
        list_file = self.checkpoint_dir / "checkpoint_list.json"
        try:
            with open(list_file, 'w', encoding='utf-8') as f:
                json.dump([asdict(cp) for cp in self._checkpoints], f, 
                         ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"⚠️ 保存检查点列表失败: {e}")
    
    def generate_checkpoint_id(self, objective: str, step_count: int) -> str:
        """
        生成检查点ID
        
        【格式】
        cp_{易读时间}_{短哈希}
        例如: cp_20260228_120530_a1b2c3d4
        """
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        content = f"{objective}_{step_count}_{timestamp_str}"
        hash_value = hashlib.md5(content.encode()).hexdigest()[:8]
        return f"cp_{timestamp_str}_{hash_value}"
    
    def should_save_checkpoint(self, current_step: int) -> bool:
        """判断是否应该保存检查点"""
        return current_step > 0 and current_step % self._checkpoint_interval == 0
    
    def save_checkpoint(self, state: dict, step_manager: dict,
                       completion_evaluator: dict, termination_manager: dict,
                       user_interaction: dict, storage_state: dict = None,
                       description: str = "") -> str:
        """
        保存检查点
        
        【参数】
        state: Agent状态
        step_manager: 步骤管理器状态
        completion_evaluator: 完成度评估器状态
        termination_manager: 终止管理器状态
        user_interaction: 用户交互状态
        storage_state: 浏览器会话状态（cookies、localStorage等）
        description: 检查点描述
        
        【返回值】
        str: 检查点ID
        """
        objective = state.get("objective", "未知任务")
        step_count = state.get("step_count", 0)
        
        checkpoint_id = self.generate_checkpoint_id(objective, step_count)
        
        metadata = CheckpointMetadata(
            checkpoint_id=checkpoint_id,
            objective=objective,
            step_count=step_count,
            timestamp=time.time(),
            is_complete=state.get("is_done", False),
            error_count=sum(1 for h in state.get("history", []) 
                          if "错误" in h.get("result", "")),
            progress_ratio=completion_evaluator.get("last_progress_ratio", 0),
            description=description
        )
        
        checkpoint_data = CheckpointData(
            metadata=metadata,
            state=state,
            step_manager=step_manager,
            completion_evaluator=completion_evaluator,
            termination_manager=termination_manager,
            user_interaction=user_interaction,
            storage_state=storage_state or {}
        )
        
        checkpoint_file = self.checkpoint_dir / f"{checkpoint_id}.json"
        try:
            with open(checkpoint_file, 'w', encoding='utf-8') as f:
                json.dump(asdict(checkpoint_data), f, ensure_ascii=False, indent=2)
            
            self._checkpoints.append(metadata)
            self._save_checkpoint_list()
            
            print(f"💾 检查点已保存: {checkpoint_id}")
            self._last_checkpoint_step = step_count
            
            return checkpoint_id
            
        except Exception as e:
            print(f"❌ 保存检查点失败: {e}")
            return ""
    
    def load_checkpoint(self, checkpoint_id: str) -> Optional[CheckpointData]:
        """
        加载检查点
        
        【参数】
        checkpoint_id: 检查点ID
        
        【返回值】
        CheckpointData: 检查点数据，失败返回None
        """
        checkpoint_file = self.checkpoint_dir / f"{checkpoint_id}.json"
        
        if not checkpoint_file.exists():
            print(f"❌ 检查点不存在: {checkpoint_id}")
            return None
        
        try:
            with open(checkpoint_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            checkpoint_data = CheckpointData(
                metadata=CheckpointMetadata(**data["metadata"]),
                state=data["state"],
                step_manager=data["step_manager"],
                completion_evaluator=data["completion_evaluator"],
                termination_manager=data["termination_manager"],
                user_interaction=data["user_interaction"],
                storage_state=data.get("storage_state", {}),
                version=data.get("version", "1.0")
            )
            
            print(f"📂 检查点已加载: {checkpoint_id}")
            return checkpoint_data
            
        except Exception as e:
            print(f"❌ 加载检查点失败: {e}")
            return None
    
    def get_latest_checkpoint(self) -> Optional[CheckpointMetadata]:
        """获取最新的检查点"""
        if not self._checkpoints:
            return None
        return max(self._checkpoints, key=lambda x: x.timestamp)
    
    def list_checkpoints(self, limit: int = 10) -> list[CheckpointMetadata]:
        """列出检查点"""
        sorted_checkpoints = sorted(self._checkpoints, 
                                    key=lambda x: x.timestamp, reverse=True)
        return sorted_checkpoints[:limit]
    
    def delete_checkpoint(self, checkpoint_id: str) -> bool:
        """删除检查点"""
        checkpoint_file = self.checkpoint_dir / f"{checkpoint_id}.json"
        
        try:
            if checkpoint_file.exists():
                checkpoint_file.unlink()
            
            self._checkpoints = [
                cp for cp in self._checkpoints 
                if cp.checkpoint_id != checkpoint_id
            ]
            self._save_checkpoint_list()
            
            print(f"🗑️ 检查点已删除: {checkpoint_id}")
            return True
            
        except Exception as e:
            print(f"❌ 删除检查点失败: {e}")
            return False
    
    def cleanup_old_checkpoints(self, max_age_hours: int = 24, 
                                keep_count: int = 5):
        """
        清理过期检查点
        
        【参数】
        max_age_hours: 最大保留时间（小时）
        keep_count: 最少保留数量
        """
        current_time = time.time()
        max_age_seconds = max_age_hours * 3600
        
        valid_checkpoints = []
        deleted_count = 0
        
        sorted_checkpoints = sorted(self._checkpoints, 
                                    key=lambda x: x.timestamp, reverse=True)
        
        for i, cp in enumerate(sorted_checkpoints):
            if i < keep_count:
                valid_checkpoints.append(cp)
            elif current_time - cp.timestamp < max_age_seconds:
                valid_checkpoints.append(cp)
            else:
                self.delete_checkpoint(cp.checkpoint_id)
                deleted_count += 1
        
        self._checkpoints = valid_checkpoints
        self._save_checkpoint_list()
        
        if deleted_count > 0:
            print(f"🧹 已清理 {deleted_count} 个过期检查点")
    
    def get_checkpoint_display(self, checkpoint: CheckpointMetadata) -> str:
        """获取检查点显示字符串"""
        time_str = datetime.fromtimestamp(checkpoint.timestamp).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        status = "✅ 已完成" if checkpoint.is_complete else "🔄 进行中"
        
        return (
            f"ID: {checkpoint.checkpoint_id}\n"
            f"   目标: {checkpoint.objective[:50]}...\n"
            f"   步骤: {checkpoint.step_count}\n"
            f"   进度: {checkpoint.progress_ratio:.1%}\n"
            f"   状态: {status}\n"
            f"   时间: {time_str}"
        )
    
    def display_checkpoints(self, limit: int = 5):
        """显示检查点列表"""
        checkpoints = self.list_checkpoints(limit)
        
        if not checkpoints:
            print("📭 暂无检查点")
            return
        
        print(f"\n📋 检查点列表 (最近 {len(checkpoints)} 个):")
        print("=" * 60)
        
        for i, cp in enumerate(checkpoints, 1):
            print(f"\n[{i}] {self.get_checkpoint_display(cp)}")
        
        print("\n" + "=" * 60)
    
    def reset(self):
        """重置检查点管理器"""
        self._last_checkpoint_step = 0
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "checkpoint_dir": str(self.checkpoint_dir),
            "last_checkpoint_step": self._last_checkpoint_step,
            "checkpoint_interval": self._checkpoint_interval,
            "checkpoint_count": len(self._checkpoints)
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'CheckpointManager':
        """从字典创建实例"""
        manager = cls(checkpoint_dir=data.get("checkpoint_dir", CHECKPOINT_DIR))
        manager._last_checkpoint_step = data.get("last_checkpoint_step", 0)
        manager._checkpoint_interval = data.get("checkpoint_interval", CHECKPOINT_INTERVAL)
        return manager
