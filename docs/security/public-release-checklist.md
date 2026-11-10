# Public release review

## Repository boundaries

- [ ] Confirm the destination contains only sanitized snapshot history and stays private during review.
- [ ] Review all branches and tags, including `1.0.0`; scan all history and the final tree with Gitleaks.
- [ ] Confirm the three original local checkouts and their history remain unchanged.
- [ ] Confirm previously exposed TLS keys, Tavily credentials, and OpenClaw dashboard tokens have been revoked or rotated where active. Rotation cannot be verified from source code.

## Content and rights

- [ ] Approve the root project license and review third-party and artwork rights in `THIRD_PARTY_NOTICES.md`.
- [ ] Manually inspect screenshots and diagrams for sensitive content and embedded image metadata.
- [ ] Check that examples contain no live Secret values, agent memories, private wiki sources, kubeconfigs, OAuth tokens, or `.env` files.
- [ ] Review node selectors, addresses, storage paths, legacy images, RBAC, host networking, and privileged workloads before reuse.

## Validation and publication

- [ ] Review static validation and history scans for every release commit.
- [ ] Record any live hardware tests separately; no cluster deployment is implied by static validation.
- [ ] Confirm `main` points to the reviewed `2.1.0` commit and release tags are annotated and immutable.
- [ ] Complete owner review and explicitly approve changing the new repository to public.
