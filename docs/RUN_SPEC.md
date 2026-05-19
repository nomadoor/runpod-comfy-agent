# Run Spec

`run_workflow.py` はrun spec JSONを読み、ComfyUI workflow API JSONにパッチを当てて実行します。

元のworkflowテンプレートは上書きしません。実行に使ったworkflowはrunごとの `artifacts/workflow_used.json` に保存します。

## 基本

```bash
python3 bin/run_workflow.py --spec runspecs/z-image-turbo.example.json
```

`sessions/current.json` がある場合、`run_workflow.py` は現在のsessionの `comfyui_url` を使い、結果を `sessions/<session_id>/runs/` に保存します。

URLを明示することもできます。

```bash
python3 bin/run_workflow.py \
  --spec runspecs/z-image-turbo.example.json \
  --comfy-url https://xxxxx-8188.proxy.runpod.net
```

## 主なフィールド

- `name`: runディレクトリ名のprefix。
- `workflow_json`: workflow API JSONへのパス。必須。
- `comfy_url`: ComfyUI URL。`--comfy-url` や `COMFYUI_URL` でも指定できる。
- `runs_root`: 出力先root。省略時はsession配下、または `sessions/manual-runs`。
- `inputs.images`: 実行前にアップロードする入力画像。
- `patches`: workflow JSON内の既存ノード入力の変更。
- `timeout_seconds`: history pollingのtimeout。
- `poll_interval_seconds`: history polling間隔。

## patch例

ノード入力を直接変更する。

```json
{
  "node": "6",
  "field": "text",
  "value": "new prompt"
}
```

JSON pathで変更する。

```json
{
  "path": ["31", "inputs", "seed"],
  "value": 5678
}
```

## 保存構造

各runは以下の形で保存されます。

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

人間が見る画像は `images/` にあります。再現・デバッグ用のJSONは `artifacts/` にあります。

session配下で実行した場合、画像はセッション全体のギャラリーにもコピーされます。

```text
sessions/<session_id>/images/
```

