"""Coordinate-based route optimizer for Star Citizen navigation.

Loads the curated location dataset (data/sc_locations.json) and computes
distances at runtime. Quantum travel is straight-line, so Euclidean distance
over the raw meter coordinates is the correct model; results are reported in
Gigameters (Gm). Cross-system distances are found by searching the gateway
graph (Dijkstra), with the jump itself costing nothing.

Location names duplicate across systems (each system has a "Stanton Gateway"
and so on), so every location carries a display key: the plain name when it is
globally unique, otherwise "Name (System)". All routes, legs, and tool outputs
speak in display keys; name/system/type stay accessible per location.

Stdlib only; safe to import standalone (no wingman host dependencies).
"""

from __future__ import annotations

import heapq
import itertools
import json
import math
import re
from dataclasses import dataclass, field
from itertools import permutations
from pathlib import Path


# Meters per Gigameter; source coordinates are meters, output is Gm.
METERS_PER_GM = 1e9

# Brute-force TSP is exact and fast up to 8 free waypoints (8! = 40320).
BRUTE_FORCE_LIMIT = 8

# Resolver outcomes.
MATCHED = "matched"
AMBIGUOUS = "ambiguous"
NOT_FOUND = "not_found"

_NON_ALNUM = re.compile(r"[^a-z0-9]")


def _normalize(text: str) -> str:
    """Lowercase and strip every non-alphanumeric character for matching."""
    return _NON_ALNUM.sub("", text.lower())


@dataclass(frozen=True)
class Location:
    """A single quantum-travel destination with raw meter coordinates."""

    name: str
    system: str
    type: str
    x: float
    y: float
    z: float
    display_key: str


@dataclass
class ResolveResult:
    """Outcome of resolving a spoken location name.

    Attributes:
        status: One of MATCHED, AMBIGUOUS, or NOT_FOUND.
        location: The resolved location when status is MATCHED, else None.
        candidates: Display keys of the tied candidates when AMBIGUOUS.
    """

    status: str
    location: Location | None = None
    candidates: list[str] = field(default_factory=list)


