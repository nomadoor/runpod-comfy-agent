# RunPod Comfy Agent

RunPod上のComfyUIを、ローカルPC / VSCode / AIエージェントから操作するためのCLIツールです。

ComfyUI workflowを用意すると、そのworkflowに合わせてPodを作成し、必要モデルのダウンロード、画像生成、生成物の回収、PodのterminateまでをAIエージェントに実行させられます。

事前に作成したworkflowをAIエージェントに使用させ、RunPod上で複数回の生成を行うための小さな運用基盤として使用します。

## 全体像

```text
 人間
  |  workflow / GPU候補 / Docker image / API keyを用意
  v
 ローカルPC
  |
  |  start_session.py
  |    - RunPod APIでPodを作成
  |    - workflow API JSONを読んで必要モデルを判定
  |    - Pod起動コマンドにモデルダウンロード処理を追加
  |
  v
 RunPod Pod
  |
  |  Docker image:
  |    nomadoor/runpod-comfy-agent:latest
  |
  |  起動後:
  |    /opt/ComfyUI を起動
  |    /workspace/comfy-agent-model-download.log にモデルダウンロードログを出力
  |
  v
 ComfyUI API :8188
  ^
  |
  |  run_workflow.py
  |    - workflowにprompt / seed等のpatchを当てる
  |    - ComfyUIへ送信
  |    - 生成画像をローカルへ回収
  |
 ローカルPC
  |
  v
 sessions/<session_id>/images/
```

## 使い方

このリポジトリは、人間がworkflowと実行方針を決め、AIエージェントがRunPod上のComfyUI実行を進めるための作業台です。

- RunPodのAPI keyを取得し、このPCの環境変数または `.env` に設定します。
- ComfyUIで作成したworkflow API JSONを `workflows/` に配置します。
- Claude Code / Codex などのAIエージェントに、使用するworkflow、生成したい内容、枚数、変更したいprompt / seed / parameterを指示します。
- 必要に応じて、使用するGPU方針もAIエージェントに指示します。標準profileは `l4` / `l40s` / `a100` です。
- AIエージェントは指示に合わせて `config/profiles.json` を確認し、このリポジトリのCLIを使ってPod作成、モデル判定とダウンロード、workflow実行、画像回収、必要に応じた再実行を行います。
- 必要に応じて、Podを複数同時に立ち上げ、並列で生成させることもできます。
- 作業終了時は、AIエージェントがPodをterminateし、削除漏れがないかreaperで確認します。

## 役割分担

```text
人間が決定する項目
  - どのworkflowを使うか
  - どのGPU候補を許すか
  - 最大実行時間とコスト上限 (デフォルトで2時間)
  - Docker image名
  - RunPod API key
  - 未登録モデルURLを追加してよいか

AIエージェントが実行する項目
  - workflow API JSONを読む
  - 既存ノードのprompt / seed / steps等を編集した一時workflowを作成する
  - このリポジトリのCLIを使ってPodを起動・実行・終了する
  - 画像とログを確認して次のrun specを作成する

AIエージェントの境界
  - RunPod API keyは人間が設定し、AIエージェントは値を扱わない
  - Pod操作はこのリポジトリのCLI経由に統一する
  - GPU profileは人間が選んだものを使う
  - workflowに書かれているモデル名を正として扱う
  - 元のworkflow API JSONはテンプレートとして残す
```

AIエージェント向けの短い運用ルールは [skills/runpod-comfy-agent/SKILL.md](skills/runpod-comfy-agent/SKILL.md) にあります。

## Docker image

デフォルトでは、以下のDocker imageが使用されます。

```text
nomadoor/runpod-comfy-agent:latest
```

imageには、ComfyUIを動作させるための最小構成が含まれます。

```text
CUDA 13.0 runtime
PyTorch cu130
ComfyUI
```

このimageはComfyUI API用です。workflowで使うモデルは、Pod起動時にworkflow API JSONから判定して `/opt/ComfyUI/models/...` へ配置されます。

RunPodで使用するimage名は、`config/profiles.json` の `pod.imageName` に指定します。

```json
{
  "pod": {
    "imageName": "nomadoor/runpod-comfy-agent:latest"
  }
}
```

imageを更新する場合は、以下の手順でbuild / pushします。

```bash
docker build -f docker/Dockerfile -t nomadoor/runpod-comfy-agent:latest .
docker push nomadoor/runpod-comfy-agent:latest
```

RunPodは、Docker Hubにpush済みのimageをpullしてPodを起動します。imageを更新した場合は `docker push` まで完了させ、`config/profiles.json` の `pod.imageName` が対象tagを指すようにします。

## API key

RunPod API keyは、環境変数または `.env` で設定します。

```bash
export RUNPOD_API_KEY=...
```

または、リポジトリ直下の `.env` に設定します。

