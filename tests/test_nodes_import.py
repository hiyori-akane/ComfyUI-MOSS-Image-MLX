import sys
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ComfyUI の外でも import できるよう、依存モジュールを空のスタブにする
for name in ("comfy", "comfy.model_management", "comfy.utils", "torch", "numpy", "PIL", "PIL.Image"):
    sys.modules.setdefault(name, types.ModuleType(name))

import nodes  # noqa: E402

COMMON = {"text", "negative_prompt", "seed", "steps", "cfg", "width", "height", "model",
          "lora_1", "lora_1_strength", "lora_2", "lora_2_strength"}


def required(cls):
    return cls.INPUT_TYPES()["required"]


class NodesTest(unittest.TestCase):
    def test_mappings(self):
        self.assertEqual(set(nodes.NODE_CLASS_MAPPINGS), {"MossImageMflux", "MossImageFelix"})
        self.assertEqual(nodes.NODE_DISPLAY_NAME_MAPPINGS,
                         {"MossImageMflux": "MOSS Image (mflux)", "MossImageFelix": "MOSS Image (felix)"})

    def test_input_names_are_frozen(self):
        self.assertEqual(set(required(nodes.MossImageMflux)), COMMON | {"quantize"})
        self.assertEqual(set(required(nodes.MossImageFelix)), COMMON | {"turbo"})
        self.assertEqual(nodes.MossImageMflux.RETURN_TYPES, ("IMAGE",))
        self.assertEqual(nodes.MossImageFelix.RETURN_TYPES, ("IMAGE",))

    def test_defaults(self):
        m, f = required(nodes.MossImageMflux), required(nodes.MossImageFelix)
        self.assertEqual(m["model"][0], ["sft", "base"])
        self.assertEqual(m["model"][1]["default"], "sft")
        self.assertEqual(m["quantize"][1]["default"], "8")
        self.assertEqual(f["model"][0], ["8bit", "compact"])
        self.assertIs(f["turbo"][1]["default"], True)
        for r in (m, f):
            self.assertEqual(r["seed"][1]["default"], 1)
            self.assertEqual(r["steps"][1]["default"], 30)
            self.assertEqual(r["cfg"][1]["default"], 5.0)
            self.assertEqual(r["width"][1]["default"], 1024)
            self.assertEqual(r["lora_1_strength"][1]["default"], 0.7)
            self.assertEqual(r["lora_2_strength"][1]["default"], 1.0)


if __name__ == "__main__":
    unittest.main()
