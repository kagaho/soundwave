# Release guide

## Release lineage

| Tag | Source | Contents |
| --- | --- | --- |
| `1.0.0` | Soundwave-legacy | Sanitized original Kubernetes and MCP reference |
| `2.0.0` | Soundwave plus the security staging PR | Reorganized infrastructure, speech tools, Hermes, and agent experiments |
| `2.1.0` | Version 2 plus hermes-llm-wiki-obsidian | Wiki/Obsidian guide, skills, templates, and helpers in `integrations/` |

These are new sanitized snapshot releases. They do not reuse old private Git objects or claim to reproduce the original private commit history. The `VERSION` file is authoritative; tag names use plain SemVer without a `v` prefix.

## Prepare and verify

1. Work in the dedicated release checkout. Never push source private branches, use `git push --mirror`, or make a source private repository public.
2. Update `VERSION` and `CHANGELOG.md` on a release branch. Review licenses, attribution, images, private paths, and examples as well as code.
3. Run static validation:

   ```bash
   python3 -m pip install -r requirements-dev.txt
   python3 scripts/check-release.py
   ```

4. Install Gitleaks from its official release, verify its published checksum, and scan both files and **all** history. Redacted reports are local audit artifacts; do not commit them.

   ```bash
   gitleaks dir . --redact --config .gitleaks.toml
   gitleaks git . --log-opts=--all --redact --config .gitleaks.toml
   ```

5. Review the [publication checklist](../security/public-release-checklist.md). Document static results separately from live cluster tests. Revocation of previously exposed credentials must be confirmed by the owner.
6. Open a PR with the results. Merge after review, then create the annotated tag on the exact reviewed commit:

   ```bash
   release_version=$(cat VERSION)
   git tag -a "$release_version" -m "Soundwave $release_version"
   git push origin main
   git push origin "refs/tags/$release_version"
   ```

For the initial migration, keep `release/2.0.0` at the `2.0.0` commit and `release/2.1.0` at the `2.1.0` commit. Promote the reviewed `2.1.0` commit to `main` with a fast-forward or a PR preserving ancestry. Do not squash away the release lineage. Never move a published tag; issue a new patch release.

## Public release

Keep the destination private while reviewing all three tags, every branch, images, and generated release archives. Confirm the root license and third-party rights, credential revocation, and scan results. Only the owner-approved final review authorizes changing the destination to public. GitHub releases should summarize changes and link to setup guidance; do not attach private deployment exports.

## Rollback

`git switch --detach 2.0.0` restores a source snapshot for inspection. It does not roll back cluster state, image registries, credentials, PVCs, or a wiki vault. Back up persistent data separately and review workload-specific migration steps before changing a live deployment.
