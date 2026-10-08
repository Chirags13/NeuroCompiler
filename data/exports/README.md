# Final model-training exports

This directory is the boundary between data collection and Phase 2.

The canonical export should eventually contain:

- transitions_train.jsonl
- transitions_validation.jsonl
- transitions_test.jsonl
- baselines.jsonl
- dataset_manifest.json
- hash_manifest.json

Only correctness-passing, runtime-stable records enter the training exports. Keep raw measurements and failed configurations outside the training export so that they remain auditable without contaminating labels.

Do not check large generated JSONL/Parquet datasets into Git. Store them in the project data location/object storage and commit only manifests, hashes, schemas, and generation code.
