# models/

**No trained model checkpoints exist in this repository.** Every component that runs today is a classical baseline
(percentile / z-score / EFI-style detectors, Hungarian + Kalman tracking, interpolation + conservation downscaling,
rule-based risk engine) and has `parameters = 0`, `checkpoint = null` in the registry.

When learned models are trained (see `Batchsize.md`), this folder will hold **model cards and manifests** (dataset, period,
seed, hyper-parameters, metrics, checkpoint SHA-256). Weights themselves are git-ignored and belong in object storage /
Git LFS, and are loaded only with `safetensors` or `torch.load(weights_only=True)`.
