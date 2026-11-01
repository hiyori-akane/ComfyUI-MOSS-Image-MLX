# ComfyUI-MOSS-Image-MLX

[MOSS-Image](https://github.com/OpenMOSS/MOSS-Image) を Apple Silicon の Mac で動かす、MLX 版の CLI を呼ぶ ComfyUI カスタムノードです。

| ノード | 呼ぶ CLI | 向いている用途 |
|---|---|---|
| `MOSS Image (mflux)` | [mflux](https://github.com/mflux-community/mflux) の `mflux-generate-moss-image` | LoRA を使いたい、品質を優先したい |
| `MOSS Image (felix)` | [moss-image-mlx](https://github.com/felix-ab/moss-image-mlx) の `moss-mlx` | メモリが少ない Mac、turbo で速く作りたい |

出力は `IMAGE` です。標準の **SaveImage** につなぐと、PNG にグラフ（`prompt`）が入ります。そのため、ComfyUI の画面や API から、seed などを変えてやり直せます。

## 前提

- Apple Silicon の Mac（MLX が必要です）
- ComfyUI（デスクトップ版で確認しました）

## 入れる

ComfyUI の `custom_nodes/` で clone して、ComfyUI を再起動します。

```sh
cd ~/ComfyUI/custom_nodes   # ComfyUI の custom_nodes フォルダ
git clone https://github.com/hiyori-akane/ComfyUI-MOSS-Image-MLX.git
```

ノードは「MOSS Image (MLX)」の分類に出ます。CLI を別に入れる必要はありません。

### CLI は初回の実行時に自動で入る

ノードを初めて実行すると、ノードのフォルダの中にノード専用の Python 環境（`.venv-mflux/`、`.venv-felix/`）を作り、CLI を入れます。

- 入るもの：mflux は修正の入った main のコミット（`54619d6`）、felix 版は `moss-image-mlx==0.2.0`。PyPI の mflux 0.24.0 は、長いプロンプト（4コマの JSON など）で真っ黒になるためです。
- ComfyUI の Python 環境には何も入れません。felix 版の `transformers>=5.3` などが、ComfyUI や他のカスタムノードとぶつからないようにするためです。
- 環境は [uv](https://docs.astral.sh/uv/) で作ります（Python 3.12）。uv は Comfy Desktop に同梱されています。uv が無いときは、ComfyUI の Python（3.11 以上が必要）の `venv` と `pip` で作ります。
- 初回はパッケージの取得に数分かかります。様子は ComfyUI のログに出ます。モデルの重みは、さらに CLI が初回に Hugging Face から取ってきます。
- 環境が壊れたとき（基になる Python が消えたなど）は、次の実行で作り直します。手で作り直すなら `.venv-*` フォルダを消します。

### 自分で入れた CLI を使う

自分で入れた CLI があれば、そちらを使います。ノードは次の順に探し、どこにも無いときだけ専用の環境を作ります。

1. 環境変数 `MOSS_MFLUX_BIN` / `MOSS_FELIX_BIN`（CLI のフルパス）
2. `PATH`
3. `~/.local/bin`（`uv tool install` の既定の場所）

uv の場所は、環境変数 `MOSS_UV` で指定できます。

## 使い方

`MOSS Image (mflux)` か `MOSS Image (felix)` の出力を、SaveImage につなぎます。

| 入力 | mflux | felix 版 | メモ |
|---|---|---|---|
| `text` | ○ | ○ | プロンプト。4コマなどの JSON もそのまま入れる |
| `negative_prompt` | ○ | ○ | 空なら使わない |
| `seed` / `steps` / `cfg` / `width` / `height` | ○ | ○ | felix 版の turbo では、steps は CLI が無視する |
| `model` | `sft` / `base` | `8bit` / `compact` | felix 版の `compact` は 24GB 未満の Mac 向け |
| `quantize` | 8 / 6 / 5 / 4 / 3 | — | 既定 8 |
| `turbo` | — | ○ | 既定オン |
| `lora_1` / `lora_2` と強さ | ○ | ○ | 空なら使わない。mflux は `repo:ファイル名`（Hugging Face）かパス。felix 版は kohya 形式のファイルのパス |

- 実行の前に、ComfyUI が持っているモデルを解放します。MLX が統合メモリを使うためです。
- 実行中に ComfyUI でキャンセルすると、CLI のプロセスを止めます。
- 初回はモデルの重みを Hugging Face から取ってきます（数十 GB、時間がかかります）。felix 版の重みは [`VisualInference/MOSS-Image-SFT-MLX-8bit`](https://huggingface.co/VisualInference/MOSS-Image-SFT-MLX-8bit) です。重みのライセンスは各配布元で確認してください。

## 実測（M1 Max 64GB）

| ノード | 条件 | 4コマ 640x2560 | ピークメモリ |
|---|---|---|---|
| mflux | main、q8、30 steps | 約16.5分 | 29.6GB |
| felix 版 | 8bit、turbo | 約4.4分 | 11.1GB |

## クラス名と入力名を変えない理由

クラス名（`MossImageMflux` / `MossImageFelix`）と入力名は、SaveImage が PNG に入れるグラフに残ります。変えると、それまでに作った画像のグラフを ComfyUI に送り直せなくなります。入力を足すことはできます（既定値を必ず付けます）。

## テスト

偽の CLI を使うので、MLX が無い環境でも動きます。

```sh
python3 -m unittest discover -s tests -v
```

## 動作確認

M1 Max 64GB、ComfyUI デスクトップ版で確かめました。

- 日本語のセリフ入り4コマ（640x2560）を、両方のノードで生成できた（4つのセリフがすべて正しく出た）
- PNG にグラフが入り、seed を変えて送り直すと、同じ設定で作り直せた
- 実行中にキャンセルすると、CLI のプロセスも止まった

## ライセンス

MIT（[LICENSE](./LICENSE)）。mflux は MIT、moss-image-mlx は Apache-2.0 です。
