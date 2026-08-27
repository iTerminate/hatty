# hatty — MIT License. See LICENSE file for details.
"""Device / area tree view.

A full-screen `Tree` over the Home Assistant registries with three toggleable
grouping modes (cycled with `v`):

- **device**      — a flat Device → Entity tree.
- **area**        — a nested Area → Device → Entity tree.
- **integration** — a nested Integration → Device → Entity tree, keyed off the
  entity registry's `platform` field.

Areas contain *devices*, not entities, so the area grouping walks
area → device.area_id → device → entity. An entity's device comes from the
entity registry's `device_id`; a device's area from the device registry's
`area_id`. Devices/entities without an area/device/platform land in an
"Unassigned"/"No device"/"No integration" bucket respectively. Areas and
integrations collapse by default, only auto-expanding under an active filter.

`/` opens an embedded search that live-filters the tree; `ctrl+s` cycles the
match *scope* (all/area/device/entity/integration) so the term can be
restricted to one node level rather than matching anywhere. `m` on a device
node reassigns it to another area via a real `config/device_registry/update`
write (see `AreaPickerPopup`); `a`/`r` create/rename an area (area mode only).
`n` on an area node quick-creates a dashboard populated from that area's
entities. `i` opens a read-only registry/device-info popup. Entity leaves:
`enter` toggles or falls back to opening controls for non-togglable domains,
`e` opens controls directly, `G` pushes the fullscreen graph, `space` toggles
list membership without touching the main table's selection.
"""

from typing import TYPE_CHECKING

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Container
from textual.screen import Screen
from textual.widgets import Footer, Header, Input, Label, ListItem, ListView, Static, Tree

from hatty.const import CONFIG_KEY_GRAPH_TYPE
from hatty.controllers.keybindings import bindings_for
from hatty.ui.entity_table import entity_matches, get_display_name, is_dead
from hatty.ui.popup_base import PopupScreen
from hatty.ui.search_input import SearchInput

if TYPE_CHECKING:
    from hatty.main import HACLI

# Synthetic bucket labels for entities/devices with no device/area/integration.
UNASSIGNED_LABEL = "— Unassigned —"
NO_DEVICE_LABEL = "— No device —"
NO_INTEGRATION_LABEL = "— No integration —"

# Area quick-create dashboards cap out at a 3x8 grid; beyond that they're unusable.
MAX_AREA_DASHBOARD_SLOTS = 24


def device_display_name(device: dict) -> str:
    return device.get("name_by_user") or device.get("name") or device.get("id") or "device"


def area_display_name(area: dict) -> str:
    return area.get("name") or area.get("area_id") or "area"


def device_info_rows(
    device: dict, area_registry: list, device_registry: list, entity_count: int
) -> list[tuple[str, str]]:
    """`(label, value)` rows for a device's info popup (issue #151), omitting
    rows whose value is empty so sparse registry entries stay tidy."""
    area_names = {a.get("area_id"): area_display_name(a) for a in area_registry if a.get("area_id")}
    by_id = {d.get("id"): d for d in device_registry if d.get("id")}

    name = device.get("name")
    name_by_user = device.get("name_by_user")
    # Show the user-set name, noting the original when it was renamed.
    name_value = name_by_user or name or ""
    if name_by_user and name and name_by_user != name:
        name_value = f"{name_by_user} (was: {name})"

    via_id = device.get("via_device_id")
    via_value = device_display_name(by_id[via_id]) if via_id and via_id in by_id else ""

    rows = [
        ("Name", name_value),
        ("Manufacturer", device.get("manufacturer") or ""),
        ("Model", device.get("model") or ""),
        ("SW version", device.get("sw_version") or ""),
        ("HW version", device.get("hw_version") or ""),
        ("Area", area_names.get(device.get("area_id"), "")),
        ("Entities", str(entity_count)),
        ("Via device", via_value),
    ]
    return [(label, value) for label, value in rows if value]


