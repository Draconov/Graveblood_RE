# Graveblood_RE

This directory is the **clean-room, buildable GBA reconstruction project**.
It is intentionally separate from the reverse-engineering evidence in the
workspace root.

The current ROM is only a development shell that proves the Butano/devkitARM
build pipeline. It boots, shows a dark green backdrop, and pressing **A**
toggles the backdrop color so it is obvious that the build is running and
receiving input.

It does **not** yet claim parity with the public Graveblood demo.

No original `.gba` file or original ROM byte blob is a build input.
Recovered behavior and assets should be reimplemented incrementally from the
workspace's documented evidence.

See [`../DEVELOPING_AND_BUILDING.md`](../DEVELOPING_AND_BUILDING.md) for the
pinned Butano checkout, local build commands, emulator testing, and GitHub
release flow.
