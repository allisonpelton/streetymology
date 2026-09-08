# DEPRECATED — see `naming_plat_rule.md`

This document tuned `CLEAN_SHARE`, a threshold on the fraction of a single OSM
*way* lying inside a plat. **That parameter no longer exists.** It measured
mapping accidents rather than geography: OSM splits a street at arbitrary points,
so the same street scores differently depending on how it was edited.

The rule that replaced it is metres of unbroken street inside a plat. It is
documented, with the experiments that produced it, in `naming_plat_rule.md`.

Kept only so a link or a memory of "the 0.4 experiment" lands somewhere true.
The comparison itself survives in the new document.
