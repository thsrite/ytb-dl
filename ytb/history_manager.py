import json
import os
from typing import List, Dict, Any, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class HistoryManager:
    def __init__(self, history_file: Optional[str] = None):
        if history_file is None:
            # Check if running in Docker container
            if os.path.exists("/app"):
                history_file = "/app/config/download_history.json"
            else:
                # Default path relative to the project root
                base_dir = os.path.dirname(os.path.dirname(__file__))  # Go up two levels from ytb/history_manager.py
                history_file = os.path.join(base_dir, "config", "download_history.json")
        self.history_file = history_file
        self.history: List[Dict[str, Any]] = []
        self.load_history()

    def load_history(self) -> None:
        """从文件加载历史记录"""
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    self.history = json.load(f)
            except Exception as e:
                logger.error(f"Error loading history: {e}")
                self.history = []
        else:
            self.history = []

    def save_history(self) -> bool:
        """保存历史记录到文件"""
        try:
            directory = os.path.dirname(self.history_file)
            if directory:
                os.makedirs(directory, exist_ok=True)
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(self.history, f, indent=2, ensure_ascii=False, default=str)
            return True
        except Exception as e:
            logger.error(f"Error saving history: {e}")
            return False

    def add_entry(self, entry: Dict[str, Any]) -> None:
        """添加新的历史记录"""
        # 确保有必要的字段
        if 'downloaded_at' not in entry:
            entry['downloaded_at'] = datetime.now().isoformat()

        # 添加到开头（最新的在前）
        self.history.insert(0, entry)

        # 限制历史记录数量（可选，保留最近100条）
        if len(self.history) > 100:
            self.history = self.history[:100]

        self.save_history()

    def get_all(self) -> List[Dict[str, Any]]:
        """获取所有历史记录"""
        return self.history

    def get_entry(self, task_id: str) -> Optional[Dict[str, Any]]:
        """根据task_id获取历史记录"""
        for entry in self.history:
            if entry.get('id') == task_id:
                return entry
        return None

    def update_entry(self, task_id: str, updates: Dict[str, Any]) -> bool:
        """更新历史记录"""
        for entry in self.history:
            if entry.get('id') == task_id:
                entry.update(updates)
                self.save_history()
                return True
        return False

    def delete_entry(self, task_id: str) -> bool:
        """删除历史记录"""
        original_length = len(self.history)
        self.history = [h for h in self.history if h.get('id') != task_id]

        if len(self.history) < original_length:
            self.save_history()
            return True
        return False

    def cleanup_old_entries(self, days: int = 30) -> int:
        """清理超过指定天数的历史记录"""
        from datetime import timedelta
        cutoff_date = datetime.now() - timedelta(days=days)
        original_length = len(self.history)

        self.history = [
            h for h in self.history
            if datetime.fromisoformat(h.get('downloaded_at', ''))> cutoff_date
        ]

        removed = original_length - len(self.history)
        if removed > 0:
            self.save_history()
        return removed
