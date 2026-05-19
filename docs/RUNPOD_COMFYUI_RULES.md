# RUNPOD_COMFYUI_RULES.md

## 目的

この文書は、ローカルPC上の VSCode / Codex / その他AIエージェントから、RunPod上で起動しているComfyUIを操作するための運用設計メモです。

目的は、ローカルPCのGPUを塞がずに、RunPod上のComfyUIへ workflow API JSON を投げ、画像生成・画像編集・データセット生成を進めることです。

これは商用SaaSや大規模チーム向けの厳密なジョブ基盤ではありません。個人利用のための、現実的で軽量な運用ルールです。

---

## この文書で決めること

この文書では、以下を決めます。

* RunPod Podをどう扱うか
* ローカルPCとRunPod ComfyUIの役割分担
* AIエージェントに何を任せるか
* workflow API JSONをどう扱うか
* 最初に作るCLIの範囲
* やりすぎないために後回しにするもの

---

## 背景

現在、ComfyUIを画像生成・画像編集・動画生成・データセット生成・前処理に使っている。

また、CodexなどのAIエージェントに、あらかじめ用意した ComfyUI workflow API JSON を使わせる運用を考えている。

やりたいことは、単発のworkflow実行ではない。

例えば、次のような流れを想定している。

```text
AIエージェントが入力画像を見る
↓
プロンプトや編集方針を決める
↓
ComfyUI workflow A を実行する
↓
出力画像をAIエージェントが見る
↓
次の編集方針を決める
↓
ComfyUI workflow B を実行する
↓
必要ならさらに別workflowへ進む
```

このように、複数のworkflowを組み合わせながら、出力を見て次の操作を決める制作ループを作りたい。

ローカルComfyUIだけでこれを行うと、ローカルGPUが占有され、PCで他の作業がしづらくなる。

そのため、RunPod上にComfyUIを立て、ローカルPCから操作する。

---

## 最重要方針

RunPod Podは、workflowごとに作らない。

Podは、作業セッションごとに作る。

```text
正しい:
  1 作業セッション = 1 RunPod Pod
  セッション中に複数workflowを何度も実行する
  作業終了時にPodをterminateする

間違い:
  1 workflow = 1 RunPod Pod
  workflowを実行するたびにPodを作成・削除する
```

ComfyUIの生成・編集workflowは、数秒〜数十秒で終わることが多い。

そのため、workflowごとにPodを起動・削除すると、Pod起動時間のほうが大きくなり、運用として成立しない。

---

## ローカルPCの役割

ローカルPCは、作業の司令塔として扱う。

ローカルPCで行うこと:

* VSCode / Codex / その他AIエージェントの実行
* workflow API JSONの管理
* 入力画像・出力画像の管理
* AIエージェントによる画像確認
* プロンプト生成
* 編集方針の決定
* 次に使うworkflowの選択
* RunPod Podの開始・終了指示
* RunPod上のComfyUIへのworkflow実行依頼
* 出力画像の回収

ローカルPCは「対話的な作業場」として残す。

---

## RunPod Podの役割

RunPod Podは、GPU実行担当として扱う。

RunPod Podで行うこと:

* ComfyUIを起動する
* セッション中はComfyUIを維持する
* ローカルから送られたworkflow API JSONを実行する
* ローカルから送られた画像を入力として使う
* 出力画像を生成する
* 出力画像をローカルへ返す

RunPod Podは、永続的な作業PCとしては扱わない。

ただし、workflowごとに毎回破棄するのではなく、作業セッション中は維持する。

---

## local ComfyUIとの関係

将来的には、ローカルComfyUIとRunPod ComfyUIを同じ種類のworkerとして扱えると便利である。

ただし、MVPではlocal worker統合を急がない。

理由は、localとRunPodでは差分が多いからである。

```text
local ComfyUI:
  - ローカルファイルを直接読める
  - upload / download が不要
  - ローカルGPUを使う
  - 常に存在する

RunPod ComfyUI:
  - 入力画像をuploadする必要がある
  - 出力画像をdownloadする必要がある
  - セッション開始・終了がある
  - Pod削除漏れによる課金リスクがある
```

