"""テスト用の偽の uv / python。仮想環境を作るコマンドだけを真似る。

  uv venv <dir> --python <py>             → <dir>/bin/python を作る
  uv pip install --python <py> <pkg>      → <py> の隣に CLI を作る
  python -m venv <dir>                    → uv venv と同じ
  python -m pip install <pkg>             → uv pip install と同じ（python は自分自身）

FAKE_ENV_LOG に呼ばれた argv を1行ずつ追記する。FAKE_ENV_FAIL=install なら install で失敗する。
FAKE_ENV_CLI に、作る CLI の名前を入れる。CLI の中身は FAKE_ENV_CLI_TARGET を exec するだけ。
"""
import os
import sys
from pathlib import Path

argv = sys.argv[1:]
with open(os.environ["FAKE_ENV_LOG"], "a", encoding="utf-8") as f:
    f.write(" ".join([Path(sys.argv[0]).name, *argv]) + "\n")


def make_venv(d):
    b = Path(d) / "bin"
    b.mkdir(parents=True, exist_ok=True)
    py = b / "python"
    # 仮想環境の python も、この偽のスクリプトとして動かす
    py.write_text(f"#!/bin/sh\nFAKE_ENV_SELF={py} exec {sys.executable} {Path(__file__).resolve()} \"$@\"\n")
    py.chmod(0o755)


def install(py):
    if os.environ.get("FAKE_ENV_FAIL") == "install":
        print("error: no matching distribution", file=sys.stderr)
        sys.exit(1)
    cli = Path(py).parent / os.environ["FAKE_ENV_CLI"]
    cli.write_text(f"#!/bin/sh\nexec {os.environ['FAKE_ENV_CLI_TARGET']} \"$@\"\n")
    cli.chmod(0o755)


if argv[:1] == ["venv"]:
    make_venv(argv[1])
elif argv[:2] == ["pip", "install"]:
    install(argv[argv.index("--python") + 1])
elif argv[:2] == ["-m", "venv"]:
    make_venv(argv[2])
elif argv[:3] == ["-m", "pip", "install"]:
    install(os.environ["FAKE_ENV_SELF"])
elif argv[:1] == ["-c"]:
    pass  # 健全性の確認
else:
    sys.exit(f"unexpected: {argv}")
