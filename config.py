import json
import os
from typing import Dict, Any, Optional

class Config:
    def __init__(self, config_file: str = "config.json"):
        self.config_file = config_file
        self.default_config = {
            "cookies_file": None,
            "proxy": None,
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "extra_params": {
                "nocheckcertificate": True,
                "geo_bypass": True,
                "age_limit": None,
                "sleep_interval": 1,
                "max_sleep_interval": 3,
                "retries": 3,
                "fragment_retries": 3,
                "skip_unavailable_fragments": True
            },
            "custom_params": []  # 自定义参数列表
        }
        self.config = self.load_config()

    def load_config(self) -> Dict[str, Any]:
        """加载配置文件"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                    # 合并默认配置和加载的配置
                    config = self.default_config.copy()
                    config.update(loaded)
                    return config
            except Exception as e:
                print(f"Error loading config: {e}")
        return self.default_config.copy()

    def save_config(self) -> bool:
        """保存配置文件"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"Error saving config: {e}")
            return False

    def update_config(self, updates: Dict[str, Any]) -> bool:
        """更新配置"""
        self.config.update(updates)
        return self.save_config()

    def get_ydl_opts(self, additional_opts: Optional[Dict] = None) -> Dict[str, Any]:
        """获取yt-dlp选项"""
        opts = {
            'quiet': True,
            'no_warnings': True,
            'user_agent': self.config.get('user_agent'),
            **self.config.get('extra_params', {})
        }

        # 添加cookies文件
        if self.config.get('cookies_file') and os.path.exists(self.config.get('cookies_file')):
            opts['cookiefile'] = self.config.get('cookies_file')

        # 添加代理
        if self.config.get('proxy'):
            opts['proxy'] = self.config.get('proxy')

        # 处理自定义参数
        custom_params = self.config.get('custom_params', [])
        for param in custom_params:
            if param and isinstance(param, str):
                # 解析参数，如 "--concurrent-fragments 5"
                parts = param.strip().split(None, 1)
                if len(parts) == 2:
                    key = parts[0].lstrip('-').replace('-', '_')
                    try:
                        # 尝试将值转换为数字
                        value = int(parts[1])
                    except ValueError:
                        try:
                            value = float(parts[1])
                        except ValueError:
                            # 如果不是数字，保持字符串
                            value = parts[1]
                    opts[key] = value
                elif len(parts) == 1:
                    # 布尔类型参数
                    key = parts[0].lstrip('-').replace('-', '_')
                    opts[key] = True

        # 合并额外选项
        if additional_opts:
            opts.update(additional_opts)

        return opts