MVPでは、まずRunPod上のComfyUIをローカルから操作することに集中する。

local worker統合は後回しにする。

---

## AIエージェントに任せること

AIエージェントには、制作判断を任せる。

任せること:

* workflow API JSONを読む
* workflow API JSON内の既存ノード入力を編集する
* promptを作る
* seed / steps / cfg / denoise などを調整する
* 入力画像・出力画像を見て判断する
* 次に使うworkflowを選ぶ
* 編集後のworkflow API JSONを一時ファイルとして保存する
* `run_workflow.py` を使って実行する

個人利用なので、workflow API JSONの編集は過度に縛らない。

ComfyUIのAPI workflowでは、基本的には既存ノードの入力値を変えるだけであり、新しいノードを追加してworkflow構造そのものを大きく壊す用途ではない。

そのため、最初から `params.schema.json` や厳密な差し替えポイント指定は必須にしない。

---

## AIエージェントに直接任せないこと

AIエージェントに、課金やインフラ操作に直結する権限は直接渡さない。

直接任せないこと:

* RunPod API keyを読む・表示する・保存する
* RunPod APIを直接叩く
* Podを直接作成・削除する
* GPU種別や価格を自由判断する
* 高額GPUを勝手に使う
* 新しいworkflowを勝手に登録する
* 元の `workflow_api.json` を直接上書きする

重要なのは、次の分離である。

```text
AIエージェントに自由に任せる:
  生成・編集の判断
  workflow API JSONの既存ノード入力編集
  出力を見た次の操作判断

CLI側で囲う:
  RunPod API
  Pod作成・削除
  GPU profile
  セッション管理
  課金事故対策
```

---

## workflow API JSONの扱い

各workflowは、テンプレートとして保存する。

```text
workflows/
  generate_v1/
    workflow_api.json
    README.md

  edit_v1/
    workflow_api.json
    README.md
```

`workflow_api.json` は元テンプレートとして扱い、直接上書きしない。

AIエージェントはこのテンプレートを読んでよい。

AIエージェントが編集したworkflowは、一時ファイル、またはセッション内のrunディレクトリに保存してから実行する。

例:

```bash
python bin/run_workflow.py \
  --workflow generate_v1 \
  --workflow-json ./tmp/edited_workflow.json \
  --input ./input.png
```

実行に使ったworkflow JSONは、必ず保存する。

```text
sessions/<session_id>/runs/<run_id>/artifacts/workflow_used.json
```

これを最小限のprovenanceとする。

最初から完全なmanifest管理やmodel hash管理はしない。

---

## 最初に作るCLI

MVPで作るCLIは、以下の4つに絞る。

```text
start_session.py
run_workflow.py
end_session.py
reap_sessions.py
```

これ以上のジョブキュー、worker pool、MCP server、SQLite管理などは最初から作らない。

---

## start_session.py

RunPod Podを起動し、ComfyUIが使える状態になるまで待つ。

主な責務:

* RunPod API keyを環境変数から読む
* 指定profileでPodを作成する
* Pod名にsession_idを含める
* Podの起動完了を待つ
* ComfyUIのhealth checkを行う
* `sessions/<session_id>/session.json` を作成する
* max runtimeを設定する

想定コマンド:

```bash
python bin/start_session.py --profile cheap_24gb
```

---

## run_workflow.py

起動済みRunPod ComfyUIへ、workflow API JSONを投げる。

主な責務:

* 現在のsessionを読む
* workflowテンプレート、または編集済みworkflow JSONを読む
* 入力画像をRunPodへuploadする
* 必要に応じてworkflow内の画像入力をRunPod側のパスに合わせる
* ComfyUI APIへworkflowをPOSTする
* prompt_idをpollingする
* 出力画像をdownloadする
* `sessions/<session_id>/runs/<run_id>/` に保存する
* 実行に使ったworkflowを `workflow_used.json` として保存する

想定コマンド:

```bash
python bin/run_workflow.py \
  --workflow generate_v1 \
  --workflow-json ./tmp/edited_workflow.json \
  --input ./input.png
```

