import json
import os
import shlex
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from moss_cli import (  # noqa: E402
    FELIX, MFLUX, CliCancelled, CliFailed, CliNotFound,
    build_felix_args, build_mflux_args, find_bin, find_uv, generate, parse_progress, resolve_bin,
)

FAKE = Path(__file__).resolve().parent / "fake_cli.py"
FAKE_ENV = Path(__file__).resolve().parent / "fake_env.py"

P = dict(text='{"t": "今日こそ\\"完璧\\"なケーキ！"}\n2行目', negative_prompt="", seed=1, steps=30, cfg=5.0,
         width=640, height=2560, model="sft", quantize=8, turbo=True,
         lora_1="axiomofmind/Moss-image-nsfw-uncensored-lora:pytorch_lora_weights.safetensors", lora_1_strength=0.7,
         lora_2="  ", lora_2_strength=1.0)


def assert_subsequence(a, seq):
    n = len(seq)
    assert any(a[i:i + n] == seq for i in range(len(a) - n + 1)), f"{seq} not in {a}"


def pid_alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    # ゾンビは止まったものとみなす
    status = os.popen(f"ps -o stat= -p {pid}").read().strip()
    return bool(status) and not status.startswith("Z")


def after(seconds):
    t0 = time.monotonic()
    return lambda: time.monotonic() - t0 > seconds


class ArgsTest(unittest.TestCase):
    def test_build_mflux_args(self):
        a = build_mflux_args(P, Path("/t/p.txt"), Path("/t/o.png"))
        for seq in (["--model", "moss-image-sft"], ["-q", "8"], ["--prompt-file", "/t/p.txt"], ["--seed", "1"],
                    ["--steps", "30"], ["--guidance", "5.0"], ["--width", "640"], ["--height", "2560"],
                    ["--lora", P["lora_1"], "0.7"], ["--output", "/t/o.png"]):
            assert_subsequence(a, seq)
        self.assertNotIn("--negative-prompt", a)
        self.assertEqual(a.count("--lora"), 1)

    def test_build_mflux_args_base_model(self):
        a = build_mflux_args({**P, "model": "base"}, Path("/t/p.txt"), Path("/t/o.png"))
        assert_subsequence(a, ["--model", "moss-image-base"])

    def test_build_felix_args(self):
        a = build_felix_args({**P, "model": "8bit", "negative_prompt": "teen"}, Path("/t/o.png"))
        for seq in (["--model", "8bit"], ["--turbo"], ["--negative-prompt", "teen"],
                    ["--lora", P["lora_1"] + "@0.7"], ["-o", "/t/o.png"]):
            assert_subsequence(a, seq)
        self.assertEqual(a[-1], P["text"])

    def test_build_felix_args_without_turbo(self):
        a = build_felix_args({**P, "model": "compact", "turbo": False}, Path("/t/o.png"))
        self.assertNotIn("--turbo", a)

    def test_parse_progress(self):
        self.assertEqual(parse_progress(" 7%|▋         | 2/30 [01:05<15:12, 32.59s/it]"), (2, 30))
        self.assertEqual(parse_progress("step 3/10     76.8 s"), (3, 10))
        self.assertIsNone(parse_progress("Fetching 26 files:   4%|▍  | 1/26 [00:00<00:06,  3.61it/s]"))
        self.assertIsNone(parse_progress("INFO: Using prompt from file"))


class FindBinTest(unittest.TestCase):
    def test_find_bin_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(CliNotFound) as cm:
                find_bin(MFLUX, env={"PATH": ""}, home=Path(tmp))
            self.assertIn(MFLUX.name, str(cm.exception))

    def test_find_bin_local_bin(self):
        with tempfile.TemporaryDirectory() as tmp:
            b = Path(tmp) / ".local/bin/moss-mlx"
            b.parent.mkdir(parents=True)
            b.write_text("#!/bin/sh\n")
            b.chmod(0o755)
            self.assertEqual(find_bin(FELIX, env={"PATH": ""}, home=Path(tmp)), str(b))

    def test_find_bin_env_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            b = Path(tmp) / "custom"
            b.write_text("#!/bin/sh\n")
            b.chmod(0o755)
            self.assertEqual(find_bin(FELIX, env={"PATH": "", "MOSS_FELIX_BIN": str(b)}, home=Path(tmp)), str(b))


