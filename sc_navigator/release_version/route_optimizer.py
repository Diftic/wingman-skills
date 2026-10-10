"""
Route optimizer for Star Citizen navigation.
Loads precomputed distance matrix and provides TSP-based route planning,
distance lookups, and fuzzy location search.
"""

import json
import os
from itertools import permutations

# Gateway pairs connecting star systems.
# Each tuple: (gateway in system A, system A, gateway in system B, system B)
GATEWAY_PAIRS = [
    ("Pyro Gateway", "Stanton", "Stanton Gateway", "Pyro"),
    ("Nyx Gateway", "Stanton", "Stanton Gateway", "Nyx"),
    ("Nyx Gateway", "Pyro", "Pyro Gateway", "Nyx"),
]

# Max waypoints for brute-force (8! = 40320 permutations)
BRUTE_FORCE_LIMIT = 8


class RouteOptimizer:
    def __init__(self, data_path: str | None = None):
        if data_path is None:
            data_path = os.path.join(
                os.path.dirname(__file__), "data", "sc_distances.json"
            )
        with open(data_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self._distances: dict[str, dict[str, float]] = data["distances"]
        self._systems: dict[str, list[str]] = data["systems"]
        self._all_locations: set[str] = set(self._distances.keys())

        # Build reverse lookup: location -> system
        self._location_system: dict[str, str] = {}
        for system, locs in self._systems.items():
            for loc in locs:
                self._location_system[loc] = system

        # Build case-insensitive lookup
        self._name_lower: dict[str, str] = {
            loc.lower(): loc for loc in self._all_locations
        }

    # ── Distance lookup ──────────────────────────────────────────────

    def get_system(self, location: str) -> str | None:
        return self._location_system.get(location)

    def get_same_system_distance(self, a: str, b: str) -> float | None:
        """Direct distance within the same system. Returns None if not found."""
        entry = self._distances.get(a)
        if entry is None:
            return None
        return entry.get(b)

    def get_distance(self, a: str, b: str) -> tuple[float | None, list[str]]:
        """
        Get distance between any two locations, including cross-system.
        Returns (distance_gm, route_via) where route_via lists gateway hops.
        """
        # Try direct (same-system)
        d = self.get_same_system_distance(a, b)
        if d is not None:
            return d, []

        # Cross-system: find gateway path
        sys_a = self.get_system(a)
        sys_b = self.get_system(b)
        if sys_a is None or sys_b is None:
            return None, []

        best_dist = None
        best_via = []

        for gw_a, gw_sys_a, gw_b, gw_sys_b in GATEWAY_PAIRS:
            # Check both directions of this gateway pair
            for ga, sa, gb, sb in [
                (gw_a, gw_sys_a, gw_b, gw_sys_b),
                (gw_b, gw_sys_b, gw_a, gw_sys_a),
            ]:
                if sa == sys_a and sb == sys_b:
                    d_a = self.get_same_system_distance(a, ga)
                    d_b = self.get_same_system_distance(gb, b)
                    if d_a is not None and d_b is not None:
                        total = d_a + d_b
                        if best_dist is None or total < best_dist:
                            best_dist = total
                            best_via = [ga, gb]

        # Two-hop: A_system -> mid_system -> B_system
        if best_dist is None:
            for gw1_a, gw1_sa, gw1_b, gw1_sb in GATEWAY_PAIRS:
                for gw2_a, gw2_sa, gw2_b, gw2_sb in GATEWAY_PAIRS:
                    for ga, sa, gb, sb in [
                        (gw1_a, gw1_sa, gw1_b, gw1_sb),
                        (gw1_b, gw1_sb, gw1_a, gw1_sa),
                    ]:
                        for gc, sc, gd, sd in [
                            (gw2_a, gw2_sa, gw2_b, gw2_sb),
                            (gw2_b, gw2_sb, gw2_a, gw2_sa),
                        ]:
                            if sa == sys_a and sb == sc and sd == sys_b:
                                d1 = self.get_same_system_distance(a, ga)
                                d2 = self.get_same_system_distance(gb, gc)
                                d3 = self.get_same_system_distance(gd, b)
                                if d1 is not None and d2 is not None and d3 is not None:
                                    total = d1 + d2 + d3
                                    if best_dist is None or total < best_dist:
                                        best_dist = total
                                        best_via = [ga, gb, gc, gd]

        return best_dist, best_via

    def _route_distance(self, route: list[str]) -> float:
        """Total distance along a sequence of locations."""
        total = 0.0
        for i in range(len(route) - 1):
            d, _ = self.get_distance(route[i], route[i + 1])
            if d is None:
                return float("inf")
            total += d
        return total

    # ── Location search ──────────────────────────────────────────────

    def resolve_location(self, name: str) -> str | None:
        """Resolve a location name (case-insensitive exact match)."""
        if name in self._all_locations:
            return name
        return self._name_lower.get(name.lower())

    def find_locations(self, query: str, system: str = "") -> list[dict]:
        """Fuzzy search for locations by substring match."""
        query_lower = query.lower()
        results = []
        for loc in sorted(self._all_locations):
            if query_lower in loc.lower():
                loc_sys = self.get_system(loc)
                if system and loc_sys and loc_sys.lower() != system.lower():
                    continue
                results.append({"name": loc, "system": loc_sys or "unknown"})
        return results

    # ── TSP solver ───────────────────────────────────────────────────

    def optimize_route(
        self,
        waypoints: list[str],
        start_location: str = "",
        end_location: str = "",
        return_to_start: bool = False,
    ) -> dict:
        """
        Find optimal visit order for waypoints.
        Returns dict with route, legs, total_distance, and algorithm used.
        """
        # Resolve all location names
        resolved = []
        errors = []
        for wp in waypoints:
            r = self.resolve_location(wp)
            if r is None:
                errors.append(f"Unknown location: '{wp}'")
            elif r not in resolved:
                resolved.append(r)

        start = None
        if start_location:
            start = self.resolve_location(start_location)
            if start is None:
                errors.append(f"Unknown start location: '{start_location}'")

        end = None
        if end_location:
            end = self.resolve_location(end_location)
            if end is None:
                errors.append(f"Unknown end location: '{end_location}'")

        if errors:
            return {"error": "; ".join(errors), "route": [], "total_distance_gm": 0}

        if not resolved:
            return {"error": "No valid waypoints provided", "route": [], "total_distance_gm": 0}

        # Remove start/end from waypoints if present (they'll be pinned)
        to_visit = [loc for loc in resolved if loc != start and loc != end]

        if len(to_visit) == 0:
            # Only start and/or end
            route = [x for x in [start, end] if x]
            if not route:
                return {"error": "No locations to route", "route": [], "total_distance_gm": 0}
        elif len(to_visit) <= BRUTE_FORCE_LIMIT:
            route = self._brute_force(to_visit, start, end, return_to_start)
        else:
            route = self._nearest_neighbor(to_visit, start, end, return_to_start)
            route = self._two_opt(route, start, end, return_to_start)

        # Build result with per-leg details
        legs = []
        total = 0.0
        for i in range(len(route) - 1):
            d, via = self.get_distance(route[i], route[i + 1])
            leg_dist = d if d is not None else 0.0
            total += leg_dist
            leg = {
                "from": route[i],
                "to": route[i + 1],
                "distance_gm": round(leg_dist, 3),
            }
            if via:
                leg["via_gateways"] = via
            legs.append(leg)

        algorithm = "brute_force" if len(to_visit) <= BRUTE_FORCE_LIMIT else "nearest_neighbor_2opt"

        return {
            "route": route,
            "legs": legs,
            "total_distance_gm": round(total, 3),
            "num_stops": len(route),
            "algorithm": algorithm,
        }

    def _brute_force(
        self,
        waypoints: list[str],
        start: str | None,
        end: str | None,
        return_to_start: bool,
    ) -> list[str]:
        """Try all permutations to find optimal route."""
        best_route = None
        best_dist = float("inf")

        for perm in permutations(waypoints):
            route = list(perm)
            if start:
                route = [start] + route
            if end and end != (route[-1] if route else None):
                route = route + [end]
            if return_to_start and start and route[-1] != start:
                route = route + [start]

            d = self._route_distance(route)
            if d < best_dist:
                best_dist = d
                best_route = route

        return best_route or ([start] if start else waypoints)

    def _nearest_neighbor(
        self,
        waypoints: list[str],
        start: str | None,
        end: str | None,
        return_to_start: bool,
    ) -> list[str]:
        """Greedy nearest-neighbor heuristic."""
        unvisited = set(waypoints)
        current = start or waypoints[0]
        if current in unvisited:
            unvisited.discard(current)
        route = [current]

        # If end is specified, don't visit it until the end
        if end and end in unvisited:
            unvisited.discard(end)

        while unvisited:
            nearest = min(unvisited, key=lambda loc: self.get_distance(current, loc)[0] or float("inf"))
            route.append(nearest)
            unvisited.discard(nearest)
            current = nearest

        if end and end != route[-1]:
            route.append(end)
        if return_to_start and start and route[-1] != start:
            route.append(start)

        return route

    def _two_opt(
        self,
        route: list[str],
        start: str | None,
        end: str | None,
        return_to_start: bool,
    ) -> list[str]:
        """Improve route with 2-opt edge swaps."""
        # Determine which indices are fixed (not swappable)
        fix_start = 1 if start else 0
        fix_end = len(route) - 1 if (end or return_to_start) else len(route)

        improved = True
        while improved:
            improved = False
            for i in range(fix_start, fix_end - 1):
                for j in range(i + 1, fix_end):
                    # Cost of current edges
                    d_old = (
                        (self.get_distance(route[i - 1], route[i])[0] or 0)
                        + (self.get_distance(route[j], route[j + 1] if j + 1 < len(route) else route[0])[0] or 0)
                    )
                    # Cost if we reverse segment [i..j]
                    d_new = (
                        (self.get_distance(route[i - 1], route[j])[0] or 0)
                        + (self.get_distance(route[i], route[j + 1] if j + 1 < len(route) else route[0])[0] or 0)
                    )
                    if d_new < d_old - 1e-9:
                        route[i : j + 1] = route[i : j + 1][::-1]
                        improved = True

        return route
