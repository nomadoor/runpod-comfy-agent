# AGENTS.md

このリポジトリは、AIエージェントがRunPod上のComfyUIを安全に操作するためのCLI道具箱です。

詳しい運用手順は [skills/runpod-comfy-agent/SKILL.md](skills/runpod-comfy-agent/SKILL.md) を優先してください。

## 必須ルール

- RunPod APIを直接叩かない。必ず `bin/` のCLIを使う。
- Pod作成前にworkflow API JSONを読む。
- `bin/start_session.py --workflow-json <workflow.json>` を使い、必要モデルをLoaderノードから推論する。
- 未登録モデルがある場合は、Pod作成前に止めてユーザーに聞く。
- workflowに書かれたモデルを勝手に別モデル・別quantへ差し替えない。
- 元のworkflowファイルを上書きしない。
- 高額GPUを勝手に選ばない。
- ユーザーが明示的に止めるなと言わない限り、作業後にterminateし、reaper確認する。

## 標準CLI

```bash
python3 bin/start_session.py --profile cheap_24gb --workflow-json workflows/<workflow_api_json>
python3 bin/run_workflow.py --spec runspecs/<run_spec_json>
python3 bin/session_status.py
python3 bin/end_session.py --yes
python3 bin/reap_sessions.py --include-orphans
```

## 出力

- 人間が見る画像: `sessions/<session_id>/images/`
- runごとの画像: `sessions/<session_id>/runs/<run_id>/images/`
- 再現・デバッグ用JSON: `sessions/<session_id>/runs/<run_id>/artifacts/`

