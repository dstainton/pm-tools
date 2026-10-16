"""Project-scoped concept identity lookup for unconfirmed discovery.

Only a unique name or alias within one project identifies a concept candidate.
An alias is not confirmed for external search or ownership decisions by using
it here. Ambiguous aliases are never resolved by guessing.
"""
import re
from collections import defaultdict

# Whole-word English tokens are unsafe as standalone acronym mentions.
UNSAFE_ALIASES = {"DID", "IT", "MAP", "CAN", "HAS", "MAY", "WILL",
                  "AS", "IN", "ON", "OR", "IF", "TO", "DO", "US",
                  "API", "APS", "BC"}


class IdentityIndex:
    def __init__(self, clusters):
        self.lookup = {}
        self.ambiguous = set()
        by_name = defaultdict(set)
        originals = {}
        for cluster in clusters:
            scope = cluster.get("project")
            canonical = cluster["canonical"]
            identity = (scope, canonical.casefold())
            originals[identity] = canonical
            for term in [canonical] + list(cluster.get("variants") or []) + list(cluster.get("aliases") or []):
                term = str(term or "").strip()
                if not term:
                    continue
                if term.upper() in UNSAFE_ALIASES and term != canonical:
                    continue
                by_name[(scope, term.casefold())].add(identity)
        for key, identities in by_name.items():
            if len(identities) == 1:
                self.lookup[key] = originals[next(iter(identities))]
            else:
                self.ambiguous.add(key)
        self.by_scope = defaultdict(list)
        for (scope, term), canonical in self.lookup.items():
            self.by_scope[scope].append((term, canonical))
        for scope in self.by_scope:
            # Prefer full names to shorter aliases at overlapping locations.
            self.by_scope[scope].sort(key=lambda x: (-len(x[0]), x[0]))

    def resolve(self, scope, term):
        """Normalize only an unambiguous known term within the same project."""
        return self.lookup.get((scope, str(term).strip().casefold()), term)

    def mentions(self, scope, text):
        """Return canonical mentions without counting overlapping spellings."""
        candidates = []
        for term, canonical in self.by_scope.get(scope, []):
            for match in re.finditer(r"(?<!\w)" + re.escape(term) + r"(?!\w)",
                                     text, flags=re.IGNORECASE):
                candidates.append((match.start(), match.end(), canonical, text[match.start():match.end()]))
        candidates.sort(key=lambda x: (-(x[1] - x[0]), x[0], x[2].casefold()))
        selected = []
        for item in candidates:
            if not any(item[0] < old[1] and old[0] < item[1] for old in selected):
                selected.append(item)
        return sorted(selected, key=lambda x: (x[0], x[2].casefold()))
