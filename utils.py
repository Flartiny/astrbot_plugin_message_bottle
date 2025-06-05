from typing import List, Dict
import astrbot.api.message_components as Comp
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent
import os
import json


async def collect_images(event: AstrMessageEvent, use_base64: bool) -> List[Dict]:
    """收集消息中的所有图片"""
    images = []

    for component in event.message_obj.message:
        if isinstance(component, Comp.Image):
            if use_base64:
                images.append({"type": "base64", "data": await component.convert_to_base64()})
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
