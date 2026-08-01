"""已经迁移到新加载器的最小模型服务。"""


class NewLoader:
    """当前使用的新依赖接口。"""

    @classmethod
    def from_pretrained(cls, model_name: str) -> object:
        return object()


class ModelService:
    """通过新加载器初始化模型。"""

    def initialize(self) -> object:
        return NewLoader.from_pretrained("example/model")
