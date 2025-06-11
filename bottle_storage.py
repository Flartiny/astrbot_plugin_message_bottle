from typing import Dict, List, Optional
import os
from astrbot.api.event import AstrMessageEvent
from astrbot.api import logger
import random
import aiohttp
from typing import Any
from datetime import datetime
from .utils import (
    _ensure_data_file,
    _load_bottles,
    _save_bottles,
    get_bottle2handle,
    check_bottle,
    get_rkey,
)
import asyncio


class BottleStorage:
    def __init__(
        self,
        data_dir: str,
        api_base_url: str,
        http_client: aiohttp.ClientSession,
        enable_content_safety: bool,
        content_safety_config: dict,
    ):
        self.api_base_url = api_base_url  # 这是 FastAPI 服务的基URL
        self.http_client = http_client
        self.data_file = os.path.join(data_dir, "astrbot_plugin_message_bottle.json")
        _ensure_data_file(self.data_file)
        self.data = _load_bottles(self.data_file)
        self.lock = asyncio.Lock()
        self.enable_content_safety = enable_content_safety
        # 检查瓶中信内容是否合规
        if enable_content_safety:
            try:
                from .content_safety import ContentSafety
            except ImportError:
                logger.error("使用内容安全检查应该先 pip install baidu-aip")
                raise
            self.content_safety = ContentSafety(
                content_safety_config["app_id"],
                content_safety_config["api_key"],
                content_safety_config["secret_key"],
            )

    async def _make_api_request(
        self, method: str, path: str, json_data: Optional[Dict] = None
    ) -> Any:
        url = f"{self.api_base_url}{path}"
        try:
            if method == "GET":
                async with self.http_client.get(url) as response:
                    response.raise_for_status()
                    return await response.json()
            elif method == "POST":
                async with self.http_client.post(url, json=json_data) as response:
                    response.raise_for_status()
                    return await response.json()
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
        except aiohttp.ClientResponseError as e:
            # 捕获 HTTP 状态码错误 (例如 404, 500)
            logger.error(
                f"API请求失败 (HTTP Status Error {e.status} - {method} {url}): {e}"
            )
            raise  # 重新抛出，让调用者处理，或根据需要返回 None
        except aiohttp.ClientError as e:
            # 捕获更广泛的客户端错误 (例如连接问题，超时)
            logger.error(f"API请求失败 (Client Error - {method} {url}): {e}")
            raise  # 重新抛出，让调用者处理，或根据需要返回 None

    async def add_bottle(
        self,
        content: str,
        images: List[Dict],
        sender: str,
        sender_id: str,
        is_cloud: bool,
        poke: bool,
    ) -> str:
        bottle_data = {
            "content": content,
            "images": images,
            "sender": sender,
            "sender_id": sender_id,
            "poke": poke,
        }
        try:
            if is_cloud:
                # 添加新云瓶中信
                response_data = await self._make_api_request(
                    "POST", "/bottles/", json_data=bottle_data
                )
                response_id = response_data.get("bottle_id")
                new_id = f"c{response_id}"
                if new_id is None:
                    raise ValueError("API did not return a bottle_id.")
            else:
                # 本地添加瓶中信
                async with self.lock:
                    bottle_data["picked"] = False
                    bottle_data["timestamp"] = datetime.now().strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                    local_id_counter = self.data.get("next_local_id", 1)
                    new_id = f"l{local_id_counter}"
                    bottle_data["bottle_id"] = new_id
                    self.data["next_local_id"] = local_id_counter + 1
                    self.data["active"].append(bottle_data)
                    _save_bottles(self.data_file, self.data)

            logger.info(f"成功添加瓶中信，ID: {new_id}")
            return new_id
        except Exception as e:
            logger.error(f"添加瓶中信失败: {str(e)}")
            return None

    async def pick_random_cloud_bottle(
        self, event: AstrMessageEvent
    ) -> tuple[Optional[Dict], str]:
        """随机捡起一个云瓶中信"""
        try:
            sender_id = event.get_sender_id()
            rkey = await get_rkey(event)
            bottle = await self._make_api_request("POST", f"/bottles/pick/{sender_id}")
            bottle["bottle_id"] = f"c{bottle['bottle_id']}"
            # 对于含qq图片的bottle, bottle2handle中添加了rkey(qq平台接收时)
            bottle2handle = await get_bottle2handle(bottle, rkey)
            # 检查瓶中信内容是否合规
            if self.enable_content_safety:
                bottle2handle, msg = await check_bottle(
                    bottle2handle, self.content_safety
                )
                if not bottle2handle:
                    return None, msg

            if bottle and bottle.get("bottle_id") is not None:
                async with self.lock:
                    if sender_id not in self.data["user_list"]:
                        self.data["user_list"][sender_id] = []
                    self.data["user_list"][sender_id].append(bottle)
                    _save_bottles(self.data_file, self.data)
                logger.info(
                    f"用户 {sender_id} 成功捡起瓶中信，ID: {bottle.get('bottle_id')}"
                )
                msg = "你捡到了一个瓶中信！"
                return bottle2handle, msg

        except aiohttp.ClientResponseError as e:
            if e.status == 404:  # FastAPI 返回 404 表示没有可捡的瓶子
                logger.info(f"没有可供用户 {sender_id} 捡起的瓶中信。")
                msg = "海面上没有别人的瓶中信了..."
                return None, msg
            else:
                logger.error(f"捡起瓶中信失败 (HTTP Status Error {e.status}): {str(e)}")
                msg = "捡起瓶中信失败，请稍后重试..."
                return None, msg
        except Exception as e:
            logger.error(f"捡起瓶中信失败: {str(e)}")
            msg = "捡起瓶中信失败，请稍后重试..."
            return None, msg

    async def pick_random_bottle(
        self, event: AstrMessageEvent
    ) -> tuple[Optional[Dict], str]:
        """随机捡起一个瓶中信"""
        try:
            sender_id = event.get_sender_id()
            rkey = await get_rkey(event)
            async with self.lock:
                available_bottles = [
                    b
                    for b in self.data["active"]
                    if not b.get("picked") and b.get("sender_id") != sender_id
                ]
                if not available_bottles:
                    msg = "海面上没有别人的瓶中信了..."
                    return None, msg
                bottle = random.choice(available_bottles)

            if bottle and bottle.get("bottle_id") is not None:
                self.data["active"].remove(bottle)
                bottle["picked"] = True
                # 对于本地瓶中信，不需要审查, bottle2handle仅用于返回
                bottle2handle = await get_bottle2handle(bottle, rkey)
                async with self.lock:
                    if sender_id not in self.data["user_list"]:
                        self.data["user_list"][sender_id] = []
                    self.data["user_list"][sender_id].append(bottle)
                    _save_bottles(self.data_file, self.data)
                logger.info(
                    f"用户 {sender_id} 成功捡起瓶中信，ID: {bottle.get('bottle_id')}"
                )
                msg = "你捡到了一个瓶中信！"
                return bottle2handle, msg
        except Exception as e:  # 捕获其他可能的异常，如连接问题
            logger.error(f"捡起瓶中信失败: {str(e)}")
            msg = "捡起瓶中信失败，请稍后重试..."
            return None, msg

    async def get_picked_bottle(
        self, event: AstrMessageEvent, bottle_id: Optional[str] = None
    ) -> Optional[Dict]:
        """获取指定ID或随机一个已捡起的瓶中信"""
        sender_id = event.get_sender_id()
        rkey = await get_rkey(event)
        if sender_id not in self.data["user_list"]:
            return None
        selected_bottle = None
        if bottle_id is not None:
            for bottle in self.data["user_list"][sender_id]:
                if bottle["bottle_id"] == bottle_id:
                    selected_bottle = bottle
                    break
            if not selected_bottle:
                return None
        else:
            selected_bottle = random.choice(self.data["user_list"][sender_id])

        bottle2handle = await get_bottle2handle(selected_bottle, rkey)
        return bottle2handle

    def get_local_bottle_counts(self, sender_id: str) -> tuple[int, int]:
        """获取瓶中信数量"""
        # total active bottles: 通过本地获取
        total_active_bottles = len(self.data["active"])

        # picked bottles: 从本地数据获取
        picked_bottles = self.data["user_list"].get(sender_id, [])
        user_picked_bottles_count = len(picked_bottles)

        # 尚有瓶中信数量，用户已捡起瓶中信数量
        return total_active_bottles, user_picked_bottles_count

    async def get_cloud_bottle_counts(self) -> int:
        """获取瓶中信数量"""
        # total active bottles: 通过API获取
        total_active_bottles = -1
        try:
            response_data = await self._make_api_request(
                "GET", "/bottles/counts/active"
            )
            total_active_bottles = response_data.get("total_active_bottles", 0)
        except Exception as e:
            logger.error(f"获取总活跃瓶中信数量失败: {str(e)}")

        return total_active_bottles

    def get_picked_bottles(self, sender_id: str) -> List[Dict]:
        """获取所有已捡起的瓶中信"""
        bottles = self.data["user_list"].get(sender_id, [])

        return sorted(bottles, key=lambda x: x["timestamp"], reverse=True)