```text
RUNPOD_API_KEY=...
```

CLIは環境変数を優先し、環境変数が未設定の場合に `.env` を読み込みます。`.env` はローカル専用の認証ファイルとして扱います。

## Pod / GPU設定

Pod設定は `config/profiles.json` に記述します。初回はexampleをコピーして作成します。

```bash
cp config/profiles.example.json config/profiles.json
```

主な設定箇所は以下です。

```json
{
  "profiles": {
    "l4": {
      "max_runtime_minutes": 120,
      "max_cost_per_hour": 0.8,
      "model_ready_timeout_seconds": 3600,
      "pod": {
        "allowedCudaVersions": ["13.0"],
        "gpuTypeIds": ["NVIDIA L4"],
        "gpuTypePriority": "availability",
        "gpuCount": 1,
        "containerDiskInGb": 80,
        "volumeInGb": 80,
        "imageName": "nomadoor/runpod-comfy-agent:latest",
        "ports": ["8188/http"]
      }
    }
  }
}
```

標準profileは `l4` / `l40s` / `a100` です。`gpuTypeIds` には、RunPod APIが受け付けるGPU名をそのまま指定します。

```text
l4    -> NVIDIA L4
l40s  -> NVIDIA L40S
a100  -> NVIDIA A100 80GB PCIe
```

`max_cost_per_hour` は現在価格ではなく、課金事故を避けるための上限ガードです。RunPod側の価格がこの値を超えて返ってきた場合、CLIは作成したPodをterminateして処理を停止します。

`max_runtime_minutes` はローカル側の安全設定です。作業終了時は `end_session.py` でPodをterminateします。

## モデルのダウンロード

Pod起動時にworkflow API JSONを読み取り、必要なモデルをPod内へダウンロードします。

```text
start_session.py --workflow-json workflows/Z-Image-Turbo.json
  |
  v
 workflow内のLoaderノードを確認
  |
  v
 comfy_agent/workflow_requirements.py の MODEL_REGISTRY と照合
  |
  v
 Pod起動後に /opt/ComfyUI/models/... へ curl でダウンロード
  |
  v
 ComfyUIのLoader一覧に必要モデルが出るまで start_session.py が待機
```

現在、自動判定に使用する主なLoaderは以下です。

```text
UNETLoader.unet_name
CLIPLoader.clip_name
DualCLIPLoader.clip_name1
DualCLIPLoader.clip_name2
TripleCLIPLoader.clip_name1
TripleCLIPLoader.clip_name2
TripleCLIPLoader.clip_name3
VAELoader.vae_name
LoraLoader.lora_name
CheckpointLoaderSimple.ckpt_name
```

workflowに記載されたモデルが `MODEL_REGISTRY` に未登録の場合、CLIはPod作成前に停止してモデル名を表示します。その場合は、人間がモデルURLを確認してから `comfy_agent/workflow_requirements.py` に追加します。

モデルダウンロードは、基本的にバックグラウンドで実行されます。ComfyUI自体は先に起動しますが、`start_session.py` はworkflowで必要なモデルがComfyUIのLoader一覧に反映されるまで待機します。

Pod内のモデルダウンロードログ:

```text
/workspace/comfy-agent-model-download.log
```

## 出力場所

確認用の生成画像は、以下に集約されます。

```text
sessions/<session_id>/images/
```

runごとの詳細は以下に保存されます。

```text
sessions/<session_id>/runs/<run_id>/
  README.md
  images/
  inputs/
  artifacts/
    run_spec_used.json
    workflow_used.json
    payload.json
    history.json
    timing.json
```

`workflow_used.json` は実行に使ったworkflowです。元の `workflows/...` はテンプレートとして残します。

## Batch

複数のrun specを順番に実行する場合は、`jobs.jsonl` と `run_batch.py` を使います。

```bash
python3 bin/run_batch.py --jobs jobs.jsonl
```

`run_batch.py` は現在のsession上のComfyUIへjobを順番に投入し、`manifest.jsonl` に `running` / `done` / `failed` を記録します。同じbatch directoryで再実行すると、最新statusが `done` のjobはskipされます。

最初のbatch実装は1 Podでの逐次実行です。複数Podへの分散は、manifest/resumeの運用が安定してから追加します。

## 状態確認と終了

状態確認:

```bash
python3 bin/session_status.py
python3 bin/session_status.py --watch 10
python3 bin/session_status.py --json
```

終了:

```bash
python3 bin/end_session.py --yes
python3 bin/reap_sessions.py --include-orphans
```

`reap_sessions.py --include-orphans` は、ローカルsessionに残っていないPodもRunPod側のPod一覧から探します。削除漏れ対策です。

## 詳細ドキュメント

- [セットアップ](docs/RUNPOD_SETUP.md)
- [run spec](docs/RUN_SPEC.md)
- [batch](docs/BATCH.md)
