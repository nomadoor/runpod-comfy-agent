# AGENTS.md

## このプロジェクトの目的

このリポジトリは、RunPod上のComfyUIをローカルPC / VSCode / AIエージェントから操作するためのテストプロジェクトです。

本番用の大きな基盤ではありません。

まずは、以下を確認することを目的とします。

* ローカルからRunPod Podを起動できるか
* RunPod上のComfyUIにworkflow API JSONを投げられるか
* 入力画像をRunPodへ渡せるか
* 出力画像をローカルへ回収できるか
* AIエージェントがworkflow API JSONを編集しながら複数workflowを実行できるか
* 作業終了時にPodをterminateできるか

---

## 参照すべき共通ルール

RunPod / ComfyUI の詳しい運用ルールは、以下の文書に従ってください。

```text
RUNPOD_COMFYUI_RULES.md
```

この `AGENTS.md` は、このテストプロジェクトでAIエージェントが迷わないための短縮ルールです。

詳細な判断に迷った場合は、必ず `RUNPOD_COMFYUI_RULES.md` を優先してください。

---

## 最重要ルール

AIエージェントは、RunPod APIを直接操作しないでください。

Podの作成・終了・掃除は、必ずこのプロジェクト内のCLIを使います。

使ってよい予定のCLIは以下です。

```bash
python bin/start_session.py --profile cheap_24gb
python bin/run_workflow.py --workflow <workflow_name> --workflow-json <edited_workflow_json> --input <input_path>
python bin/end_session.py
python bin/reap_sessions.py
```

まだCLIが存在しない場合は、このルールに従って実装してください。

---

## RunPod Podの扱い

Podはworkflowごとに作りません。

Podは作業セッションごとに1つ作ります。

```text
正しい:
  start_session.py でPodを1つ起動する
  そのPod上のComfyUIで複数workflowを実行する
  作業が終わったら end_session.py でPodをterminateする

間違い:
  workflow実行ごとにPodを作成・削除する
```

ComfyUIのworkflow実行は短時間で終わることが多いため、workflowごとにPodを作る設計にはしないでください。

---

## workflow API JSONの扱い

`workflows/<workflow_name>/workflow_api.json` はテンプレートです。

AIエージェントは、このworkflow API JSONを読んでよいです。

AIエージェントは、既存ノードの入力値を編集したworkflow API JSONを作ってよいです。

編集してよい例:

* prompt
* seed
* steps
* cfg
* denoise
* 入力画像に関する値
* samplerやschedulerなど、既存ノードの入力値

ただし、元の `workflow_api.json` を直接上書きしてはいけません。

編集済みworkflowは一時ファイル、またはsession内のrunディレクトリに保存してください。

実行に使ったworkflow JSONは、必ず以下に保存してください。

```text
sessions/<session_id>/runs/<run_id>/artifacts/workflow_used.json
```

---

## AIエージェントに許可すること

AIエージェントは以下を行ってよいです。

* workflow API JSONを読む
* workflow API JSON内の既存ノード入力を編集する
* 入力画像を確認する
* 出力画像を確認する
* promptを作る
* 次に使うworkflowを選ぶ
* 編集済みworkflow JSONを作る
* `run_workflow.py` を使ってRunPod上のComfyUIにworkflowを投げる

---

## AIエージェントに禁止すること

AIエージェントは以下を行ってはいけません。

* RunPod API keyを読む、表示する、保存する
* RunPod APIを直接叩く
* runpodctlを直接実行する
* Podを直接作成・削除する
* GPU種別や価格を自由判断してPodを作る
* 高額GPUを勝手に使う
* 元の `workflow_api.json` を直接上書きする
* 未登録のworkflowを勝手に登録する
* `RUNPOD_COMFYUI_RULES.md` の内容と矛盾する実装をする

---

## 最初に作るCLI

このテストプロジェクトでは、まず以下の4つだけを作ります。

```text
start_session.py
run_workflow.py
end_session.py
reap_sessions.py
```

それ以外は、必要になるまで作りません。

最初から作らないもの:

* 複数Pod対応
* 自動worker選択
* local ComfyUI worker統合
* Serverless対応
* MCP server
* SQLite履歴管理
* 厳密なparams schema
* 完全なmanifest管理
* GUI

---

## 実装方針

実装は小さく始めてください。

最初の目標は、以下の1ループを通すことです。

```text
start_session.py
  ↓
RunPod上でComfyUIが起動する
  ↓
run_workflow.py でworkflow API JSONを1回投げる
  ↓
出力画像をローカルへ回収する
  ↓
end_session.py でPodをterminateする
```

この1ループが安定するまで、機能を増やさないでください。

---

## 課金事故対策

以下は必須です。

* Pod名にはsession_idを含める
* sessionにはmax_runtimeを持たせる
* `end_session.py` はPodをterminateする
* `reap_sessions.py` は削除漏れPodを検出してterminateする
* ローカルのsession情報だけを信用しない
* RunPod側のPod一覧を見て孤児Podを検出できるようにする

---

## 判断に迷ったとき

迷った場合は、以下の優先順位で判断してください。

1. `RUNPOD_COMFYUI_RULES.md` に従う
2. Pod課金事故を防ぐ
3. 元のworkflowテンプレートを壊さない
4. 実行に使ったworkflow JSONを保存する
5. まず1つのworkflowが通ることを優先する
6. 汎用化・自動化・抽象化は後回しにする
