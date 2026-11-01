"""MOSS-Image の MLX 版 CLI（mflux / felix 版）を子プロセスで呼ぶ。ComfyUI には依存しない。"""
import collections
import queue
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping


@dataclass(frozen=True)
class CliSpec:
    key: str
    name: str
    env: str
    package: str  # ノード専用の仮想環境に入れるもの（版を固定する）


# mflux は PyPI の 0.24.0 だと長いプロンプトで NaN（真っ黒）になる。修正の入った main のコミットに固定する
MFLUX = CliSpec("mflux", "mflux-generate-moss-image", "MOSS_MFLUX_BIN",
                "mflux @ git+https://github.com/mflux-community/mflux@54619d6288a6c90dcdfbee7a9555382ae46ccb92")
FELIX = CliSpec("felix", "moss-mlx", "MOSS_FELIX_BIN", "moss-image-mlx==0.2.0")

NODE_DIR = Path(__file__).resolve().parent
# Comfy Desktop に同梱されている uv
DESKTOP_UV = ("/Applications/Comfy Desktop.app/Contents/Resources/bootstrap-python/bin/uv",)
VENV_PYTHON = "3.12"  # uv で作るときの Python。ComfyUI の Python が更新されても影響を受けない
MARKER = ".moss-installed"
_AUTO = object()  # resolve_bin の uv を自動で探す印


class CliNotFound(RuntimeError):
    pass


class CliFailed(RuntimeError):
    pass


class CliCancelled(RuntimeError):
    pass


def find_bin(spec: CliSpec, env: Mapping[str, str] = os.environ, home: Path = Path.home()) -> str:
    """環境変数 → PATH → ~/.local/bin の順に探す。ComfyUI デスクトップ版の PATH には ~/.local/bin が無いことがある。"""
    if env.get(spec.env):
        return env[spec.env]
    found = shutil.which(spec.name, path=env.get("PATH", ""))
    if found:
        return found
    local = home / ".local" / "bin" / spec.name
    if local.is_file() and os.access(local, os.X_OK):
        return str(local)
    raise CliNotFound(f"{spec.name} が見つかりません")


def find_uv(env: Mapping[str, str] = os.environ, candidates: tuple[str, ...] = DESKTOP_UV) -> str | None:
    """環境変数 MOSS_UV → PATH → Comfy Desktop 同梱の uv の順に探す"""
    if env.get("MOSS_UV"):
        return env["MOSS_UV"]
    found = shutil.which("uv", path=env.get("PATH", ""))
    if found:
        return found
    return next((c for c in candidates if os.access(c, os.X_OK)), None)


def ensure_venv(spec: CliSpec, root: Path, *, uv: str | None, python: str = sys.executable,
                on_log: Callable[[str], None] = print) -> str:
    """root/.venv-<key> に CLI を入れて、そのパスを返す。入れ終わった印（MARKER）が無いか、
    中身が違うか、python が動かなければ作り直す。ComfyUI の Python 環境には何も入れない。"""
    venv = root / f".venv-{spec.key}"
    py, cli, marker = venv / "bin" / "python", venv / "bin" / spec.name, venv / MARKER
    if marker.is_file() and marker.read_text().strip() == spec.package and cli.is_file() and _runs(py):
        return str(cli)
    on_log(f"[MOSS Image] {spec.name} をノード専用の環境に入れます（初回のみ、数分かかります）: {venv}")
    shutil.rmtree(venv, ignore_errors=True)
    if uv:
        steps = [[uv, "venv", str(venv), "--python", VENV_PYTHON],
                 [uv, "pip", "install", "--python", str(py), spec.package]]
    else:
        steps = [[python, "-m", "venv", str(venv)],
                 [str(py), "-m", "pip", "install", spec.package]]
    for argv in steps:
        r = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace")
        for line in r.stdout.splitlines():
            on_log(f"[MOSS Image] {line}")
        if r.returncode != 0:
            tail = "\n".join(r.stdout.splitlines()[-20:])
            raise CliFailed(f"{spec.name} を入れられませんでした（{' '.join(argv[:3])}、exit {r.returncode}）:\n{tail}")
    if not cli.is_file():
        raise CliFailed(f"{spec.package} を入れましたが、{cli} がありません")
    marker.write_text(spec.package + "\n")
    on_log(f"[MOSS Image] {spec.name} を入れました")
    return str(cli)


def _runs(py: Path) -> bool:
    try:
        return subprocess.run([str(py), "-c", ""], capture_output=True, timeout=30).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def resolve_bin(spec: CliSpec, *, env: Mapping[str, str] = os.environ, home: Path | None = None,
                root: Path = NODE_DIR, uv=_AUTO, python: str = sys.executable,
                on_log: Callable[[str], None] = print) -> str:
    """入っている CLI があればそれを、無ければノード専用の仮想環境を作って使う"""
    try:
        return find_bin(spec, env=env, home=home or Path.home())
    except CliNotFound:
        return ensure_venv(spec, root, uv=find_uv(env) if uv is _AUTO else uv, python=python, on_log=on_log)


