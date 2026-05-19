# RunPod Comfy Agent

RunPod上のComfyUIを、ローカルPC / VSCode / AIエージェントから操作するためのCLI群です。

目的はシンプルです。

- RunPod Podを作る
- workflow API JSONを読んで必要モデルを判断する
- ComfyUIへworkflowを投げる
- 生成画像をローカルへ回収する
- 作業後にPodをterminateする

## 基本フロー

```bash
python3 bin/start_session.py --profile cheap_24gb --workflow-json workflows/<workflow_api_json>
python3 bin/run_workflow.py --spec runspecs/<run_spec_json>
python3 bin/end_session.py --yes
python3 bin/reap_sessions.py --include-orphans
```

人間が見る画像はここにまとまります。

```text
sessions/<session_id>/images/
```

各runの再現用JSON、ComfyUI履歴、時間ログは `runs/<run_id>/artifacts/` に保存されます。

## ドキュメント

- [セットアップ](docs/RUNPOD_SETUP.md)
- [run spec](docs/RUN_SPEC.md)

AIエージェント向けの短い運用ルールは [skills/runpod-comfy-agent/SKILL.md](skills/runpod-comfy-agent/SKILL.md) にあります。
