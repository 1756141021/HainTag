"""Parser plugins for different AI image generators."""

from .a1111 import A1111Parser
from .comfyui import ComfyUIParser
from .fooocus import FooocusParser
from .novelai import NovelAIParser

__all__ = ["A1111Parser", "ComfyUIParser", "FooocusParser", "NovelAIParser"]
