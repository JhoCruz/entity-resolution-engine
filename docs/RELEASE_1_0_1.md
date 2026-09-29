# v1.0.1: common-name blocking fix

An exact identifier can resolve a row before the name candidate stage runs. Previously,
the name stage counted those resolved rows when enforcing its per-key limit. With 33
invented rows sharing the same name on each side, all 33 had distinct matching
identifiers, yet the command stopped at a 1,089-pair name limit. The stage now excludes
accepted rows before checking the limit, and the end-to-end regression test confirms
the 33 matches complete without new name or date candidates.

The normal workflow, report formats, and privacy limits are described in the
[v1.0 release guide](RELEASE_1_0.md). Metrics in this repository use synthetic
records and do not establish accuracy on real identities.
