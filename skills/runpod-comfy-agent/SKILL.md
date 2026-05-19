# RunPod Comfy Agent

このSkillは、このリポジトリのCLIを使ってRunPod上のComfyUIを操作するときに使う。

## 最重要ルール

- RunPod APIを直接叩かない。必ずこのリポジトリのCLIを使う。
- Podを作る前にworkflow API JSONを読む。
- `bin/start_session.py --workflow-json <workflow.json>` を使い、Loaderノードから必要モデルを推論する。
- 未登録モデルが出たら、Podを作る前に止めてユーザーに聞く。
- workflowに書かれているモデルを、勝手に別quantや軽量版へ差し替えない。
- 元のworkflowファイルを上書きしない。
- 高額GPUを勝手に選ばない。

## 標準フロー

```bash
python3 bin/start_session.py --profile l4 --workflow-json workflows/<workflow_api_json>
python3 bin/run_workflow.py --spec runspecs/<run_spec_json>
python3 bin/end_session.py --yes
python3 bin/reap_sessions.py --include-orphans
```

ユーザーが明示的に「terminateするな」と言った場合だけ、Podを残す。その場合は、session id、Pod id、URL、cost/hour、経過時間を報告する。

## 出力を見る場所

- セッション全体の画像一覧: `sessions/<session_id>/images/`
- runごとの画像: `sessions/<session_id>/runs/<run_id>/images/`
- 再現・デバッグ用ファイル: `sessions/<session_id>/runs/<run_id>/artifacts/`
- runごとの時間ログ: `sessions/<session_id>/runs/<run_id>/artifacts/timing.json`

## 最終応答前の確認

- Pod状態を確認する。
- ユーザーが止めるなと言っていない限り、`end_session.py --yes` と `reap_sessions.py --include-orphans` を実行する。
- 生成画像の場所、session id、cost/hour、経過時間、terminate結果を報告する。
- 失敗した場合は、Podがまだ動いているかを必ず報告する。

詳細なCLI仕様は `README.md` と `docs/RUNPOD_SETUP.md` を読む。