def _common(p: dict) -> list[str]:
    a = []
    if p["negative_prompt"].strip():
        a += ["--negative-prompt", p["negative_prompt"]]
    a += ["--seed", str(p["seed"]), "--steps", str(p["steps"]), "--guidance", str(p["cfg"]),
          "--width", str(p["width"]), "--height", str(p["height"])]
    return a


def _loras(p: dict) -> list[tuple[str, float]]:
    return [(p[f"lora_{i}"].strip(), p[f"lora_{i}_strength"]) for i in (1, 2) if p[f"lora_{i}"].strip()]


def build_mflux_args(p: dict, prompt_file: Path, output: Path) -> list[str]:
    a = ["--model", f"moss-image-{p['model']}", "-q", str(p["quantize"]), "--prompt-file", str(prompt_file), *_common(p)]
    for path, strength in _loras(p):
        a += ["--lora", path, str(strength)]
    return a + ["--output", str(output)]


def build_felix_args(p: dict, output: Path) -> list[str]:
    a = ["--model", p["model"], *_common(p)]
    if p["turbo"]:
        a.append("--turbo")
    for path, strength in _loras(p):
        a += ["--lora", f"{path}@{strength}"]
    # プロンプトは位置引数。"-" で始まる JSON でも引数と取り違えないよう -- の後に置く
    return a + ["-o", str(output), "--", p["text"]]


# mflux は tqdm（" 7%|▋ | 2/30 [01:05<..."）、felix 版は "step 3/10  76.8 s"。ダウンロードの "Fetching N files" は無視する
_TQDM = re.compile(r"^\s*\d+%\|[^|]*\|\s*(\d+)/(\d+)\s*\[")
_STEP = re.compile(r"^\s*step\s+(\d+)/(\d+)\b")


def parse_progress(line: str) -> tuple[int, int] | None:
    m = _STEP.match(line) or _TQDM.match(line)
    return (int(m[1]), int(m[2])) if m else None


def run_cli(argv: list[str], *, on_progress: Callable[[int, int], None] = lambda c, t: None,
            should_cancel: Callable[[], bool] = lambda: False, poll: float = 0.5) -> None:
    proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True,
                            env={**os.environ, "PYTHONUNBUFFERED": "1"})
    tail = collections.deque(maxlen=20)
    # 進捗はキューに置き、呼び出し側のスレッドで on_progress に渡す。
    # ComfyUI の進捗フックは中断フラグを消費して例外を投げるので、別スレッドで呼ぶとキャンセルが失われる
    progress = queue.SimpleQueue()

    def report():
        while not progress.empty():
            on_progress(*progress.get())

    def read():
        buf = b""
        while chunk := proc.stdout.read1(4096):
            buf += chunk
            *lines, buf = re.split(rb"[\r\n]", buf)
            for raw in lines:
                line = raw.decode(errors="replace")
                if line.strip():
                    tail.append(line)
                    if (pr := parse_progress(line)):
                        progress.put(pr)
        if buf.strip():
            tail.append(buf.decode(errors="replace"))

    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    try:
        while proc.poll() is None:
            report()
            if should_cancel():
                _kill_group(proc)
                reader.join(timeout=1)
                raise CliCancelled("キャンセルしました")
            time.sleep(poll)
        reader.join(timeout=5)
        report()
    except BaseException:
        # on_progress が投げた例外（ComfyUI の中断など）でも CLI を残さない
        _kill_group(proc)
        raise
    finally:
        proc.stdout.close()
    if proc.returncode != 0:
        raise CliFailed(f"{Path(argv[0]).name} が失敗しました（exit {proc.returncode}）:\n" + "\n".join(tail))


def _kill_group(proc: subprocess.Popen) -> None:
    for sig, wait in ((signal.SIGTERM, 5), (signal.SIGKILL, 5)):
        try:
            os.killpg(proc.pid, sig)
        except ProcessLookupError:
            return
        try:
            proc.wait(timeout=wait)
            # 親が先に終わっても、孫が同じグループに残っていれば止める
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            return
        except subprocess.TimeoutExpired:
            continue
        return


def generate(kind: str, p: dict, **run_kw) -> Path:
    """CLI で1枚作り、PNG の一時ファイルのパスを返す。消すのは呼び出し側。"""
    with tempfile.TemporaryDirectory(prefix="moss-mlx-") as d:
        out = Path(d) / "out.png"
        if kind == "mflux":
            prompt_file = Path(d) / "prompt.txt"
            prompt_file.write_text(p["text"], encoding="utf-8")
            argv = [resolve_bin(MFLUX), *build_mflux_args(p, prompt_file, out)]
        elif kind == "felix":
            argv = [resolve_bin(FELIX), *build_felix_args(p, out)]
        else:
            raise ValueError(kind)
        run_cli(argv, **run_kw)
        if not out.is_file():
            raise CliFailed(f"{Path(argv[0]).name} は正常に終わりましたが、PNG が出力されていません")
        fd, result = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        shutil.move(out, result)
        return Path(result)
