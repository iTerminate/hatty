# hatty — MIT License. See LICENSE file for details.
"""Widget-type <-> entity compatibility, shared by both directions of
`DashboardSlotPopup`'s picker (type-first filters entities, entity-first filters
types) so the rule can't drift between them."""

from hatty.const import WIDGET_TYPE_DOMAINS, WIDGET_TYPES
from hatty.types import Entity
from hatty.ui.entity_table import is_numeric_state


def entity_matches_widget_type(entity: Entity, widget_type: str) -> bool:
    if widget_type == "graph":
        # Binary sensors graph as 0/1 step timelines, so they qualify too.
        return is_numeric_state(entity) or entity.get("entity_id", "").startswith("binary_sensor.")
    if widget_type == "gauge":
        return is_numeric_state(entity)
    domain = WIDGET_TYPE_DOMAINS.get(widget_type)
    if domain:
        return entity.get("entity_id", "").split(".")[0] == domain
    return True  # panel and any unmapped type accept anything


def compatible_widget_types(entity: Entity) -> list[str]:
    """Types this entity qualifies for, in WIDGET_TYPES order except the
    domain-matched type (if any) is hoisted first as the sensible default."""
    types = [wt for wt in WIDGET_TYPES if entity_matches_widget_type(entity, wt)]
    domain = entity.get("entity_id", "").split(".")[0]
    for wt, dom in WIDGET_TYPE_DOMAINS.items():
        if dom == domain and wt in types:
            types.remove(wt)
            types.insert(0, wt)
            break
    return types
