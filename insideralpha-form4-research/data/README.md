# Data inputs

This directory includes the public sample and its SHA-256 checksum. The same
version is served from:

https://insider-alpha.com/downloads/insideralpha-form4-sample-v2.0.0.zip

The archive contains 10,000 deterministic, evenly spaced rows and all 64
columns in schema 2.0.0. It is licensed under CC BY 4.0. The notebook verifies
the archive before opening it and can therefore run without network access.

Do not commit a complete commercial release to this repository. Provide its
local path with `INSIDERALPHA_DATASET_PATH` when exact report reproduction is
required.
