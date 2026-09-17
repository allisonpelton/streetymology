"""Single-linkage grouping, which both plats and places are built by.

Two callers with nothing else in common. `plats` groups polygons by distance
into one naming act. `places` groups OSM ways by alignment, then by grid band,
then by proximity into one street. What they share is the merge itself, not
what they merge.
"""


def single_linkage(groups, joins, absorb):
    """Fold each group into the earlier groups it joins, transitively.

    Single linkage: a group need only reach ONE member of an earlier group to
    join it, and a group reaching two earlier groups pulls those two together.
    That second part is what a pairwise loop misses, and why this is one pass
    over `groups` rather than a nearest-match assignment.

    `joins(a, b)` decides; `absorb(first, other)` folds `other` into `first` and
    is what knows the group's shape. Callers hand in singletons and get the
    components back, in first-seen order.
    """
    out = []
    for g in groups:
        hits = [o for o in out if joins(g, o)]
        if not hits:
            out.append(g)
            continue
        # `g` first, then the groups it bridged. The order inside a group
        # reaches Place.name, which breaks a post-type tie by way order.
        first = hits[0]
        absorb(first, g)
        for other in hits[1:]:
            absorb(first, other)
            out.remove(other)
    return out
