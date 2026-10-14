# Vendored BPIO2 FlatBuffers code

Generated Python for the Bus Pirate's BPIO2 schema (`bpio.fbs`), copied from
<https://github.com/DangerousPrototypes/BusPirate-BPIO2-flatbuffer-interface>
at commit `eb89844` (`python/tooling/bpio/`). Apache-2.0, see `LICENSE`.

One change: the generated absolute import `from bpio.X import X` was made
relative (`from .X import X`) so the code works inside this package.

To update: re-copy that folder at a newer commit, re-apply the import fix, and
run `pytest tests/test_bp6_*.py`.
