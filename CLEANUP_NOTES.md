Cleanup actions performed in this branch
======================================

Summary
-------

- Removed in-repo Python virtual environment `.venv` (ignored by `.gitignore`).
- Added CI workflow at `.github/workflows/ci.yml` (lint, security scans, local image builds).
- Added `scripts/scan_secrets.py` for lightweight pre-push scanning.
- Tightened `.gitignore` to exclude common local artifacts and logs.
- Untracked large model binaries (`*.pkl`) so repository remains lightweight.

How to restore models locally
-----------------------------

If you need to regenerate the model files locally, run:

```bash
python training/train_model.py
```

Or copy exported model files back into `aiops-engine/models/` and `training/models/`.

Why we untracked models
------------------------

Binary model files are large and change often during iterative training. They
should be stored in a release artifact store (GitHub Releases, S3, or a
model registry) rather than in the git history. This keeps the repo fast and
clean for recruiters and CI.

If you prefer to keep model files in the repo, we can revert this.
