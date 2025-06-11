from typing import List, Dict, Optional
import astrbot.api.message_components as Comp
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent
import os
import json
import copy
import random


async def collect_images(event: AstrMessageEvent, use_base64: bool) -> List[Dict]:
    """收集消息中的所有图片"""
    images = []

    for component in event.message_obj.message:
        if isinstance(component, Comp.Image):
            if use_base64:
                images.append(
                    {"type": "base64", "data": await component.convert_to_base64()}
                )
            else:
                if event.get_platform_name() == "aiocqhttp":
                    url = component.url.split("&rkey=")[0]
                    images.append({"type": "qq_url", "data": url})
                else:
                    images.append({"type": "url", "data": component.url})

    return images


def _ensure_data_file(data_dir: str):
    """确保数据文件存在"""
    os.makedirs(os.path.dirname(data_dir), exist_ok=True)
    if not os.path.exists(data_dir):
        with open(data_dir, "w", encoding="utf-8") as f:
            json.dump(
                {"active": [], "user_list": {}, "next_local_id": 1},
                f,
                ensure_ascii=False,
                indent=2,
            )


def _load_bottles(data_dir: str) -> Dict[str, Dict]:
    """加载瓶中信数据"""
    try:
        with open(data_dir, "r", encoding="utf-8") as f:
            data = json.load(f)
            if "active" not in data or not isinstance(data["active"], list):
                data["active"] = []
            if "user_list" not in data or not isinstance(data["user_list"], dict):
                data["user_list"] = {}
            if "next_local_id" not in data or not isinstance(
                data["next_local_id"], int
            ):
                data["next_local_id"] = 1
            return data
    except Exception as e:
        logger.error(f"加载瓶中信数据时出错: {str(e)}, 将重新规格化")
        return {"active": [], "user_list": {}, "next_local_id": 1}


def _save_bottles(data_dir: str, bottles: Dict[str, Dict]):
    """保存瓶中信数据"""
    try:
        with open(data_dir, "w", encoding="utf-8") as f:
            json.dump(bottles, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"保存瓶中信数据时出错: {str(e)}")


async def get_rkey(event: AstrMessageEvent) -> Optional[str]:
    if event.get_platform_name() == "aiocqhttp":
        from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
            AiocqhttpMessageEvent,
        )

        assert isinstance(event, AiocqhttpMessageEvent)
        client = event.bot
        rkeys = await client.api.call_action("get_rkey")

        rkey_data = next((rkey for rkey in rkeys if rkey["type"] == "group"), None)
        rkey = rkey_data["rkey"]
        return rkey
    return None


# 获得带有rkey的bottle
async def get_bottle2handle(bottle: Dict, rkey: Optional[str] = None):
    bottle = copy.deepcopy(bottle)
    for img in bottle["images"]:
        if img["type"] == "qq_url":
            img["data"] = img["data"] + (rkey or "")
    return bottle


async def check_bottle(bottle: Dict, content_safety):
    if bottle["content"] and not content_safety.check("text", bottle["content"]):
        msg = "瓶中信内容不合规，已被屏蔽。"
        return None, msg
    if bottle["images"] and not all(
        content_safety.check("image", img["data"]) for img in bottle["images"]
    ):
        msg = "瓶中信内容不合规，已被屏蔽。"
        return None, msg
    return bottle, ""


async def _handle_qq_poke(event: AstrMessageEvent):
    if event.get_platform_name() == "aiocqhttp":
        client = event.bot
        group_id = event.get_group_id()
        sender_id = event.get_sender_id()
        if group_id:
            # self_id = int(event.get_self_id())
            # payloads = {"group_id": group_id}
            # group_members = await client.api.call_action(
            #     "get_group_member_list", **payloads
            # )
            # group_members = [
            #     member for member in group_members if member.get("user_id") != self_id
            # ]
            # chosen_one = random.choice(group_members)
            # user_id = chosen_one.get("user_id")
            payloads = {"group_id": group_id, "user_id": sender_id}
            await client.api.call_action("group_poke", **payloads)
        else:
            payloads = {"user_id": sender_id}
            await client.api.call_action("friend_poke", **payloads)
