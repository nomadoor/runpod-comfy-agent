# Batch

`run_batch.py` は `jobs.jsonl` を読み、複数のrun specを現在のComfyUI sessionへ順番に投入します。

この段階のbatchは、1つのPod上で逐次実行します。複数Podへの分散は、manifest/resumeの運用が固まってから追加します。

## 基本

先にPodを起動します。

```bash
python3 bin/start_session.py --profile l4 --workflow-json workflows/<workflow_api_json>
```

次にbatchを実行します。

```bash
python3 bin/run_batch.py --jobs jobs.jsonl
```

動作確認だけを行う場合:

```bash
python3 bin/run_batch.py --jobs jobs.jsonl --dry-run
```

## jobs.jsonl

1行が1jobです。jobはrun specと同じ形式で書けます。

```jsonl
{"job_id":"000001","workflow_json":"workflows/Z-Image-Turbo.json","patches":[{"node":"6","field":"text","value":"red ink in water"},{"node":"3","field":"seed","value":1001}]}
{"job_id":"000002","workflow_json":"workflows/Z-Image-Turbo.json","patches":[{"node":"6","field":"text","value":"blue ink in water"},{"node":"3","field":"seed","value":1002}]}
```

`spec` オブジェクトで包むこともできます。

```jsonl
{"job_id":"000001","spec":{"workflow_json":"workflows/Z-Image-Turbo.json","patches":[{"node":"3","field":"seed","value":1001}]}}
```

`job_id` はresume判定に使います。省略した場合は行番号から `000001` のように生成します。

## 保存先

現在sessionがある場合、batchは以下に保存されます。

```text
sessions/<session_id>/batches/<batch_id>/
  batch.json
  summary.json
  manifest.jsonl
  job_specs/
    <job_id>.json
  runs/
    <job_id>/
      images/
      artifacts/
```

sessionがない場合は `sessions/manual-batches/` 配下に保存されます。

## manifest / resume

`manifest.jsonl` はappend-onlyです。

```jsonl
{"job_id":"000001","status":"running","run_id":"000001"}
{"job_id":"000001","status":"done","output":[".../000001/images/ComfyUI_00001_.png"]}
{"job_id":"000002","status":"failed","error":"ComfyUI rejected the prompt: ..."}
```

同じ `--batch-dir` で再実行すると、最新statusが `done` のjobはskipされます。`failed` のjobは再実行対象です。

完了済みも再実行する場合:

```bash
python3 bin/run_batch.py --jobs jobs.jsonl --batch-dir sessions/<session_id>/batches/<batch_id> --rerun-done
```

## 注意点

- `run_batch.py` はPodを作成しません。Pod作成は `start_session.py` が担当します。
- `run_batch.py` は完了後にPodをterminateしません。作業終了時は `end_session.py --yes` と `reap_sessions.py --include-orphans` を実行します。
- multi-pod分散はまだ実装していません。
