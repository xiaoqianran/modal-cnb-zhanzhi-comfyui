from .md import *
CATEGORY_TYPE = "🎈LAOGOU/Switch"
class LazySwitch2way:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "boolean": ("BOOLEAN", {"default": True}),
                "ON_TRUE": (any, {"lazy": True}),
                "on_true": (any, {"lazy": True}),
                "ON_FALSE": (any, {"lazy": True}),
                "on_false": (any, {"lazy": True}),
            }
        }
    
    RETURN_TYPES = (any, any,)
    RETURN_NAMES = ("OUTPUT", "output",)
    FUNCTION = "switch"
    CATEGORY = CATEGORY_TYPE

    def check_lazy_status(self, boolean, ON_TRUE, on_true, ON_FALSE, on_false):
        result = []
        if boolean:
            if ON_TRUE is None:
                result.append("ON_TRUE")
            if on_true is None:
                result.append("on_true")
        else:
            if ON_FALSE is None:
                result.append("ON_FALSE")
            if on_false is None:
                result.append("on_false")
        return result if result else None

    def switch(self, boolean, ON_TRUE, on_true, ON_FALSE, on_false):
        if boolean:
            return (ON_TRUE, on_true,)
        else:
            return (ON_FALSE, on_false,)

class LazySwitch1way:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "boolean": ("BOOLEAN", {"default": True}),
                "ON_TRUE": (any, {"lazy": True}),
                "ON_FALSE": (any, {"lazy": True}),
            }
        }
    
    RETURN_TYPES = (any,)
    RETURN_NAMES = ("OUTPUT",)
    FUNCTION = "switch"
    CATEGORY = CATEGORY_TYPE

    def check_lazy_status(self, boolean, ON_TRUE, ON_FALSE):
        result = []
        if boolean:
            if ON_TRUE is None:
                result.append("ON_TRUE")
        else:
            if ON_FALSE is None:
                result.append("ON_FALSE")
        return result if result else None

    def switch(self, boolean, ON_TRUE, ON_FALSE):
        if boolean:
            return (ON_TRUE,)
        else:
            return (ON_FALSE,)

class GroupSwitcher:
    """
    组切换节点，带有布尔值控制
    """
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "boolean": ("BOOLEAN", {"default": True}),  # 布尔值控制
            }
        }
    
    RETURN_TYPES = ()  # 无输出端口
    FUNCTION = "switch"
    CATEGORY = CATEGORY_TYPE

    def switch(self, boolean):

        return ()

class MuterSwitcher:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "boolean": ("BOOLEAN", {"default": True}),
            },
            "optional": {
                "ON_TRUE": (any,),
                "on_true": (any,),
                "ON_FALSE": (any,),
                "on_false": (any,),
            }
        }
    
    RETURN_TYPES = (any, any,)
    RETURN_NAMES = ("OUTPUT", "output",)
    FUNCTION = "switch"
    CATEGORY = CATEGORY_TYPE

    def switch(self, ON_TRUE=None, on_true=None, ON_FALSE=None, on_false=None, boolean=True):
        # 根据布尔值选择输出
        if boolean:
            return (ON_TRUE, on_true,)
        else:
            return (ON_FALSE, on_false,)

NODE_CLASS_MAPPINGS = {
    "LazySwitch2way": LazySwitch2way,
    "LazySwitch1way": LazySwitch1way,
    "GroupSwitcher": GroupSwitcher,
    "MuterSwitcher": MuterSwitcher,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "LazySwitch2way": "🎈LazySwitch2way",
    "LazySwitch1way": "🎈LazySwitch1way",
    "GroupSwitcher": "🎈GroupSwitcher",
    "MuterSwitcher": "🎈MuterSwitcher"
}