def build_device_groups(entity_registry: list, device_registry: list) -> list[dict]:
    """Ordered device groups `{device_id, label, area_id, entity_ids}`, sorted by
    name, with a trailing no-device group (device_id=None) for entities whose
    registry entry has no device (or that lack a device-registry match).

    Registry entries with `disabled_by` set are skipped (issue #139) — HA never
    loads disabled entities into the state machine, so they'd only ever show as
    stateless leaves. This is the shared choke point: area mode composes this and
    integration mode calls it per platform partition, so all grouping modes (and
    the area→dashboard quick-create that walks the tree) inherit the filter."""
    device_by_id = {d.get("id"): d for d in device_registry if d.get("id")}

    order: list[str] = []
    groups: dict[str, dict] = {}
    no_device: dict = {"device_id": None, "label": NO_DEVICE_LABEL, "area_id": None, "entity_ids": []}

    for entry in entity_registry:
        entity_id = entry.get("entity_id")
        if not entity_id:
            continue
        if entry.get("disabled_by"):
            continue
        device_id = entry.get("device_id")
        device = device_by_id.get(device_id)
        if device_id and device is not None:
            group = groups.get(device_id)
            if group is None:
                group = {
                    "device_id": device_id,
                    "label": device_display_name(device),
                    "area_id": device.get("area_id"),
                    "entity_ids": [],
                }
                groups[device_id] = group
                order.append(device_id)
            group["entity_ids"].append(entity_id)
        else:
            no_device["entity_ids"].append(entity_id)

    result = sorted((groups[d] for d in order), key=lambda g: g["label"].lower())
    if no_device["entity_ids"]:
        result.append(no_device)
    return result


def build_area_groups(entity_registry: list, device_registry: list, area_registry: list) -> list[dict]:
    """Ordered area groups `{area_id, label, devices}`, sorted by name. Devices
    with no (known) area fall into a trailing "Unassigned" bucket; entities with
    no device fall into a final "No device" bucket (as area-direct devices)."""
    area_names = {a.get("area_id"): area_display_name(a) for a in area_registry if a.get("area_id")}
    device_groups = build_device_groups(entity_registry, device_registry)

    order: list[str] = []
    areas: dict[str, dict] = {}
    unassigned: dict = {"area_id": None, "label": UNASSIGNED_LABEL, "devices": []}
    no_device_group: dict | None = None

    for group in device_groups:
        if group["device_id"] is None:
            no_device_group = group
            continue
        area_id = group["area_id"]
        if area_id and area_id in area_names:
            area = areas.get(area_id)
            if area is None:
                area = {"area_id": area_id, "label": area_names[area_id], "devices": []}
                areas[area_id] = area
                order.append(area_id)
            area["devices"].append(group)
        else:
            unassigned["devices"].append(group)

    result = sorted((areas[a] for a in order), key=lambda a: a["label"].lower())
    for area in result:
        area["devices"].sort(key=lambda g: g["label"].lower())
    if unassigned["devices"]:
        unassigned["devices"].sort(key=lambda g: g["label"].lower())
        result.append(unassigned)
    if no_device_group is not None:
        result.append({"area_id": None, "label": NO_DEVICE_LABEL, "devices": [no_device_group]})
    return result


def build_integration_groups(entity_registry: list, device_registry: list) -> list[dict]:
    """Ordered integration groups `{integration, label, devices}`, sorted by name
    (issue #147). The entity registry's `platform` names the integration (zha,
    mqtt, hue, …); entities are partitioned by platform, then each partition is
    grouped into Device → Entity via `build_device_groups`. Entities with no
    platform fall into a trailing "No integration" bucket."""
    partitions: dict[str | None, list] = {}
    order: list[str | None] = []
    for entry in entity_registry:
        if not entry.get("entity_id"):
            continue
        if entry.get("disabled_by"):
            continue
        platform = entry.get("platform") or None
        if platform not in partitions:
            partitions[platform] = []
            order.append(platform)
        partitions[platform].append(entry)

    named = sorted((p for p in order if p is not None), key=str.lower)
    result: list[dict] = [
        {
            "integration": platform,
            "label": platform,
            "devices": build_device_groups(partitions[platform], device_registry),
        }
        for platform in named
    ]
    if None in partitions:
        result.append(
            {
                "integration": None,
                "label": NO_INTEGRATION_LABEL,
                "devices": build_device_groups(partitions[None], device_registry),
            }
        )
    return result


def _label_matches(term: str, label: str) -> bool:
    # Mirrors entity_matches' skip-word semantics (#241): every word of the term
    # just has to appear somewhere in the label, in any order.
    haystack = label.lower()
    return all(word in haystack for word in term.split())


