# RunPod ComfyUI 検証状況

最終更新: 2026-05-19

## 検証済み

- `.env` から `RUNPOD_API_KEY` を読める。
- Docker Hub imageをRunPodからpullできる。
  - `nomadoor/runpod-comfy-agent:latest`
  - digest: `sha256:4a5fee7d27e585a6168ed9c851c24e18eef92fd7c170daefa70c16647bd94c87`
- imageはCUDA 13.0 runtime + PyTorch `cu130` + ComfyUI。
- `bin/start_session.py` でPodを作成できる。
- ComfyUI APIへRunPod proxy経由でアクセスできる。
- workflow JSONから必要モデルを抽出できる。
- Z-Image workflowで複数枚生成できる。
- 2つのPodを同時に起動し、それぞれで生成できる。
- `bin/end_session.py` でPodをterminateできる。
- `bin/reap_sessions.py --include-orphans` で残留Podを確認できる。
- セッション画像は `sessions/<session_id>/images/` にまとまる。

## 代表的な確認結果

```text
ComfyUI: 0.21.1
PyTorch: 2.12.0+cu130
GPU: NVIDIA L4
VRAM: 約23.7GB
cost/hour: 0.39
```

## CLI

```bash
python3 bin/start_session.py --profile cheap_24gb --workflow-json workflows/Z-Image-Turbo.json
python3 bin/run_workflow.py --spec runspecs/z-image-turbo.example.json
python3 bin/session_status.py
python3 bin/end_session.py --yes
python3 bin/reap_sessions.py --include-orphans
```

## ローカルで必要なファイル

- `.env`
  - `RUNPOD_API_KEY` を入れる
  - git管理しない
- `config/profiles.json`
  - 実運用のprofile設定
  - git管理しない

## 残っている改善候補

- Pod内のモデルDLログをCLIから取得する機能。
- workflow/model registryの拡充。
- GPU候補profileの整理。

