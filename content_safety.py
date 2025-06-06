"""
使用此功能应该先 pip install baidu-aip
"""

from aip import AipContentCensor


class ContentSafety:
    def __init__(self, appid: str, ak: str, sk: str) -> None:
        self.app_id = appid
        self.api_key = ak
        self.secret_key = sk
        self.client = AipContentCensor(self.app_id, self.api_key, self.secret_key)

    def check(self, type: str, content: str):
        if type == "text":
            res = self.client.textCensorUserDefined(content)
        elif type == "image":
            res = self.client.imageCensorUserDefined(content)
        if "conclusionType" not in res:
            return False
        # 合规
        if res["conclusionType"] == 1:
            return True
        else:
            return False