def filter_device_groups(groups: list[dict], term: str, entity_matcher, scope: str = "all") -> list[dict]:
    """Prune device groups to a search term under a scope (issue #140):

    - ``all``: a device-label match keeps all entities, else keep the entities
      matched by ``entity_matcher``.
    - ``device``: only device labels match (keeps all entities); no entity fallback.
    - ``entity``: only ``entity_matcher`` matches; device labels are ignored.
    - ``area``: no device matches on its own (area scope lives at the area level);
      in device grouping mode this yields nothing.
    """
    result = []
    for group in groups:
        if scope in ("all", "device") and _label_matches(term, group["label"]):
            result.append(group)
            continue
        if scope in ("all", "entity"):
            kept = [eid for eid in group["entity_ids"] if entity_matcher(eid)]
            if kept:
                result.append({**group, "entity_ids": kept})
    return result


def filter_area_groups(areas: list[dict], term: str, entity_matcher, scope: str = "all") -> list[dict]:
    """Prune area groups to a search term under a scope (issue #140):

    - ``all``: an area-label match keeps the whole subtree, else recurse.
    - ``area``: only area labels match (keeps the whole subtree); no fallback.
    - ``device``/``entity``: area labels are ignored; recurse into
      `filter_device_groups` with the same scope and keep areas that survive.
    - ``integration``: there are no integration nodes in area grouping, so this
      matches nothing (mirrors how ``area`` matches nothing in integration mode).
    """
    result = []
    for area in areas:
        if scope in ("all", "area") and _label_matches(term, area["label"]):
            result.append(area)
            continue
        if scope in ("area", "integration"):
            continue
        kept = filter_device_groups(area["devices"], term, entity_matcher, scope)
        if kept:
            result.append({**area, "devices": kept})
    return result


def filter_integration_groups(groups: list[dict], term: str, entity_matcher, scope: str = "all") -> list[dict]:
    """Prune integration groups to a search term (issue #147). Mirrors
    `filter_area_groups`: the `all` and `integration` scopes keep a whole subtree
    on an integration-label match, the `area`/`integration` scopes otherwise match
    nothing here, and `device`/`entity` recurse as usual (issue #180)."""
    result = []
    for group in groups:
        if scope in ("all", "integration") and _label_matches(term, group["label"]):
            result.append(group)
            continue
        if scope in ("area", "integration"):
            continue
        kept = filter_device_groups(group["devices"], term, entity_matcher, scope)
        if kept:
            result.append({**group, "devices": kept})
    return result


