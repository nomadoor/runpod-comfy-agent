# RunPod セットアップ

RunPodのPod操作は、すべてこのリポジトリのCLI越しに行います。

```bash
python3 bin/start_session.py --profile l4 --workflow-json workflows/<workflow_api_json>
python3 bin/run_workflow.py --spec runspecs/<run_spec_json>
python3 bin/session_status.py --watch 10
python3 bin/end_session.py --yes
python3 bin/reap_sessions.py --include-orphans
```

共通処理は `comfy_agent/`、CLIは `bin/` にあります。

## 設定

profileを作ります。

```bash
cp config/profiles.example.json config/profiles.json
```

`config/profiles.json` はローカル運用設定です。実際のimage名、GPU候補、diskサイズなどはここで調整します。

RunPod API keyは環境変数か `.env` で設定します。

```bash
RUNPOD_API_KEY=...
```

`.env` はローカル専用の認証ファイルとして扱います。

## Docker image

このリポジトリのDocker imageはComfyUI API用です。

```bash
docker build -f docker/Dockerfile -t nomadoor/runpod-comfy-agent:latest .
docker push nomadoor/runpod-comfy-agent:latest
```

現在の標準image:

```text
nomadoor/runpod-comfy-agent:latest
CUDA 13.0 runtime
PyTorch cu130
ComfyUI
```

Pod起動後、workflowから必要モデルを判断して `/opt/ComfyUI/models/...` へダウンロードします。

大きいモデルDL中でもComfyUIを先に開くため、`bootstrap.background_model_downloads` は `true` を基本にします。

Pod内のモデルDLログ:

```text
/workspace/comfy-agent-model-download.log
```

## セッション開始

通常はworkflow API JSONを渡します。

```bash
python3 bin/start_session.py \
  --profile l4 \
  --workflow-json workflows/<workflow_api_json>
```

CLIは以下の標準Loaderノードを見て、必要モデルを推論します。

- `UNETLoader.unet_name`
- `CLIPLoader.clip_name`
- `VAELoader.vae_name`

未登録モデルが見つかった場合、CLIはPod作成前に停止してモデル名を表示します。workflowに書かれているモデル名を正として扱い、人間がURLを確認してから登録します。

payloadだけ確認する場合:

```bash
python3 bin/start_session.py \
  --profile l4 \
  --workflow-json workflows/<workflow_api_json> \
  --dry-run
```

## workflow実行

```bash
python3 bin/run_workflow.py --spec runspecs/<run_spec_json>
```

画像はセッション直下にも集約されます。

```text
sessions/<session_id>/images/
```

再現・デバッグ用のJSONはrunごとの `artifacts/` に保存されます。

## 状態確認

```bash
python3 bin/session_status.py
python3 bin/session_status.py --watch 10
python3 bin/session_status.py --json
```

表示するもの:

- session / Pod状態
- cost/hour
- 経過時間
- 概算コスト
- RunPod billing APIが返す課金記録

現在クレジット残高はRunPodのBilling画面で確認します。このCLIはsession / Pod状態、経過時間、概算コスト、billing APIが返す課金記録を表示します。

## 終了

```bash
python3 bin/end_session.py --yes
python3 bin/reap_sessions.py --include-orphans
```

`end_session.py` は現在session、または `--session-id` で指定したsessionのPodをterminateします。

`reap_sessions.py` はローカル記録だけでなくRunPod側のPod一覧も見て、削除漏れを検出します。

## 注意点

- `max_runtime_minutes` はローカルポリシーです。
- workflowごとにPodを作らず、作業セッションごとに1 Podを使います。
- 使い終わったら必ずterminateします。ユーザーが明示的に止めるなと言った場合だけ残します。
