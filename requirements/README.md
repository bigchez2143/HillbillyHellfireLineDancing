# Dependency groups

`core.txt` declares the local application dependencies. `core-win-py312.lock.txt` records the exact dependency closure observed on Windows x64 with CPython 3.12.14. `dev.txt` selects `dev-win-py312.lock.txt`, the full tested environment including pytest/httpx; test tools are excluded from the portable application. The evidence directory also records that installed development-environment snapshot.

The lock pins versions, but is not a wheel/hash lock and does not promise identical packages on another operating system or Python version. Before public release, retain the exact Windows wheels and hashes, scan them, and reproduce the build on the supported Windows target. Do not silently update this lock during startup.

The normal launcher never installs `addon-lyrics.txt` or `addon-repair.txt`. These are explicit, user-managed local tools. They can download large models on first use and have separate CPU/GPU, dependency, codec and model-licence requirements. Resolve each addon in a fresh environment before offering an installer; their unpinned transitive requirements can conflict with the core lock. Current engine calls expect addons in the application's interpreter. A separate addon environment needs an explicit engine adapter and is not yet supplied by this packaging foundation.

AI connections are optional and belong to the user. No shared key, developer-funded credits, company-operated paid inference backend, or proxy service is provided. Core use needs no account or model download.
