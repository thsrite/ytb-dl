"""统一消息模板模块"""
from typing import Optional, Dict, Any
from datetime import datetime


class MessageTemplates:
    """统一的消息模板类"""

    @staticmethod
    def format_admin_notification(
        task_id: str,
        status: str,
        user_id: str = "Unknown",
        source: str = "Web",
        url: Optional[str] = None,
        title: Optional[str] = None,
        download_link: Optional[str] = None,
        error_msg: Optional[str] = None,
        file_size: Optional[str] = None,
        duration: Optional[str] = None,
        retry_count: int = 0
    ) -> Dict[str, Any]:
        """
        生成管理员通知的统一模板

        Args:
            task_id: 任务ID
            status: 状态 (start/complete/error/403_error/403_retry)
            user_id: 用户ID
            source: 来源 (WeChat/Web)
            url: YouTube URL
            title: 视频标题
            download_link: 下载链接
            error_msg: 错误消息
            file_size: 文件大小
            duration: 下载耗时
            retry_count: 重试次数

        Returns:
            格式化的消息字典
        """
        # 状态映射
        status_map = {
            'start': '📥 新任务开始',
            'complete': '✅ 下载完成',
            'error': '❌ 下载失败',
            '403_error': '🔒 403错误',
            '403_retry': '🔄 重试下载',
            'network_error': '🌐 网络错误',
            'network_retry': '🔄 网络重试'
        }

        # 构建标题
        if status == 'complete' and title:
            msg_title = f"✅ 下载完成: {title[:30]}{'...' if len(title) > 30 else ''}"
        elif status == 'error':
            msg_title = f"❌ 下载失败: {title[:30]}{'...' if len(title) > 30 else ''}" if title else f"❌ 下载失败: 任务 {task_id}"
        elif status == '403_error':
            msg_title = f"🔒 403错误: {title[:30]}{'...' if len(title) > 30 else ''}" if title else f"🔒 403错误: 任务 {task_id}"
        elif status == '403_retry':
            msg_title = f"🔄 Cookie同步中: {title[:30]}{'...' if len(title) > 30 else ''}" if title else f"🔄 Cookie同步中: 任务 {task_id}"
        elif status == 'network_error':
            msg_title = f"🌐 网络错误: {title[:30]}{'...' if len(title) > 30 else ''}" if title else f"🌐 网络错误: 任务 {task_id}"
        elif status == 'network_retry':
            msg_title = f"🔄 网络重试: {title[:30]}{'...' if len(title) > 30 else ''}" if title else f"🔄 网络重试: 任务 {task_id}"
        elif status == 'start' and title:
            msg_title = f"📥 新任务: {title[:30]}{'...' if len(title) > 30 else ''}"
        else:
            msg_title = f"📥 新任务: {task_id}"

        # 构建描述
        description_parts = []
        description_parts.append(f"📊 状态: {status_map.get(status, status)}")
        description_parts.append(f"👤 用户: {user_id}")
        description_parts.append(f"🌐 来源: {source}")

        if url:
            description_parts.append(f"🔗 URL: {url}")

        if title and status != 'complete':  # complete状态标题已在msg_title中
            description_parts.append(f"📹 标题: {title}")

        if file_size:
            description_parts.append(f"📦 大小: {file_size}")

        if duration:
            description_parts.append(f"⏱️ 耗时: {duration}")

        if retry_count > 0:
            description_parts.append(f"🔁 重试次数: {retry_count}")

        if error_msg:
            # 限制错误消息长度
            error_display = error_msg[:100] + '...' if len(error_msg) > 100 else error_msg
            description_parts.append(f"⚠️ 错误: {error_display}")

        description_parts.append(f"🕐 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        # 确定链接
        if status == 'complete' and download_link:
            link = download_link
            description_parts.append("\n💾 点击卡片下载文件")
        elif url:
            link = url
        else:
            link = None

        description = "\n".join(description_parts)

        return {
            'title': msg_title,
            'description': description,
            'url': link,
            'picurl': ''
        }

    @staticmethod
    def format_user_notification(
        status: str,
        title: Optional[str] = None,
        download_link: Optional[str] = None,
        error_msg: Optional[str] = None,
        retry_info: Optional[str] = None
    ) -> str:
        """
        生成用户通知的统一模板

        Args:
            status: 状态 (start/complete/error/403_error/403_retry)
            title: 视频标题
            download_link: 下载链接
            error_msg: 错误消息
            retry_info: 重试信息

        Returns:
            格式化的消息字符串
        """
        if status == 'start':
            return f"📥 开始下载: {title[:50]}..." if title else "📥 开始下载任务"

        elif status == 'complete':
            msg = f"✅ 下载完成: {title[:50]}..." if title else "✅ 下载完成"
            if download_link:
                msg += f"\n🔗 下载链接: {download_link}"
            return msg

        elif status == 'error':
            msg = f"❌ 下载失败: {title[:50]}..." if title else "❌ 下载失败"
            if error_msg:
                error_display = error_msg[:100] + '...' if len(error_msg) > 100 else error_msg
                msg += f"\n⚠️ 错误: {error_display}"
            return msg

        elif status == '403_error':
            msg = "🔒 遇到403错误，正在尝试同步Cookie..."
            if retry_info:
                msg += f"\n{retry_info}"
            return msg

        elif status == '403_retry':
            msg = "🔄 Cookie同步成功，正在重新下载..."
            if retry_info:
                msg += f"\n{retry_info}"
            return msg

        else:
            return f"📢 {status}"

    @staticmethod
    def format_403_notification(
        task_id: str,
        url: str,
        retry_count: int = 0,
        cookie_sync_status: Optional[str] = None,
        is_final: bool = False
    ) -> Dict[str, Any]:
        """
        生成403错误相关的通知模板

        Args:
            task_id: 任务ID
            url: YouTube URL
            retry_count: 重试次数
            cookie_sync_status: Cookie同步状态
            is_final: 是否最终失败

        Returns:
            包含admin和user消息的字典
        """
        if is_final:
            admin_msg = {
                'title': f"❌ 403错误最终失败: {task_id}",
                'description': f"📊 状态: ❌ 最终失败\n"
                             f"🔗 URL: {url}\n"
                             f"🔁 重试次数: {retry_count}\n"
                             f"⚠️ 原因: 多次重试后仍然失败\n"
                             f"🕐 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                'url': url
            }
            user_msg = f"❌ 下载失败: 403错误\n已尝试{retry_count}次仍然失败，请检查Cookie配置"
        elif cookie_sync_status:
            admin_msg = {
                'title': f"🔄 正在重试: {task_id}",
                'description': f"📊 状态: 🔄 Cookie同步{cookie_sync_status}\n"
                             f"🔗 URL: {url}\n"
                             f"🔁 第{retry_count}次重试\n"
                             f"🕐 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                'url': url
            }
            user_msg = f"🔄 Cookie同步{cookie_sync_status}，正在第{retry_count}次重试下载..."
        else:
            admin_msg = {
                'title': f"🔒 403错误: {task_id}",
                'description': f"📊 状态: 🔒 403错误\n"
                             f"🔗 URL: {url}\n"
                             f"🔁 准备第{retry_count + 1}次重试\n"
                             f"🕐 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                'url': url
            }
            user_msg = f"🔒 遇到403错误，正在同步Cookie并准备重试..."

        return {
            'admin': admin_msg,
            'user': user_msg
        }