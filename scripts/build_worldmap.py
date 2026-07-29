#!/usr/bin/env python3
"""Turn a world GeoJSON into compact SVG paths for the dashboard map.

Run once against a downloaded GeoJSON; the output is committed and served
locally. This is a BUILD-time download, not a runtime CDN dependency: the
published page fetches nothing external, which is the repo's standing rule.

The raw file is 257kb of full-precision coordinates, far more detail than a
1000x500 viewBox can show. Projecting first and then rounding to the pixel
grid throws away only detail that could never have rendered, which is what
gets it under 100kb without a simplification library.

Usage:
  curl -o /tmp/world.geo.json https://raw.githubusercontent.com/johan/world.geo.json/master/countries.geo.json
  python3 scripts/build_worldmap.py /tmp/world.geo.json
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "dashboard" / "world-paths.json"

W, H = 1000.0, 500.0
# Antarctica is a third of the vertical space and will never hold a company.
# Clipping the latitude range also stops Greenland dominating the frame.
LAT_MAX, LAT_MIN = 84.0, -56.0
SKIP = {"Antarctica"}
# Drop islands smaller than this in projected units squared: at 1000x500 they
# are sub-pixel specks that cost bytes and render as noise. Countries that lose
# ALL their geometry this way (Singapore, Luxembourg, Malta, Bahrain) are not
# dropped: they get a centroid point instead, so a country holding data can
# never silently disappear from the map.
MIN_AREA = 0.6

# GeoJSON names -> the names used in radar.geo / hq_location.
RENAME = {
    "United States of America": "United States",
    "Republic of Korea": "Korea",
    "South Korea": "Korea",
    "Korea, Republic of": "Korea",
    "Russian Federation": "Russia",
    "Czech Republic": "Czechia",
    "Republic of Serbia": "Serbia",
    "United Republic of Tanzania": "Tanzania",
    "Viet Nam": "Vietnam",
    "Iran (Islamic Republic of)": "Iran",
    "Syrian Arab Republic": "Syria",
    "Lao PDR": "Laos",
    "Democratic Republic of the Congo": "DR Congo",
    "Republic of the Congo": "Congo",
    "Côte d'Ivoire": "Ivory Coast",
    "Macedonia": "North Macedonia",
    "Bosnia and Herzegovina": "Bosnia",
}


# City-states and micro-states absent from the source GeoJSON entirely. This
# is not a threshold problem: the file has 180 features and simply omits them.
# Without this, a country holding real data renders nowhere and the map quietly
# undercounts. Values are (lon, lat) of the city centre.
EXTRA_POINTS = {
    "Singapore": (103.82, 1.35),
    "Hong Kong": (114.17, 22.32),
    "Bahrain": (50.55, 26.07),
    "Monaco": (7.42, 43.74),
    "Liechtenstein": (9.55, 47.17),
}


def project(lon, lat):
    x = (lon + 180.0) / 360.0 * W
    y = (LAT_MAX - lat) / (LAT_MAX - LAT_MIN) * H
    return x, y


def ring_stats(pts):
    """Shoelace area and area-weighted centroid of a projected ring."""
    a = cx = cy = 0.0
    n = len(pts)
    for i in range(n):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % n]
        cross = x0 * y1 - x1 * y0
        a += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    a *= 0.5
    if abs(a) < 1e-9:
        return 0.0, (pts[0][0], pts[0][1])
    return abs(a), (cx / (6 * a), cy / (6 * a))


def ring_to_path(ring):
    pts = []
    last = None
    for lon, lat in ring:
        if lat > LAT_MAX or lat < LAT_MIN:
            lat = max(min(lat, LAT_MAX), LAT_MIN)
        x, y = project(lon, lat)
        # Round to 0.1px: finer than the display can resolve, and it collapses
        # long runs of near-identical coastline points.
        p = (round(x, 1), round(y, 1))
        if p != last:
            pts.append(p)
            last = p
    if len(pts) < 4:
        return None, 0.0
    area, centre = ring_stats(pts)
    if area < MIN_AREA:
        return None, area, centre
    d = f"M{pts[0][0]} {pts[0][1]}" + "".join(f"L{x} {y}" for x, y in pts[1:]) + "Z"
    return d, area, centre


def main(src):
    data = json.loads(Path(src).read_text())
    out = {}
    points = {}
    labels = {}
    for feat in data["features"]:
        name = feat["properties"].get("name") or ""
        name = RENAME.get(name, name)
        if not name or name in SKIP:
            continue
        geom = feat.get("geometry") or {}
        polys = []
        if geom.get("type") == "Polygon":
            polys = [geom["coordinates"]]
        elif geom.get("type") == "MultiPolygon":
            polys = geom["coordinates"]
        parts = []
        biggest = (0.0, None)                      # (area, centroid)
        for poly in polys:
            for ring in poly:                      # outer ring + holes
                d, area, centre = ring_to_path(ring)
                if d:
                    parts.append(d)
                    # Label position comes from the LARGEST landmass, not an
                    # average: averaging puts France's label in the Atlantic
                    # between the mainland and its overseas territories.
                    if area > biggest[0]:
                        biggest = (area, centre)
        if parts:
            out[name] = "".join(parts)
            if biggest[1]:
                labels[name] = [round(biggest[1][0], 1), round(biggest[1][1], 1),
                                round(biggest[0])]
        elif polys:
            # Every ring was sub-threshold: keep the country as a point.
            pts = [pt for poly in polys for ring in poly for pt in ring]
            if pts:
                xs, ys = zip(*(project(lon, lat) for lon, lat in pts))
                points[name] = [round(sum(xs) / len(xs), 1), round(sum(ys) / len(ys), 1)]

    for name, (lon, lat) in EXTRA_POINTS.items():
        if name not in out and name not in points:
            x, y = project(lon, lat)
            points[name] = [round(x, 1), round(y, 1)]

    OUT.write_text(json.dumps({"paths": out, "points": points, "labels": labels},
                              separators=(",", ":")))
    kb = OUT.stat().st_size / 1024
    print(f"{len(out)} countries + {len(points)} points -> {OUT.relative_to(ROOT)}  ({kb:.0f} kb)")
    print("  points:", ", ".join(sorted(points)) or "none")
    missing = [c for c in ("United States", "United Kingdom", "Germany", "France",
                           "India", "Japan", "Australia", "Brazil", "South Africa",
                           "Singapore")
               if c not in out and c not in points]
    print("  missing key countries:", missing or "none")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/tmp/world.geo.json")
