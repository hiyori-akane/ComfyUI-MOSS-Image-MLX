"""MOSS-Image の MLX 版（mflux / felix 版）を呼ぶ ComfyUI ノード。

クラス名と入力名は、保存された PNG の prompt（API 形式のグラフ）に残る。変えると、
取り込み済みの画像を再生成できなくなるので変えない。入力を足すときは既定値を必ず付ける。
"""
import comfy.model_management as mm
import comfy.utils
import numpy as np
import torch
from PIL import Image

try:
    from .moss_cli import CliCancelled, generate
except ImportError:  # テストから直接 import したとき
    from moss_cli import CliCancelled, generate

CATEGORY = "MOSS Image (MLX)"


def _inputs(models: list[str], extra: dict) -> dict:
    return {"required": {
        "text": ("STRING", {"multiline": True, "default": ""}),
        "negative_prompt": ("STRING", {"multiline": True, "default": ""}),
        "seed": ("INT", {"default": 1, "min": 0, "max": 0xFFFFFFFFFFFFFFFF}),
        "steps": ("INT", {"default": 30, "min": 1, "max": 200}),
        "cfg": ("FLOAT", {"default": 5.0, "min": 0.0, "max": 20.0, "step": 0.1}),
        "width": ("INT", {"default": 1024, "min": 64, "max": 4096, "step": 16}),
        "height": ("INT", {"default": 1024, "min": 64, "max": 4096, "step": 16}),
        "model": (models, {"default": models[0]}),
        **extra,
        "lora_1": ("STRING", {"default": ""}),
        "lora_1_strength": ("FLOAT", {"default": 0.7, "min": -2.0, "max": 2.0, "step": 0.05}),
        "lora_2": ("STRING", {"default": ""}),
        "lora_2_strength": ("FLOAT", {"default": 1.0, "min": -2.0, "max": 2.0, "step": 0.05}),
    }}


def _run(kind: str, p: dict):
    # MLX は統合メモリを使うので、ComfyUI が持っているモデルを先に解放する
    mm.unload_all_models()
    mm.soft_empty_cache()
    bar = comfy.utils.ProgressBar(p["steps"])
    try:
        path = generate(kind, p, on_progress=lambda c, t: bar.update_absolute(c, t),
                        should_cancel=mm.processing_interrupted)
    except CliCancelled:
        mm.throw_exception_if_processing_interrupted()
        raise
    try:
        with Image.open(path) as img:
            arr = np.asarray(img.convert("RGB"), dtype=np.float32) / 255.0
    finally:
        path.unlink(missing_ok=True)
    return (torch.from_numpy(arr)[None],)


class MossImageMflux:
    """mflux main の mflux-generate-moss-image を呼ぶ。LoRA が使え、品質を優先したいとき向け。"""
    CATEGORY = CATEGORY
    FUNCTION = "generate"
    RETURN_TYPES = ("IMAGE",)

    @classmethod
    def INPUT_TYPES(cls):
        return _inputs(["sft", "base"], {"quantize": (["8", "6", "5", "4", "3"], {"default": "8"})})

    def generate(self, **p):
        return _run("mflux", p)


class MossImageFelix:
    """felix 版（moss-image-mlx）の moss-mlx を呼ぶ。メモリが少なくても動き、turbo で速い。"""
    CATEGORY = CATEGORY
    FUNCTION = "generate"
    RETURN_TYPES = ("IMAGE",)

    @classmethod
    def INPUT_TYPES(cls):
        return _inputs(["8bit", "compact"], {"turbo": ("BOOLEAN", {"default": True})})

    def generate(self, **p):
        return _run("felix", p)


NODE_CLASS_MAPPINGS = {"MossImageMflux": MossImageMflux, "MossImageFelix": MossImageFelix}
NODE_DISPLAY_NAME_MAPPINGS = {"MossImageMflux": "MOSS Image (mflux)", "MossImageFelix": "MOSS Image (felix)"}
