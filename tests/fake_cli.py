"""テスト用の偽の CLI。mflux-generate-moss-image / moss-mlx の代わりに動く。

FAKE_MODE で動作を変える:
  ok    進捗を2行出し、出力先に 1x1 の PNG を書いて 0 で終わる
  fail  30 行出して 3 で終わる
  nopng 何も書かずに 0 で終わる
  hang  子プロセスを1つ作り、両方とも眠る（子の PID を FAKE_CHILD_PID に書く）
  hang_progress  hang と同じだが、眠る前に進捗を1行出す
"""
import base64
import json
import os
import subprocess
import sys
import time

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4z8AAAAMBAQDJ/pLvAAAAAElFTkSuQmCC")

argv = sys.argv[1:]


def value(*names):
    for n in names:
        if n in argv:
            return argv[argv.index(n) + 1]
    return None


log = {"argv": argv}
prompt_file = value("--prompt-file")
if prompt_file:
    with open(prompt_file, encoding="utf-8") as f:
        log["prompt_file_content"] = f.read()
if os.environ.get("FAKE_ARGV_LOG"):
    with open(os.environ["FAKE_ARGV_LOG"], "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False)

mode = os.environ.get("FAKE_MODE", "ok")
if mode == "ok":
    for i in (1, 2):
        print(f"step {i}/2     0.1 s", flush=True)
    with open(value("-o", "--output"), "wb") as f:
        f.write(PNG)
elif mode == "fail":
    for i in range(30):
        print(f"line {i}", file=sys.stderr, flush=True)
    sys.exit(3)
elif mode in ("hang", "hang_progress"):
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    with open(os.environ["FAKE_CHILD_PID"], "w") as f:
        f.write(str(child.pid))
    if mode == "hang_progress":
        print("step 1/10     0.1 s", flush=True)
    time.sleep(60)
