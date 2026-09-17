"""Single-linkage grouping, used by both plats and places.

`plats` groups polygons by distance into one naming act. `places` groups OSM
ways by alignment, then by grid band, then by proximity into one street. The
merge procedure is identical; the things merged are not.
"""


def single_linkage(groups, joins, absorb):
    """Merge each group into the earlier groups it joins, transitively.

    Single linkage: one member matching one member of an earlier group joins
    the two, and a group matching two earlier groups merges those two with each
    other. A pairwise loop misses that second case, which is why this is one
    pass over `groups` rather than a nearest-match assignment.

    `joins(a, b)` is the match test. `absorb(first, other)` merges `other` into
    `first` and is specific to the group representation. Pass in singletons;
    the return value is the connected components, in first-seen order.
    """
    out = []
    for g in groups:
        hits = [o for o in out if joins(g, o)]
        if not hits:
            out.append(g)
            continue
        # `g` first, then the groups it connected. The order inside a group
        # is read by Place.name, which breaks a post-type tie by way order.
        first = hits[0]
        absorb(first, g)
        for other in hits[1:]:
            absorb(first, other)
            out.remove(other)
    return out