def script(path, target):
    path.write_text(f"#!/bin/sh\nexec {shlex.quote(sys.executable)} {shlex.quote(str(target))} \"$@\"\n")
    path.chmod(0o755)
    return str(path)


class ResolveBinTest(unittest.TestCase):
    """CLI が見つからないとき、ノード専用の仮想環境を作って入れる"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        self.home = self.d / "home"
        self.root = self.d / "node"
        self.home.mkdir()
        self.root.mkdir()
        self.uv = script(self.d / "uv", FAKE_ENV)
        self.python = script(self.d / "python3", FAKE_ENV)
        self.log = self.d / "env.log"
        self.saved = {k: os.environ.get(k) for k in ("FAKE_ENV_LOG", "FAKE_ENV_CLI", "FAKE_ENV_CLI_TARGET", "FAKE_ENV_FAIL")}
        os.environ.update(FAKE_ENV_LOG=str(self.log), FAKE_ENV_CLI="moss-mlx", FAKE_ENV_CLI_TARGET="/bin/echo")
        os.environ.pop("FAKE_ENV_FAIL", None)

    def tearDown(self):
        for k, v in self.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self.tmp.cleanup()

    def resolve(self, **kw):
        return resolve_bin(FELIX, env={"PATH": ""}, home=self.home, root=self.root,
                           **{"uv": self.uv, "python": self.python, "on_log": lambda s: None, **kw})

    def calls(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    def installs(self):
        return [c for c in self.calls() if "install" in c]

    def test_creates_venv_with_uv(self):
        b = self.resolve()
        self.assertEqual(b, str(self.root / ".venv-felix" / "bin" / "moss-mlx"))
        self.assertTrue(any(c.split()[1:3] == ["venv", str(self.root / ".venv-felix")] for c in self.calls()))
        self.assertTrue(any("--python 3.12" in c for c in self.calls() if " venv " in f" {c} "))
        self.assertTrue(self.installs()[0].endswith(FELIX.package))

    def test_reuses_existing_venv(self):
        self.resolve()
        self.resolve()
        self.assertEqual(len(self.installs()), 1)

    def test_recreates_when_package_changes(self):
        self.resolve()
        (self.root / ".venv-felix" / ".moss-installed").write_text("moss-image-mlx==0.1.0\n")
        self.resolve()
        self.assertEqual(len(self.installs()), 2)

    def test_recreates_when_python_is_broken(self):
        self.resolve()
        (self.root / ".venv-felix" / "bin" / "python").unlink()
        self.resolve()
        self.assertEqual(len(self.installs()), 2)

    def test_install_failure_raises_and_retries_next_time(self):
        os.environ["FAKE_ENV_FAIL"] = "install"
        with self.assertRaises(CliFailed) as cm:
            self.resolve()
        self.assertIn("no matching distribution", str(cm.exception))
        self.assertFalse((self.root / ".venv-felix" / ".moss-installed").exists())
        os.environ.pop("FAKE_ENV_FAIL")
        self.resolve()
        self.assertEqual(len(self.installs()), 2)

    def test_falls_back_to_python_venv_without_uv(self):
        self.resolve(uv=None)
        self.assertTrue(any(c.split()[1:3] == ["-m", "venv"] for c in self.calls()))
        self.assertTrue(any(c.split()[1:4] == ["-m", "pip", "install"] for c in self.calls()))

    def test_prefers_installed_cli(self):
        b = self.home / ".local/bin/moss-mlx"
        b.parent.mkdir(parents=True)
        script(b, FAKE_ENV)
        self.assertEqual(self.resolve(), str(b))
        self.assertEqual(self.calls(), [])

    def test_mflux_is_pinned_to_fixed_commit(self):
        self.assertIn("54619d6288a6c90dcdfbee7a9555382ae46ccb92", MFLUX.package)
        self.assertEqual(FELIX.package, "moss-image-mlx==0.2.0")

    def test_find_uv(self):
        self.assertEqual(find_uv({"PATH": "", "MOSS_UV": "/x/uv"}, candidates=()), "/x/uv")
        self.assertEqual(find_uv({"PATH": ""}, candidates=(self.uv,)), self.uv)
        self.assertIsNone(find_uv({"PATH": ""}, candidates=(str(self.d / "nope"),)))


class GenerateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        wrapper = d / "fake"
        wrapper.write_text(f"#!/bin/sh\nexec {shlex.quote(sys.executable)} {shlex.quote(str(FAKE))} \"$@\"\n")
        wrapper.chmod(0o755)
        self.log = d / "argv.json"
        self.child_pid = d / "child.pid"
        self.env = {"MOSS_MFLUX_BIN": str(wrapper), "MOSS_FELIX_BIN": str(wrapper),
                    "FAKE_ARGV_LOG": str(self.log), "FAKE_CHILD_PID": str(self.child_pid)}
        self.saved = {k: os.environ.get(k) for k in [*self.env, "FAKE_MODE"]}
        os.environ.update(self.env)

    def tearDown(self):
        for k, v in self.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self.tmp.cleanup()

    def mode(self, m):
        os.environ["FAKE_MODE"] = m

    def test_generate_ok_mflux(self):
        self.mode("ok")
        progress = []
        before = set(os.listdir(tempfile.gettempdir()))
        out = generate("mflux", P, on_progress=lambda c, t: progress.append((c, t)))
        try:
            self.assertTrue(out.read_bytes().startswith(b"\x89PNG"))
        finally:
            out.unlink()
        logged = json.loads(self.log.read_text(encoding="utf-8"))
        self.assertEqual(logged["prompt_file_content"], P["text"])
        self.assertEqual(progress, [(1, 2), (2, 2)])
        leftover = [n for n in set(os.listdir(tempfile.gettempdir())) - before if n.startswith("moss-mlx-")]
        self.assertEqual(leftover, [])

    def test_on_progress_runs_on_calling_thread(self):
        # ComfyUI の進捗フックは中断フラグを消費するので、should_cancel と同じスレッドで呼ぶ必要がある
        import threading
        self.mode("ok")
        threads = []
        out = generate("felix", P, on_progress=lambda c, t: threads.append(threading.current_thread()), poll=0.05)
        out.unlink()
        self.assertTrue(threads)
        self.assertTrue(all(t is threading.current_thread() for t in threads))

    def test_on_progress_exception_kills_cli(self):
        # ComfyUI の進捗フックが中断の例外を投げたときも、CLI を残さずに例外をそのまま上げる
        self.mode("hang_progress")

        class Interrupted(Exception):
            pass

        def hook(c, t):
            raise Interrupted()
        with self.assertRaises(Interrupted):
            generate("felix", P, on_progress=hook, poll=0.05)
        child = int(self.child_pid.read_text())
        deadline = time.monotonic() + 3
        while pid_alive(child) and time.monotonic() < deadline:
            time.sleep(0.1)
        self.assertFalse(pid_alive(child))

    def test_generate_ok_felix_passes_prompt_as_argument(self):
        self.mode("ok")
        out = generate("felix", P)
        out.unlink()
        logged = json.loads(self.log.read_text(encoding="utf-8"))
        self.assertEqual(logged["argv"][-1], P["text"])

    def test_generate_fail(self):
        self.mode("fail")
        with self.assertRaises(CliFailed) as cm:
            generate("felix", P)
        msg = str(cm.exception)
        self.assertIn("exit 3", msg)
        self.assertIn("line 29", msg)
        self.assertNotIn("line 5\n", msg + "\n")

    def test_generate_nopng(self):
        self.mode("nopng")
        with self.assertRaisesRegex(CliFailed, "PNG"):
            generate("felix", P)

    def test_cancel_kills_group(self):
        self.mode("hang")
        with self.assertRaises(CliCancelled):
            generate("felix", P, should_cancel=after(1.0), poll=0.1)
        child = int(self.child_pid.read_text())
        deadline = time.monotonic() + 3
        while pid_alive(child) and time.monotonic() < deadline:
            time.sleep(0.1)
        self.assertFalse(pid_alive(child))


if __name__ == "__main__":
    unittest.main()