`--workflow-json` が省略された場合は、`workflows/<workflow>/workflow_api.json` を使う。

---

## end_session.py

現在のRunPodセッションを終了する。

主な責務:

* `session.json` からPod IDを読む
* RunPod Podをterminateする
* session状態をclosedにする

想定コマンド:

```bash
python bin/end_session.py
```

---

## reap_sessions.py

削除漏れPodを掃除する。

これは課金事故対策として重要である。

主な責務:

* RunPod APIで自分のPod一覧を取得する
* `comfy-session-` のような命名規則に合うPodを探す
* max runtimeを超えたPodをterminateする
* ローカルsessionに紐づかない孤児Podを検出する
* 必要に応じてterminateする

想定コマンド:

```bash
python bin/reap_sessions.py
```

ローカルの `session.json` だけを信用しない。

PCが落ちたり、スクリプトが異常終了した場合でも、RunPod側に残ったPodを検出できるようにする。

---

## GPU profile

MVPでは、GPU profileは1つだけでよい。

```text
cheap_24gb:
  24GB級GPU
  通常のComfyUI生成・編集用
  価格上限あり
  max_runtimeあり
```

CodexやAIエージェントに、GPU名や価格を自由判断させない。

GPU選択は、profileとして人間が定義する。

将来的に必要なら、以下を追加する。

```text
fast_24gb
heavy_48gb
training_48gb
```

---

## session構造

最小構成は以下。

```text
sessions/
  <session_id>/
    session.json
    runs/
      <run_id>/
        README.md
        inputs/
        images/
        artifacts/
          workflow_used.json
          run_spec_used.json
          payload.json
          history.json
          timing.json
        notes.md
```

`session.json` には最低限以下を保存する。

```json
{
  "session_id": "...",
  "pod_id": "...",
  "pod_name": "comfy-session-...",
  "profile": "cheap_24gb",
  "comfyui_url": "...",
  "status": "active",
  "started_at": "...",
  "max_runtime_minutes": 180
}
```

---

## まずやらないこと

最初から以下は作らない。

```text
- 複数Pod対応
- 自動worker選択
- local ComfyUI worker統合
- Serverless対応
- MCP server化
- SQLite履歴管理
- 厳密なparams.schema.json
- 完全なmanifest.json
- model hash管理
- custom node commit管理の完全自動化
- GPU価格最適化
- GUI
```

これらは、RunPod上のComfyUIをVSCode / AIエージェントから操作できるようになってから追加を検討する。

---

## 最初の検証手順

workflowが用意済みなら、まず以下を確認する。

1. RunPod上でComfyUIが起動する
2. 必要なcustom nodeが入る
3. 必要モデルが正しい場所にある
4. workflow API JSONをRunPod上のComfyUIで実行できる
5. 入力画像を渡せる
6. 出力画像を取得できる
7. Podをterminateできる

最初から大きな自動化をしない。

まず、RunPod上で普段使っているworkflowが成立するかを見る。

---

## 実装時の注意

### 1. GUIで立てるPodについて

最終運用では、RunPod GUIからPodを立てる必要はない。

ただし、初回の切り分けとしてGUIでPodを立てるのはあり。

目的は、自動化前に以下を確認すること。

* ComfyUIがRunPod上で動くか
* workflowが通るか
* custom nodeやmodel pathで詰まらないか

確認後、その手順をCLIに移す。

### 2. PodがrunningでもComfyUIが起動済みとは限らない

Podの状態がrunningになっても、ComfyUIがAPIを受け付けられるとは限らない。

`start_session.py` では、ComfyUIのhealth checkを必ず行う。

### 3. 元workflowは上書きしない

`workflows/<name>/workflow_api.json` はテンプレートである。

AIエージェントが編集したworkflowは別ファイルに保存する。

実行に使ったworkflowは `artifacts/workflow_used.json` として保存する。

### 4. 課金事故対策

以下は必須。

* sessionにmax_runtimeを持たせる
* Pod名にsession_idを含める
* `end_session.py` でterminateする
* `reap_sessions.py` を用意する
* RunPod側のspending limitを設定する