class RouteOptimizer:
    """Route planning, distance lookup, and location resolution."""

    def __init__(self, data_path: str | None = None) -> None:
        if data_path is None:
            data_path = str(Path(__file__).parent / "data" / "sc_locations.json")
        with open(data_path, encoding="utf-8") as handle:
            data = json.load(handle)

        self.metadata: dict = data.get("metadata", {})
        raw_locations: list[dict] = data["locations"]
        raw_links: list[dict] = data.get("gateway_links", [])
        raw_aliases: dict[str, str] = data.get("aliases", {})

        # A name is globally unique when it appears once across all systems;
        # otherwise the display key qualifies it with the system.
        name_counts: dict[str, int] = {}
        for loc in raw_locations:
            name_counts[loc["name"]] = name_counts.get(loc["name"], 0) + 1

        self._locations: list[Location] = []
        self._by_display: dict[str, Location] = {}
        self._by_sys_name: dict[tuple[str, str], Location] = {}
        self._by_name: dict[str, list[Location]] = {}
        self._by_norm: dict[str, list[Location]] = {}

        for loc in raw_locations:
            name = loc["name"]
            system = loc["system"]
            display = name if name_counts[name] == 1 else f"{name} ({system})"
            location = Location(
                name=name,
                system=system,
                type=loc.get("type", ""),
                x=float(loc["x"]),
                y=float(loc["y"]),
                z=float(loc["z"]),
                display_key=display,
            )
            self._locations.append(location)
            self._by_display[display] = location
            self._by_sys_name[(system, name)] = location
            self._by_name.setdefault(name, []).append(location)
            self._by_norm.setdefault(_normalize(name), []).append(location)

        # Alias keys are normalized spoken forms mapping to canonical names.
        self._aliases: dict[str, str] = {
            _normalize(spoken): canonical for spoken, canonical in raw_aliases.items()
        }

        # Gateway graph: which gateways in a system participate in a jump, and
        # where each jump exits. Terra Gateway (no target system) is absent.
        self._gateways: dict[str, list[Location]] = {}
        self._transit: dict[tuple[str, str], list[tuple[str, str]]] = {}
        for link in raw_links:
            self._register_link(
                link["system_a"],
                link["gateway_a"],
                link["system_b"],
                link["gateway_b"],
            )

    def _register_link(
        self, system_a: str, gateway_a: str, system_b: str, gateway_b: str
    ) -> None:
        """Record one undirected jump link in the gateway graph."""
        loc_a = self._by_sys_name.get((system_a, gateway_a))
        loc_b = self._by_sys_name.get((system_b, gateway_b))
        if loc_a is None or loc_b is None:
            return
        self._gateways.setdefault(system_a, []).append(loc_a)
        self._gateways.setdefault(system_b, []).append(loc_b)
        self._transit.setdefault((system_a, gateway_a), []).append(
            (system_b, gateway_b)
        )
        self._transit.setdefault((system_b, gateway_b), []).append(
            (system_a, gateway_a)
        )

    # -- Resolution ------------------------------------------------------

    def resolve_location(self, name: str, system: str = "") -> ResolveResult:
        """Resolve a spoken name to a single location.

        Matching runs in order: exact display key, exact name, normalized
        exact, alias map, then unique normalized-substring. A system argument
        restricts the candidate pool (case-insensitive) before any uniqueness
        test. The first stage that produces one candidate matches; a stage
        that produces two or more is ambiguous; exhausting all stages is not
        found.

        Args:
            name: The spoken location name.
            system: Optional system filter (e.g. "Stanton").

        Returns:
            A ResolveResult carrying the outcome.
        """
        pool = self._locations
        if system:
            wanted = system.lower()
            pool = [loc for loc in pool if loc.system.lower() == wanted]
            if not pool:
                return ResolveResult(NOT_FOUND)

        exact_display = [loc for loc in pool if loc.display_key == name]
        exact_name = [loc for loc in pool if loc.name == name]
        norm_query = _normalize(name)
        norm_exact = [loc for loc in pool if _normalize(loc.name) == norm_query]

        alias_matches: list[Location] = []
        canonical = self._aliases.get(norm_query)
        if canonical is not None:
            alias_matches = [loc for loc in pool if loc.name == canonical]

        substring = [loc for loc in pool if norm_query and norm_query in _normalize(loc.name)]

        for candidates in (exact_display, exact_name, norm_exact, alias_matches, substring):
            if len(candidates) == 1:
                return ResolveResult(MATCHED, location=candidates[0])
            if len(candidates) >= 2:
                return ResolveResult(
                    AMBIGUOUS,
                    candidates=sorted(loc.display_key for loc in candidates),
                )

        return ResolveResult(NOT_FOUND)

    def get_system(self, display_key: str) -> str | None:
        """Return the system for a display key, or None if unknown."""
        loc = self._by_display.get(display_key)
        return loc.system if loc is not None else None

    def find_locations(self, query: str, system: str = "") -> list[dict]:
        """Search locations by normalized-substring match.

        Args:
            query: Partial name to search for.
            system: Optional system filter (case-insensitive).

        Returns:
            A list of {"name": display_key, "system": system} dicts, sorted
            by display key.
        """
        norm_query = _normalize(query)
        wanted = system.lower() if system else ""
        results = []
        for loc in self._locations:
            if wanted and loc.system.lower() != wanted:
                continue
            if norm_query and norm_query in _normalize(loc.name):
                results.append({"name": loc.display_key, "system": loc.system})
        return sorted(results, key=lambda item: item["name"])

    # -- Distances -------------------------------------------------------

    def _euclid_gm(self, a: Location, b: Location) -> float:
        """Straight-line distance between two locations in Gigameters."""
        return (
            math.dist((a.x, a.y, a.z), (b.x, b.y, b.z)) / METERS_PER_GM
        )

    def get_distance(
        self, a: str, b: str
    ) -> tuple[float | None, list[str]]:
        """Distance between two display keys and the gateways traversed.

        Args:
            a: Origin display key.
            b: Destination display key.

        Returns:
            (distance_gm, via). distance_gm is None only when a or b is
            unknown or the systems have no path between them; 0.0 is a valid
            distance. via lists the gateway display keys traversed (exit then
            entry per hop), empty for same-system routes.
        """
        loc_a = self._by_display.get(a)
        loc_b = self._by_display.get(b)
        if loc_a is None or loc_b is None:
            return None, []
        if loc_a.system == loc_b.system:
            return self._euclid_gm(loc_a, loc_b), []
        return self._cross_system(loc_a, loc_b)

    def _cross_system(
        self, origin: Location, target: Location
    ) -> tuple[float | None, list[str]]:
        """Shortest gateway route between two systems via Dijkstra.

        Nodes are the origin, the target, and every routing gateway. Moving
        within a system to a gateway (or to the target) costs the straight-line
        distance; a jump through a gateway costs 0 Gm and records the exit and
        entry gateway display keys.
        """
        counter = itertools.count()
        start_node: tuple = ("origin",)
        heap: list[tuple[float, int, tuple, list[str]]] = [
            (0.0, next(counter), start_node, [])
        ]
        visited: set[tuple] = set()

        while heap:
            cost, _, node, via = heapq.heappop(heap)
            if node in visited:
                continue
            visited.add(node)
            if node == ("target",):
                return cost, via
            for next_node, edge_cost, via_step in self._neighbors(
                node, origin, target
            ):
                if next_node in visited:
                    continue
                heapq.heappush(
                    heap,
                    (cost + edge_cost, next(counter), next_node, via + via_step),
                )

        return None, []

    def _node_location(
        self, node: tuple, origin: Location, target: Location
    ) -> Location:
        """Resolve a search node to its backing location."""
        if node == ("origin",):
            return origin
        if node == ("target",):
            return target
        return self._by_sys_name[(node[1], node[2])]

    def _neighbors(
        self, node: tuple, origin: Location, target: Location
    ) -> list[tuple[tuple, float, list[str]]]:
        """Expand a search node into (next_node, cost, via_step) edges."""
        here = self._node_location(node, origin, target)
        system = here.system
        edges: list[tuple[tuple, float, list[str]]] = []

        for gateway in self._gateways.get(system, []):
            gateway_node = ("gw", gateway.system, gateway.name)
            if gateway_node == node:
                continue
            edges.append((gateway_node, self._euclid_gm(here, gateway), []))

        if node[0] == "gw":
            for linked_system, linked_name in self._transit.get(
                (node[1], node[2]), []
            ):
                entry = self._by_sys_name[(linked_system, linked_name)]
                edges.append(
                    (
                        ("gw", linked_system, linked_name),
                        0.0,
                        [here.display_key, entry.display_key],
                    )
                )

        if system == target.system:
            edges.append((("target",), self._euclid_gm(here, target), []))

        return edges

    def _leg_cost(self, a: str, b: str) -> float:
        """Distance for optimization; unreachable legs weigh infinity."""
        distance, _ = self.get_distance(a, b)
        return math.inf if distance is None else distance

    def _route_distance(self, route: list[str]) -> float:
        """Total straight-line distance along a sequence of display keys."""
        return sum(
            self._leg_cost(route[i], route[i + 1]) for i in range(len(route) - 1)
        )

    # -- TSP -------------------------------------------------------------

    def optimize_route(
        self,
        waypoints: list[str],
        start_location: str = "",
        end_location: str = "",
        return_to_start: bool = False,
    ) -> dict:
        """Find the shortest visit order for a set of waypoints.

        Args:
            waypoints: Spoken location names to visit.
            start_location: Pinned start (optional). When empty and the
                heuristic path is used, every waypoint is tried as a start.
            end_location: Pinned final destination (optional).
            return_to_start: Close the route back to the start.

        Returns:
            A dict with route, legs, total_distance_gm, num_stops, and
            algorithm. Cross-system legs carry via_gateways; unreachable legs
            are flagged and named in a top-level warnings list.
        """
        resolved, errors = self._resolve_all(waypoints)
        start, start_err = self._resolve_one(start_location, "start location")
        end, end_err = self._resolve_one(end_location, "end location")
        errors.extend(err for err in (start_err, end_err) if err)

        if errors:
            return {"error": "; ".join(errors), "route": [], "total_distance_gm": 0}
        if not resolved:
            return {
                "error": "No valid waypoints provided",
                "route": [],
                "total_distance_gm": 0,
            }

        to_visit = [key for key in resolved if key != start and key != end]
        closed = return_to_start and bool(start)

        if not to_visit:
            route = [key for key in (start, end) if key]
            if not route:
                return {
                    "error": "No locations to route",
                    "route": [],
                    "total_distance_gm": 0,
                }
            if closed and route[-1] != start:
                route.append(start)
        elif len(to_visit) <= BRUTE_FORCE_LIMIT:
            route = self._brute_force(to_visit, start, end, closed)
        else:
            route = self._nearest_neighbor(to_visit, start, end, closed)
            route = self._two_opt(route)

        algorithm = (
            "brute_force" if len(to_visit) <= BRUTE_FORCE_LIMIT
            else "nearest_neighbor_2opt"
        )
        return self._build_result(route, algorithm)

    def _resolve_all(self, waypoints: list[str]) -> tuple[list[str], list[str]]:
        """Resolve waypoints to display keys, collecting errors and dedup."""
        resolved: list[str] = []
        errors: list[str] = []
        for waypoint in waypoints:
            result = self.resolve_location(waypoint)
            if result.status == MATCHED and result.location is not None:
                key = result.location.display_key
                if key not in resolved:
                    resolved.append(key)
            elif result.status == AMBIGUOUS:
                errors.append(
                    f"Ambiguous location '{waypoint}': candidates "
                    f"{result.candidates}; specify the system."
                )
            else:
                errors.append(f"Unknown location: '{waypoint}'")
        return resolved, errors

    def _resolve_one(
        self, name: str, label: str
    ) -> tuple[str, str | None]:
        """Resolve a single optional pinned location (start or end)."""
        if not name:
            return "", None
        result = self.resolve_location(name)
        if result.status == MATCHED and result.location is not None:
            return result.location.display_key, None
        if result.status == AMBIGUOUS:
            return "", (
                f"Ambiguous {label} '{name}': candidates {result.candidates}; "
                f"specify the system."
            )
        return "", f"Unknown {label}: '{name}'"

    def _build_result(self, route: list[str], algorithm: str) -> dict:
        """Assemble the tool result, pricing and flagging each leg."""
        legs = []
        warnings = []
        total = 0.0
        for i in range(len(route) - 1):
            distance, via = self.get_distance(route[i], route[i + 1])
            leg: dict = {"from": route[i], "to": route[i + 1]}
            if distance is None:
                leg["distance_gm"] = None
                leg["unreachable"] = True
                warnings.append(f"No route between '{route[i]}' and '{route[i + 1]}'")
            else:
                leg["distance_gm"] = round(distance, 3)
                total += distance
            if via:
                leg["via_gateways"] = via
            legs.append(leg)

        result = {
            "route": route,
            "legs": legs,
            "total_distance_gm": round(total, 3),
            "num_stops": len(route),
            "algorithm": algorithm,
        }
        if warnings:
            result["warnings"] = warnings
        return result

    def _assemble(
        self, order: list[str], start: str, end: str, closed: bool
    ) -> list[str]:
        """Wrap an ordering of free waypoints with pinned start/end/return."""
        route: list[str] = []
        if start:
            route.append(start)
        route.extend(order)
        if end:
            route.append(end)
        if closed and route and route[-1] != start:
            route.append(start)
        return route

    def _brute_force(
        self, waypoints: list[str], start: str, end: str, closed: bool
    ) -> list[str]:
        """Exact shortest order by trying every permutation."""
        best_route: list[str] | None = None
        best_dist = math.inf
        for perm in permutations(waypoints):
            route = self._assemble(list(perm), start, end, closed)
            dist = self._route_distance(route)
            if dist < best_dist:
                best_dist = dist
                best_route = route
        return best_route if best_route is not None else self._assemble(
            list(waypoints), start, end, closed
        )

    def _nn_order(self, free: list[str], anchor: str) -> list[str]:
        """Greedy nearest-neighbor ordering of free keys from an anchor."""
        unvisited = set(free)
        order: list[str] = []
        current = anchor
        while unvisited:
            nearest = min(unvisited, key=lambda key: self._leg_cost(current, key))
            order.append(nearest)
            unvisited.discard(nearest)
            current = nearest
        return order

    def _nearest_neighbor(
        self, waypoints: list[str], start: str, end: str, closed: bool
    ) -> list[str]:
        """Nearest-neighbor route; multi-start when no start is pinned."""
        if start:
            order = self._nn_order(waypoints, start)
            return self._assemble(order, start, end, closed)

        best_route: list[str] | None = None
        best_dist = math.inf
        for seed in waypoints:
            rest = [key for key in waypoints if key != seed]
            order = [seed, *self._nn_order(rest, seed)]
            route = self._assemble(order, "", end, closed)
            dist = self._route_distance(route)
            if dist < best_dist:
                best_dist = dist
                best_route = route
        return best_route if best_route is not None else self._assemble(
            list(waypoints), "", end, closed
        )

    def _two_opt(self, route: list[str]) -> list[str]:
        """Refine a route with 2-opt swaps, endpoints fixed.

        The inner edge ``(route[j], route[j + 1])`` is only considered up to
        ``j == n - 2``, so no phantom wraparound edge is ever introduced. This
        is what makes both route shapes correct without a branch: an open
        route keeps its two path endpoints and gains no closing edge, while a
        closed route (return_to_start) carries the start as a real duplicated
        last element, so its closing edge is a genuine edge the loop prices.
        """
        n = len(route)
        if n < 4:
            return route
        improved = True
        while improved:
            improved = False
            for i in range(1, n - 1):
                for j in range(i + 1, n - 1):
                    a, b = route[i - 1], route[i]
                    c, d = route[j], route[j + 1]
                    before = self._leg_cost(a, b) + self._leg_cost(c, d)
                    after = self._leg_cost(a, c) + self._leg_cost(b, d)
                    if after < before - 1e-9:
                        route[i : j + 1] = route[i : j + 1][::-1]
                        improved = True
        return route
