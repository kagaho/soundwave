# Contributing

Open a focused pull request describing the concrete change, prerequisites, and validation. Keep runtime data and credentials outside this repository.

1. Start from `main` and create a component branch.
2. Adapt manifests to your hardware; describe ARM64/x86_64, drivers, storage, images, and GPU requirements.
3. Run `python3 scripts/check-release.py` and the tree and full-history Gitleaks commands in [the release guide](docs/releases/RELEASING.md).
4. For scripts, include meaningful tests for changed behavior. Cluster changes need an explicitly documented test on suitable hardware; static checks do not establish deployability.
5. Update the component guide and `CHANGELOG.md`. Keep independently maintained projects in `integrations/` with their original license and attribution.

See [the security policy](SECURITY.md) before reporting a credential or vulnerability. Publication and release procedures are in [RELEASING.md](docs/releases/RELEASING.md).
