# Preserved pre-integration valuation branch

These 13 files were copied into the integrated repository alongside the canonical
Review/application migration chain. Three reuse the exact revision IDs
20260825_0005/0006/0007 with different schema operations; executing both branches
would create overlapping tables. The integrated equivalents are already in
20260901_0009/0010/0011 and the later canonical revisions.

They are preserved here, outside Alembic's active versions directory, rather than
deleted or renumbered. Active `alembic heads` now resolves to one revision. These
files are not packaged in the integrated migration image.

An old standalone valuation database stamped at 20260830_0016 is NOT automatically
converted by this change. It needs a separately reviewed data-preserving handoff;
do not stamp it as the integrated head. A database at an ambiguous early duplicate
revision must have its schema inspected before upgrade.
