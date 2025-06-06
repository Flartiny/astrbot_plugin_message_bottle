from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger, AstrBotConfig
from typing import Optional

from .bottle_storage import BottleStorage
from .utils import collect_images
from .config_manager import ConfigManager
from .message_formatter import MessageFormatter
import aiohttp


@register("message_bottle", "Flartiny", "", "")
class DriftBottlePlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config_manager = ConfigManager(config)
        self.message_formatter = MessageFormatter()
        try:
            logger.info(context.get_config()["content_safety"]["baidu_aip"])
            self._http_client = aiohttp.ClientSession()
            self.storage = BottleStorage(
                data_dir="data",
                api_base_url=self.config_manager.api_base_url,
                http_client=self._http_client,
                enable_content_safety=self.config_manager.enable_content_safety,
                content_safety_config=context.get_config()["content_safety"][
                    "baidu_aip"
                ],
            )
        except Exception as e:
            logger.error(f"DriftBottlePlugin: 初始化失败，服务可能不可用: {e}")
            self._http_client = None
            self.storage = None

    async def terminate(self):
        """插件终止时的清理工作：关闭 aiohttp.ClientSession"""
        logger.info("DriftBottlePlugin: 插件终止中，关闭HTTP客户端...")
        if self._http_client:
            try:
                await self._http_client.close()  # 确保关闭异步 HTTP 客户端
                logger.info("DriftBottlePlugin: aiohttp ClientSession 已关闭。")
            except Exception as e:
                logger.error(f"DriftBottlePlugin: 关闭 aiohttp ClientSession 失败: {e}")
            self._http_client = None  # 清理引用
        self.storage = None  # 清理引用
        logger.info("DriftBottlePlugin: 插件清理完成。")

    @filter.command("扔云瓶中信", alias={"throw_cloud_bottle"})
    async def throw_cloud_bottle(
        self, event: AstrMessageEvent, content: Optional[str] = ""
    ):
        """扔一个云瓶中信"""
        images = await collect_images(event, self.config_manager.use_base64)
        if content == "" and not images:
            yield event.plain_result("瓶中信不能是空的哦，请至少包含文字或图片～")
            return
        # 检查内容限制
        passed, error_msg = self.config_manager.check_content_limits(content, images)
        if not passed:
            yield event.plain_result(error_msg)
            return
        # 只保留允许的最大图片数量
        images = images[: self.config_manager.max_images]

        # 添加瓶中信
        bottle_id = await self.storage.add_bottle(
            content=content,
            images=images,
            sender=event.get_sender_name(),
            sender_id=event.get_sender_id(),
            is_cloud=True,
        )
        if bottle_id == None:
            yield event.plain_result("添加云瓶中信失败，请稍后重试或查看日志...")
            return
        yield event.plain_result(
            f"你的瓶中信已经扔进大海了！云瓶中信的编号是 {bottle_id}"
        )

    @filter.command("捡云瓶中信", alias={"pick_cloud_bottle"})
    async def pick_cloud_bottle(self, event: AstrMessageEvent):
        """捡起一个瓶中信"""
        bottle, msg = await self.storage.pick_random_bottle(
            event.get_sender_id(), is_cloud=True
        )

        if not bottle:
            yield event.plain_result(msg)
            return

        yield self.message_formatter.create_bottle_message(event, bottle, msg)

    @filter.command(
        "被捡起的瓶中信", alias={"selected_picked_bottle", "random_picked_bottle"}
    )
    async def picked_bottle(
        self, event: AstrMessageEvent, bottle_id: Optional[str] = None
    ):
        """查看已捡起的瓶中信"""
        bottle = self.storage.get_picked_bottle(event.get_sender_id(), bottle_id)
        if not bottle:
            if bottle_id is not None:
                yield event.plain_result(f"没有找到编号为 {bottle_id} 的瓶中信")
            else:
                yield event.plain_result("还没有被捡起的瓶中信...")
            return

        yield self.message_formatter.create_bottle_message(
            event, bottle, "这是一个被捡起的瓶中信！"
        )

    @filter.command("未被捡起的瓶中信", alias={"bottle_count"})
    async def bottle_count(self, event: AstrMessageEvent):
        """查看当前瓶中信数量"""
        local_active_count, picked_count = self.storage.get_local_bottle_counts(
            event.get_sender_id()
        )
        cloud_active_count = await self.storage.get_cloud_bottle_counts()
        if cloud_active_count == -1:
            yield event.plain_result(
                "获取云瓶中信数量失败，请稍后重试...\n"
                f"当前海面上还有 {local_active_count} 个瓶中信\n"
                f"你已经捡起 {picked_count} 个瓶中信"
            )
            return
        yield event.plain_result(
            f"当前海面上还有 {local_active_count + cloud_active_count} 个瓶中信\n"
            f"你已经捡起 {picked_count} 个瓶中信"
        )

    @filter.command("被捡起的瓶中信列表", alias={"list_picked_bottles"})
    async def list_picked_bottles(self, event: AstrMessageEvent):
        """显示所有被捡起的瓶中信列表"""
        bottles = self.storage.get_picked_bottles(event.get_sender_id())
        message = self.message_formatter.format_picked_bottles_list(bottles)
        yield event.plain_result(message)

    @filter.command("扔瓶中信", alias={"throw_bottle"})
    async def throw_bottle(self, event: AstrMessageEvent, content: Optional[str] = ""):
        """扔一个瓶中信"""
        # 收集所有图片
        images = await collect_images(event, self.config_manager.use_base64)

        # 检查内容限制
        passed, error_msg = self.config_manager.check_content_limits(content, images)
        if not passed:
            yield event.plain_result(error_msg)
            return

        # 只保留允许的最大图片数量
        images = images[: self.config_manager.max_images]

        # 添加瓶中信
        bottle_id = await self.storage.add_bottle(
            content=content,
            images=images,
            sender=event.get_sender_name(),
            sender_id=event.get_sender_id(),
            is_cloud=False,
        )
        if bottle_id is None:
            yield event.plain_result("添加瓶中信失败，请稍后重试...")
            return
        yield event.plain_result(f"你的瓶中信已经扔进大海了！瓶子的编号是 {bottle_id}")

    @filter.command("捡瓶中信", alias={"pick_bottle"})
    async def pick_bottle(self, event: AstrMessageEvent):
        """捡起一个瓶中信"""
        bottle, msg = await self.storage.pick_random_bottle(
            event.get_sender_id(), is_cloud=False
        )

        if not bottle:
            yield event.plain_result(msg)
            return

        yield self.message_formatter.create_bottle_message(
            event, bottle, "你捡到了一个瓶中信！"
        )