class AreaNamePopup(PopupScreen):
    """Single-Input name prompt for creating or renaming an area (issue #146).
    Dismisses with the trimmed name, or `None` when empty/cancelled."""

    BINDINGS = bindings_for("area_name")

    DEFAULT_CSS = """
    AreaNamePopup #area_name_container {
        width: 60;
    }
    """

    def __init__(self, title: str, initial_name: str = "", placeholder: str = "Area name..."):
        super().__init__()
        self._title = title
        self._initial_name = initial_name
        self._placeholder = placeholder

    def compose(self) -> ComposeResult:
        with Container(id="area_name_container", classes="popup-container"):
            yield Label(self._title, classes="popup-title")
            yield Input(value=self._initial_name, placeholder=self._placeholder, id="area_name_input")
            yield Footer()

    def on_mount(self) -> None:
        self.query_one("#area_name_input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value.strip() or None)

    def action_cancel(self) -> None:
        self.dismiss(None)


class AreaPickerPopup(PopupScreen):
    """Pick a target area for a device. Dismisses with `{"area_id": <id|None>}`
    (None clears the assignment) or `None` when cancelled."""

    BINDINGS = bindings_for("area_picker")

    DEFAULT_CSS = """
    AreaPickerPopup #area_picker_container {
        width: 60;
        max-height: 80%;
    }
    AreaPickerPopup #area_list {
        height: auto;
        max-height: 20;
    }
    """

    def __init__(self, device_label: str, areas: list[tuple[str | None, str]]):
        super().__init__()
        self._device_label = device_label
        # A leading "clear" option, then every area; parallel to the ListView rows.
        self._options: list[tuple[str | None, str]] = [(None, "(No area)")] + list(areas)

    def compose(self) -> ComposeResult:
        with Container(id="area_picker_container", classes="popup-container"):
            yield Label(Text(f"Move '{self._device_label}' to area"), classes="popup-title")
            with ListView(id="area_list"):
                for _area_id, label in self._options:
                    yield ListItem(Label(label))
            yield Footer()

    def on_mount(self) -> None:
        self.query_one("#area_list", ListView).focus()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        index = event.list_view.index or 0
        area_id = self._options[index][0]
        self.dismiss({"area_id": area_id})

    def action_cancel(self) -> None:
        self.dismiss(None)


class DeviceInfoPopup(PopupScreen):
    """Read-only device (or entity) info panel (issue #151). Constructed from an
    already-resolved title + `(label, value)` rows so it stays pure/testable."""

    BINDINGS = bindings_for("device_info")

    DEFAULT_CSS = """
    DeviceInfoPopup #device_info_container {
        width: 64;
    }
    DeviceInfoPopup .device-info-row {
        height: auto;
    }
    """

    def __init__(self, title: str, rows: list[tuple[str, str]]):
        super().__init__()
        self._title = title
        self._rows = rows

    def compose(self) -> ComposeResult:
        with Container(id="device_info_container", classes="popup-container"):
            yield Label(Text(self._title), classes="popup-title")
            for label, value in self._rows:
                yield Label(Text(f"{label}: {value}"), classes="device-info-row")
            yield Footer()

    def action_cancel(self) -> None:
        self.dismiss(None)


class DeviceTreeScreen(Screen):
    app: "HACLI"  # narrow Textual's inherited attr for type-checkers; annotation only, no runtime effect

    # Space is priority: the focused Tree binds it to toggle_node, forwarded here
    # for non-entity nodes. ctrl+s is priority so it fires while search is focused.
    BINDINGS = bindings_for("tree")

    _MODES = ("device", "area", "integration")
    # Scopes offered per view; ctrl+s cycles only within the current tuple. The
    # first entry is that view's default, applied on a view switch (#206).
    _VIEW_SCOPES = {
        "device": ("device", "all", "entity"),
        "area": ("area", "all", "device", "entity"),
        "integration": ("integration", "all", "device", "entity"),
    }

    DEFAULT_CSS = """
    DeviceTreeScreen #device_tree_status {
        padding: 0 1;
        color: $text-muted;
    }
    DeviceTreeScreen Tree {
        height: 1fr;
    }
    """

    def __init__(self, initial_entity_id: str | None = None):
        super().__init__()
        self._mode = "device"
        self._filter = ""
        self._scope = self._VIEW_SCOPES[self._mode][0]
        # entity_id -> its leaf nodes (a list to stay robust to duplicate placements).
        self._entity_nodes: dict[str, list] = {}
        # device_id -> its device nodes, for cursor-follow across mode switches (#153).
        self._device_nodes: dict[str, list] = {}
        # Entity to cursor after the first build (table -> tree, issue #153).
        self._initial_entity_id = initial_entity_id

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(self._status_text(), id="device_tree_status")
        yield SearchInput(id="device_tree_search")
        yield Tree("", id="device_tree")
        yield Footer()

    def on_mount(self) -> None:
        tree = self.query_one("#device_tree", Tree)
        # The grouping mode is named in the status line, so the synthetic
        # "Devices"/"Areas" root just wastes a level and an indent column.
        tree.show_root = False
        self.rebuild()
        if self._initial_entity_id:
            self._focus_entity(self._initial_entity_id)
        tree.focus()

    # ── rendering ─────────────────────────────────────────────────────────────

    _MODE_LABELS = {
        "device": "Device → Entity",
        "area": "Area → Device → Entity",
        "integration": "Integration → Device → Entity",
    }

    def _status_text(self) -> str:
        label = self._MODE_LABELS[self._mode]
        text = (
            f"Grouping: {label}   ·   /: search   ·   e: expand   ·   G: graph"
            "   ·   space: list   ·   v: switch view   ·   x/X: collapse/expand all"
            "   ·   l: lists   ·   d: dashboard   ·   m: move device to area   ·   r: rename   ·   i: info"
        )
        if self._mode == "area":
            text += "   ·   n: new dashboard from area   ·   a: new area"
        if self._filter:
            # _entity_nodes is populated by rebuild() before this is rendered, so
            # it's the live count of surviving entity leaves (issue #149).
            count = len(self._entity_nodes)
            noun = "entity" if count == 1 else "entities"
            text += f"   ·   Filter: '{self._filter}' — {count} {noun} (ctrl+s scope: {self._scope})"
        return text

    def _search_placeholder(self) -> str:
        back = self.app.keys_ctl.display("nav.back")
        return f"Filter [{self._scope}]... (Enter to apply, ctrl+s: scope, {back} to clear)"

    def _entity_matcher(self):
        term = self._filter

        def match(entity_id: str) -> bool:
            entity = self.app.find_entity(entity_id) or {"entity_id": entity_id}
            return entity_matches(entity, term)

        return match

    def _membership_list(self) -> str | None:
        """The list `space` toggles against: the current list, falling back to
        the last-shown/default list (without switching the main table to it)."""
        return self.app.current_list_name or self.app.list_ctl.jump_target()

    def _entity_label(self, entity_id: str) -> str | Text:
        entity = self.app.find_entity(entity_id)
        name = get_display_name(entity) if entity else entity_id
        state = entity.get("state", "") if entity else ""
        label = f"{name} — {state}" if state else name
        target = self._membership_list()
        if target and entity_id in self.app.entity_lists.get(target, []):
            label += " ✓"
        # Dim dead entities so unreachable devices are scannable at a glance (#148).
        # Text() also escapes any Rich markup in the HA-derived name/state (#157).
        if entity and is_dead(entity):
            return Text(label, style="dim")
        return Text(label)

    def rebuild(self) -> None:
        """Full rebuild from the app's registries + live states (registry reload,
        area move, or a grouping-mode toggle)."""
        tree = self.query_one("#device_tree", Tree)
        tree.clear()
        self._entity_nodes = {}
        self._device_nodes = {}

        if self._mode == "device":
            groups = build_device_groups(self.app.entity_registry, self.app.device_registry)
            if self._filter:
                groups = filter_device_groups(groups, self._filter, self._entity_matcher(), self._scope)
            for group in groups:
                self._add_device_node(tree.root, group)
        elif self._mode == "area":
            areas = build_area_groups(self.app.entity_registry, self.app.device_registry, self.app.area_registry)
            if self._filter:
                areas = filter_area_groups(areas, self._filter, self._entity_matcher(), self._scope)
            for area in areas:
                self._add_container_node(tree.root, area, "area", "area_id")
        else:  # integration
            groups = build_integration_groups(self.app.entity_registry, self.app.device_registry)
            if self._filter:
                groups = filter_integration_groups(groups, self._filter, self._entity_matcher(), self._scope)
            for group in groups:
                self._add_container_node(tree.root, group, "integration", "integration")

        # An all-pruned filter would otherwise leave a silently blank tree (#149).
        if self._filter and not self._entity_nodes:
            tree.root.add_leaf(Text("— no matches —", style="dim"), data={"kind": "placeholder"})

        # Rendered after the tree body so the status line's filter count reflects
        # the freshly-built _entity_nodes (issue #149).
        self.query_one("#device_tree_status", Static).update(self._status_text())
        tree.root.expand()

    def _add_container_node(self, parent, group: dict, kind: str, id_key: str) -> None:
        """Add an area/integration container node (Group → Device → Entity).
        Collapsed by default (like devices); only auto-expand while filtering so
        search hits aren't hidden (issue #145)."""
        node = parent.add(Text(group["label"]), data={"kind": kind, id_key: group[id_key]})
        for device_group in group["devices"]:
            self._add_device_node(node, device_group)
        if self._filter:
            node.expand()

    def _add_device_node(self, parent, group: dict) -> None:
        device_node = parent.add(
            Text(group["label"]),
            data={"kind": "device", "device_id": group["device_id"], "area_id": group["area_id"]},
        )
        if group["device_id"]:
            self._device_nodes.setdefault(group["device_id"], []).append(device_node)
        for entity_id in group["entity_ids"]:
            leaf = device_node.add_leaf(self._entity_label(entity_id), data={"kind": "entity", "entity_id": entity_id})
            self._entity_nodes.setdefault(entity_id, []).append(leaf)
        if self._filter:
            device_node.expand()

    def refresh_entity(self, entity_id: str) -> None:
        """Cheap live update of one entity's leaf label(s)."""
        for leaf in self._entity_nodes.get(entity_id, []):
            leaf.set_label(self._entity_label(entity_id))

    # ── cursor follow (issue #153) ──────────────────────────────────────────────

    def _focus_node(self, node) -> None:
        """Expand the node's ancestors so it's visible, then put the cursor on it.
        `expand()` only marks the node and defers the line-cache rebuild to the
        next refresh, so `node.line` (which `move_cursor` reads) would be stale;
        force the rebuild synchronously so the cursor lands deterministically."""
        tree = self.query_one("#device_tree", Tree)
        parent = node.parent
        while parent is not None:
            parent.expand()
            parent = parent.parent
        tree._invalidate()
        # Accessing _tree_lines rebuilds the cache now, refreshing every node.line.
        _ = tree._tree_lines
        tree.move_cursor(node)
        tree.scroll_to_node(node)

    def _focus_entity(self, entity_id: str | None) -> None:
        nodes = self._entity_nodes.get(entity_id or "")
        if nodes:
            self._focus_node(nodes[0])

    def _focus_device(self, device_id: str | None) -> None:
        nodes = self._device_nodes.get(device_id or "")
        if nodes:
            self._focus_node(nodes[0])

    # ── search ────────────────────────────────────────────────────────────────

    def action_toggle_search(self) -> None:
        search = self.query_one("#device_tree_search", SearchInput)
        search.action_focus_display()
        search.placeholder = self._search_placeholder()

    def action_cycle_scope(self) -> None:
        """Cycle the search scope within the current view's valid scopes (so it
        never lands on a dead scope), reflected in the placeholder + status line,
        and re-filter (issues #140/#180/#206)."""
        scopes = self._VIEW_SCOPES[self._mode]
        index = scopes.index(self._scope)
        self._scope = scopes[(index + 1) % len(scopes)]
        self.query_one("#device_tree_search", SearchInput).placeholder = self._search_placeholder()
        self.rebuild()

    def on_search_input_search_changed(self, event: SearchInput.SearchChanged) -> None:
        event.stop()
        self._filter = event.value.strip().lower()
        self.rebuild()

    def on_search_input_search_submitted(self, event: SearchInput.SearchSubmitted) -> None:
        event.stop()
        self.query_one("#device_tree", Tree).focus()

    def _clear_search(self) -> None:
        search = self.query_one("#device_tree_search", SearchInput)
        search.value = ""
        search.action_hide_display()
        self._filter = ""
        self.rebuild()
        self.query_one("#device_tree", Tree).focus()

    # ── actions ───────────────────────────────────────────────────────────────

    def action_cycle_mode(self) -> None:
        # Remember what the cursor is on so it follows into the new grouping (#153).
        node = self.query_one("#device_tree", Tree).cursor_node
        data = node.data if node and node.data else {}
        keep_entity = data.get("entity_id") if data.get("kind") == "entity" else None
        keep_device = data.get("device_id") if data.get("kind") == "device" else None

        index = self._MODES.index(self._mode)
        self._mode = self._MODES[(index + 1) % len(self._MODES)]
        # Match the new view: reset the scope to its default (issue #206), and
        # refresh the placeholder since the shown scope changed.
        self._scope = self._VIEW_SCOPES[self._mode][0]
        search = self.query_one("#device_tree_search", SearchInput)
        search.placeholder = self._search_placeholder()
        if self._filter:
            # A search filtering the old grouping shouldn't silently carry over
            # into the new one (issue #211).
            search.value = ""
            search.action_hide_display()
            self._filter = ""
        self.rebuild()

        if keep_entity:
            self._focus_entity(keep_entity)
        elif keep_device:
            self._focus_device(keep_device)

    def action_expand_all(self) -> None:
        self.query_one("#device_tree", Tree).root.expand_all()

    def action_collapse_all(self) -> None:
        root = self.query_one("#device_tree", Tree).root
        root.collapse_all()
        # Keep the hidden root expanded (issue #144) or its children vanish.
        root.expand()

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        data = event.node.data or {}
        if data.get("kind") == "entity":
            self.app.toggle_or_open_controls(data["entity_id"], fullscreen_graph_fallback=True)

    def _cursor_entity_id(self) -> str | None:
        node = self.query_one("#device_tree", Tree).cursor_node
        data = node.data if node else None
        if data and data.get("kind") == "entity":
            return data["entity_id"]
        return None

    def action_expand_entity(self) -> None:
        entity_id = self._cursor_entity_id()
        if not entity_id:
            self.app.notify("Select an entity to expand it.", severity="information")
            return
        self.app.open_entity_controls(entity_id, fullscreen_graph_fallback=True)

    def action_jump_to_list(self) -> None:
        # Dismiss the tree first so list state never changes behind it, then reuse
        # the app's jump-or-pick logic (picker only opens if no list exists yet).
        self.app.pop_to_base_screen()
        self.app.action_show_list_selection_popup()

    def action_open_dashboard(self) -> None:
        # action_show_dashboard already pops to the base screen (dismissing the
        # tree) before pushing the last-shown/default dashboard.
        self.app.action_show_dashboard()

    def action_show_help(self) -> None:
        self.app.action_show_help()

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if action == "toggle_list_membership":
            # Release the priority space binding while the filter is being typed.
            search = self.query_one("#device_tree_search", SearchInput)
            if search.display and search.has_focus:
                return False
        if action in ("area_to_dashboard", "create_area"):
            return self._mode == "area"
        return True

    def action_toggle_list_membership(self) -> None:
        tree = self.query_one("#device_tree", Tree)
        node = tree.cursor_node
        data = node.data if node else None
        if not data or data.get("kind") != "entity":
            # Keep space as expand/collapse on container nodes.
            tree.action_toggle_node()
            return

        entity_id = data["entity_id"]
        target = self._membership_list()
        if target is None:
            from hatty.ui.list_selection_popup import ListSelectionPopup

            def _picked(result) -> None:
                if isinstance(result, str):
                    self.app.select_or_create_list(result)
                    self._apply_membership_toggle(result, entity_id)

            self.app.push_screen(ListSelectionPopup(), _picked)
            return
        self._apply_membership_toggle(target, entity_id)

    def _apply_membership_toggle(self, list_name: str, entity_id: str) -> None:
        action = "remove" if entity_id in self.app.entity_lists.get(list_name, []) else "add"
        self.app.list_ctl.apply_membership(list_name, entity_id, action)
        self.app.list_ctl.record_toggle(list_name, entity_id, action)
        verb, prep = ("Removed", "from") if action == "remove" else ("Added", "to")
        self.app.notify(f"{verb} {entity_id} {prep} {list_name}", title="List Updated")
        # apply_membership refreshes the (hidden) main table, not the tree.
        self.refresh_entity(entity_id)

    def action_graph_fullscreen(self) -> None:
        from hatty.ui.graph.preview_screen import GraphPreviewScreen

        entity_id = self._cursor_entity_id()
        if not entity_id:
            self.app.notify("Select an entity to graph it.", severity="information")
            return
        entity = self.app.find_entity(entity_id)
        if not entity or not self.app.graph_ctl.is_graphable(entity):
            self.app.notify("No graph available for this entity type.", severity="warning")
            return
        self.app.push_screen(
            GraphPreviewScreen(
                [entity_id],
                initial_graph_type=self.app.app_config.get(CONFIG_KEY_GRAPH_TYPE),
            )
        )

    def action_device_info(self) -> None:
        node = self.query_one("#device_tree", Tree).cursor_node
        if node is None or node.data is None:
            return
        data = node.data
        kind = data.get("kind")

        if kind == "device" and data.get("device_id"):
            device = next((d for d in self.app.device_registry if d.get("id") == data["device_id"]), None)
            if device is None:
                self.app.notify("Device not found in the registry.", severity="warning")
                return
            entity_count = sum(1 for c in node.children if (c.data or {}).get("kind") == "entity")
            rows = device_info_rows(device, self.app.area_registry, self.app.device_registry, entity_count)
            self.app.push_screen(DeviceInfoPopup(device_display_name(device), rows))
            return

        if kind == "entity":
            entity_id = data["entity_id"]
            entry = next((e for e in self.app.entity_registry if e.get("entity_id") == entity_id), {})
            by_id = {d.get("id"): d for d in self.app.device_registry if d.get("id")}
            device = by_id.get(entry.get("device_id"))
            rows = [
                ("Entity ID", entity_id),
                ("Integration", entry.get("platform") or ""),
                ("Device", device_display_name(device) if device else ""),
                ("Category", entry.get("entity_category") or ""),
            ]
            rows = [(label, value) for label, value in rows if value]
            title = get_display_name(self.app.find_entity(entity_id) or {"entity_id": entity_id})
            self.app.push_screen(DeviceInfoPopup(title, rows))
            return

        self.app.notify("Select a device to see its info.", severity="information")

    def action_move_device(self) -> None:
        node = self.query_one("#device_tree", Tree).cursor_node
        data = node.data if node else None
        if node is None or not data or data.get("kind") != "device" or not data.get("device_id"):
            self.app.notify("Select a device to move it to an area.", severity="information")
            return

        device_id = data["device_id"]
        label = str(node.label)
        areas = sorted(
            ((a.get("area_id"), area_display_name(a)) for a in self.app.area_registry if a.get("area_id")),
            key=lambda pair: pair[1].lower(),
        )

        def _picked(result) -> None:
            if result is None:
                return
            self.app.spawn(self.app.client.update_device_registry(device_id, result["area_id"]))

        self.app.push_screen(AreaPickerPopup(label, areas), _picked)

    def action_create_area(self) -> None:
        def _named(name) -> None:
            if name:
                self.app.spawn(self.app.client.create_area(name))

        self.app.push_screen(AreaNamePopup("Create Area"), _named)

    def action_rename(self) -> None:
        """Rename dispatched by node kind (issue #152): entity leaves reuse the
        main table's rename seam, devices push a name popup writing `name_by_user`,
        and area nodes keep the existing area-rename flow."""
        node = self.query_one("#device_tree", Tree).cursor_node
        if node is None or node.data is None:
            return
        data = node.data
        kind = data.get("kind")

        if kind == "entity":
            self.app.open_rename_for_entity(data["entity_id"])
            return

        if kind == "device" and data.get("device_id"):
            device_id = data["device_id"]

            def _renamed(name) -> None:
                if name:
                    self.app.spawn(self.app.client.update_device_registry(device_id, name_by_user=name))

            self.app.push_screen(
                AreaNamePopup("Rename Device", str(node.label), placeholder="Device name..."),
                _renamed,
            )
            return

        if kind == "area" and data.get("area_id"):
            area_id = data["area_id"]

            def _named(name) -> None:
                if name:
                    self.app.spawn(self.app.client.rename_area(area_id, name))

            self.app.push_screen(AreaNamePopup("Rename Area", str(node.label)), _named)
            return

        self.app.notify("Select an entity, device, or area to rename it.", severity="information")

    def action_area_to_dashboard(self) -> None:
        node = self.query_one("#device_tree", Tree).cursor_node
        data = node.data if node else None
        if node is None or not data or data.get("kind") != "area" or not data.get("area_id"):
            self.app.notify("Select an area node to create a dashboard from it.", severity="information")
            return

        # Walk the *tree node's* descendants rather than re-deriving from the
        # registries, so an active search filter scopes the dashboard.
        entity_ids = [
            (leaf.data or {}).get("entity_id")
            for device_node in node.children
            for leaf in device_node.children
            if (leaf.data or {}).get("kind") == "entity"
        ]
        categories = {e.get("entity_id"): e.get("entity_category") for e in self.app.entity_registry}
        entity_ids = [eid for eid in entity_ids if eid and categories.get(eid) not in ("diagnostic", "config")]
        if not entity_ids:
            self.app.notify("No dashboard-worthy entities in this area.", severity="warning")
            return
        if len(entity_ids) > MAX_AREA_DASHBOARD_SLOTS:
            self.app.notify(
                f"Area has {len(entity_ids)} entities; using the first {MAX_AREA_DASHBOARD_SLOTS}.",
                severity="information",
            )
            entity_ids = entity_ids[:MAX_AREA_DASHBOARD_SLOTS]

        name = self.app.dash_ctl.create_populated(str(node.label), entity_ids)
        self.app.notify(f"Created dashboard '{name}'.", title="Dashboard Created")

        from hatty.ui.dashboard.screen import DashboardScreen

        # Pushed on top of the tree (not action_show_dashboard, which pops to
        # the base screen and would dismiss the tree).
        self.app.push_screen(DashboardScreen())

    def action_go_back(self) -> None:
        search = self.query_one("#device_tree_search", SearchInput)
        if search.display or self._filter:
            self._clear_search()
            return
        # Hand the cursored entity back so the main table lands on it (#153).
        self.dismiss(self._cursor_entity_id())
