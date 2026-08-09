"""Optionale Kapitel-/Karten-Vorschau vor dem Export."""

from __future__ import annotations

import html
import json
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from .models import BookPlan, Photo

# Erdige, gut unterscheidbare Farben (kein Neon-Lila)
CHAPTER_COLORS = [
    "#2F5D50",
    "#8B5A2B",
    "#3D5A80",
    "#A63D40",
    "#6B705C",
    "#BC6C25",
    "#4A6670",
    "#7F5539",
    "#5C677D",
    "#9C6644",
]


@dataclass
class ChapterPreview:
    key: str
    title: str
    kind: str  # region | transit
    color: str
    start: str
    end: str
    selected_count: int
    total_count: int
    mean_lat: Optional[float]
    mean_lon: Optional[float]
    points: list[tuple[float, float]]


def _fmt_date(dt) -> str:
    return dt.strftime("%Y-%m-%d") if dt else "?"


def _mean_gps(photos: list[Photo], indices: list[int]) -> tuple[Optional[float], Optional[float], list[tuple[float, float]]]:
    pts: list[tuple[float, float]] = []
    for i in indices:
        p = photos[i]
        if p.has_gps:
            pts.append((float(p.gps_lat), float(p.gps_lon)))  # type: ignore[arg-type]
    if not pts:
        return None, None, []
    lat = sum(a for a, _ in pts) / len(pts)
    lon = sum(b for _, b in pts) / len(pts)
    return lat, lon, pts


def build_chapter_previews(
    photos: list[Photo],
    plan: BookPlan,
    order: list[tuple[int, str, str]] | None = None,
) -> list[ChapterPreview]:
    """Kapitel-Übersicht mit GPS-Schwerpunkten der Auswahl (Fallback: alle Fotos)."""
    selected_by_region: dict[str, list[int]] = {}
    if order:
        for idx, _folder, ctype in order:
            region = photos[idx].region or ""
            if ctype == "Transit":
                key = region
            else:
                key = region
            selected_by_region.setdefault(key, []).append(idx)
    else:
        for i, p in enumerate(photos):
            if p.is_selected:
                selected_by_region.setdefault(p.region or "", []).append(i)

    chapters: list[ChapterPreview] = []
    transit_by_after = {t.chapter_index: t for t in plan.transits}
    color_i = 0

    for r_idx, region in enumerate(plan.regions):
        color = CHAPTER_COLORS[color_i % len(CHAPTER_COLORS)]
        color_i += 1
        sel = selected_by_region.get(region.name, [])
        # GPS bevorzugt aus Auswahl, sonst alle Regionsfotos
        gps_indices = sel or region.photo_indices
        lat, lon, pts = _mean_gps(photos, gps_indices)
        # Nur ausgewählte Punkte für die Karte markieren
        _, _, sel_pts = _mean_gps(photos, sel) if sel else (None, None, [])
        chapters.append(
            ChapterPreview(
                key=region.name,
                title=f"Kapitel {r_idx + 1}: {region.name}",
                kind="region",
                color=color,
                start=_fmt_date(region.start_time),
                end=_fmt_date(region.end_time),
                selected_count=len(sel),
                total_count=len(region.photo_indices),
                mean_lat=lat,
                mean_lon=lon,
                points=sel_pts or pts[:40],
            )
        )
        if r_idx in transit_by_after:
            t = transit_by_after[r_idx]
            t_key = f"Transit:{t.from_region}->{t.to_region}"
            t_sel = selected_by_region.get(t_key, [])
            t_gps = t_sel or t.photo_indices
            t_lat, t_lon, t_pts_all = _mean_gps(photos, t_gps)
            _, _, t_pts = _mean_gps(photos, t_sel) if t_sel else (None, None, [])
            t_color = CHAPTER_COLORS[color_i % len(CHAPTER_COLORS)]
            color_i += 1
            chapters.append(
                ChapterPreview(
                    key=t_key,
                    title=f"Transit: {t.name}",
                    kind="transit",
                    color=t_color,
                    start="",
                    end="",
                    selected_count=len(t_sel),
                    total_count=len(t.photo_indices),
                    mean_lat=t_lat,
                    mean_lon=t_lon,
                    points=t_pts or t_pts_all[:20],
                )
            )
    return chapters


def write_chapter_map(
    photos: list[Photo],
    plan: BookPlan,
    output_dir: Path,
    order: list[tuple[int, str, str]] | None = None,
) -> Path:
    """Schreibt eine lokale HTML-Karte (Leaflet/OSM) nach kapitel_karte.html."""
    chapters = build_chapter_previews(photos, plan, order)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "kapitel_karte.html"

    features = []
    for ch in chapters:
        for lat, lon in ch.points:
            features.append(
                {
                    "type": "Feature",
                    "properties": {
                        "chapter": ch.title,
                        "kind": ch.kind,
                        "color": ch.color,
                    },
                    "geometry": {"type": "Point", "coordinates": [lon, lat]},
                }
            )
        if ch.mean_lat is not None and ch.mean_lon is not None:
            features.append(
                {
                    "type": "Feature",
                    "properties": {
                        "chapter": ch.title,
                        "kind": "center",
                        "color": ch.color,
                        "label": ch.title,
                        "count": ch.selected_count,
                    },
                    "geometry": {
                        "type": "Point",
                        "coordinates": [ch.mean_lon, ch.mean_lat],
                    },
                }
            )

    # Polyline durch Regionszentren (Reihenfolge)
    line_coords = [
        [ch.mean_lon, ch.mean_lat]
        for ch in chapters
        if ch.kind == "region" and ch.mean_lat is not None and ch.mean_lon is not None
    ]

    legend_items = "".join(
        f'<li><span style="background:{html.escape(ch.color)}"></span>'
        f"{html.escape(ch.title)} "
        f"({ch.selected_count} ausgewählt / {ch.total_count} Fotos)"
        f"{f' · {html.escape(ch.start)} – {html.escape(ch.end)}' if ch.start else ''}"
        f"</li>"
        for ch in chapters
    )

    geojson = json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False)
    line_json = json.dumps(line_coords)

    center_lat, center_lon, zoom = 48.0, 10.0, 5
    with_gps = [ch for ch in chapters if ch.mean_lat is not None]
    if with_gps:
        center_lat = sum(ch.mean_lat for ch in with_gps) / len(with_gps)  # type: ignore[misc]
        center_lon = sum(ch.mean_lon for ch in with_gps) / len(with_gps)  # type: ignore[misc]
        zoom = 6 if len(with_gps) > 1 else 10

    content = f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Fotobuch – Weltkarte</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<style>
  body {{ margin: 0; font-family: "Segoe UI", sans-serif; background: #12141C; color: #E8EAF2; }}
  header {{ padding: 16px 20px 8px; display: flex; gap: 12px; align-items: baseline; flex-wrap: wrap; }}
  h1 {{ margin: 0; font-size: 1.35rem; font-weight: 600; }}
  p {{ margin: 6px 0 0; color: #9AA3B5; font-size: 0.9rem; flex: 1; }}
  .btn {{ background: #7B6CFF; color: #fff; border: 0; border-radius: 8px; padding: 8px 14px;
          font: 600 0.88rem "Segoe UI", sans-serif; cursor: pointer; }}
  .btn.secondary {{ background: #262C40; color: #E8EAF2; }}
  #wrap {{ display: flex; gap: 12px; padding: 0 16px 16px; height: calc(100vh - 88px); box-sizing: border-box; }}
  #map {{ flex: 1; min-height: 360px; border-radius: 10px; border: 1px solid #2C3348; }}
  aside {{ width: 300px; overflow: auto; background: #1C2030; border: 1px solid #2C3348; border-radius: 10px;
           padding: 14px 16px; font-size: 0.88rem; }}
  aside h2 {{ font-size: 0.8rem; letter-spacing: 0.06em; text-transform: uppercase; color: #9AA3B5; margin: 0 0 12px; }}
  aside ul {{ list-style: none; padding: 0; margin: 0; }}
  aside li {{ margin: 0 0 12px; line-height: 1.4; }}
  aside li span {{ display: inline-block; width: 12px; height: 12px; border-radius: 3px; margin-right: 8px; vertical-align: middle; }}
  .empty {{ padding: 24px; color: #9AA3B5; }}
</style>
</head>
<body>
<header>
  <div>
    <h1>Weltkarte · Kapitel</h1>
    <p>OpenStreetMap – Reise-Route und Kapitel auf der Weltkarte.</p>
  </div>
  <button class="btn secondary" type="button" onclick="showWorld()">Weltkarte</button>
  <button class="btn" type="button" onclick="showTrip()">Reise</button>
</header>
<div id="wrap">
  <div id="map"></div>
  <aside>
    <h2>Kapitel</h2>
    <ul>{legend_items or '<li class="empty">Keine Kapitel</li>'}</ul>
  </aside>
</div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
const geo = {geojson};
const line = {line_json};
const map = L.map('map', {{ worldCopyJump: true }}).setView([{center_lat}, {center_lon}], {zoom});
L.tileLayer('https://{{s}}.basemaps.cartocdn.com/dark_all/{{z}}/{{x}}/{{y}}{{r}}.png', {{
  maxZoom: 18,
  attribution: '&copy; OpenStreetMap, &copy; CARTO'
}}).addTo(map);
if (line.length >= 2) {{
  L.polyline(line.map(c => [c[1], c[0]]), {{color: '#7B6CFF', weight: 3, opacity: 0.85}}).addTo(map);
}}
const bounds = [];
L.geoJSON(geo, {{
  pointToLayer: function(feature, latlng) {{
    const p = feature.properties || {{}};
    const isCenter = p.kind === 'center';
    const marker = L.circleMarker(latlng, {{
      radius: isCenter ? 9 : 5,
      color: p.color || '#7B6CFF',
      fillColor: p.color || '#7B6CFF',
      fillOpacity: isCenter ? 0.95 : 0.55,
      weight: isCenter ? 2 : 1
    }});
    if (isCenter && p.label) {{
      marker.bindPopup('<strong>' + p.label + '</strong><br>' + (p.count || 0) + ' ausgewählt');
      marker.bindTooltip(p.label, {{permanent: false}});
    }}
    bounds.push(latlng);
    return marker;
  }}
}}).addTo(map);
function showTrip() {{
  if (bounds.length) {{ map.fitBounds(bounds, {{padding: [40, 40], maxZoom: 10}}); }}
  else {{ map.setView([{center_lat}, {center_lon}], {zoom}); }}
}}
function showWorld() {{ map.setView([20, 10], 2); }}
showTrip();
</script>
</body>
</html>
"""
    path.write_text(content, encoding="utf-8")
    return path


def open_chapter_map_in_browser(path: Path) -> None:
    webbrowser.open(path.resolve().as_uri())


def open_map_preview(
    master,
    photos: list[Photo],
    plan: BookPlan,
    output_dir: Path,
    order: list[tuple[int, str, str]] | None = None,
    *,
    await_export: bool = False,
    on_confirm: Optional[Callable[[], None]] = None,
    on_cancel: Optional[Callable[[], None]] = None,
) -> None:
    """Öffnet das Vorschau-Fenster (Kapitel + einfache Karte)."""
    MapPreviewWindow(
        master,
        photos,
        plan,
        output_dir,
        order=order,
        await_export=await_export,
        on_confirm=on_confirm,
        on_cancel=on_cancel,
    )


# tkinter erst bei Bedarf importieren (CLI ohne Display)
import tkinter as tk
from tkinter import messagebox

from .i18n import t
from .settings import theme_colors
from .ui_widgets import PaddedButton
from .window_layout import place_window
from .world_basemap import draw_world_basemap, lonlat_to_xy, trip_bounds, world_view_bounds


def _short_date(iso: str) -> str:
    """2025-11-17 → 17.11. (kompakter, weniger Zeilenumbruch)."""
    parts = (iso or "").split("-")
    if len(parts) == 3:
        return f"{parts[2]}.{parts[1]}."
    return iso


def _chapter_labels(ch: ChapterPreview) -> tuple[str, str]:
    """Titel + Meta getrennt – keine ellenlangen Einzeiler in der Liste."""
    if ch.kind == "transit":
        title = ch.title.replace("Transit: ", "", 1)
        title = f"Transit · {title}"
    else:
        title = ch.title
    if len(title) > 42:
        title = title[:40] + "…"
    meta = f"{ch.selected_count}/{ch.total_count} {t('map_selected')}"
    if ch.start:
        if ch.end and ch.end != ch.start:
            meta += f"  ·  {_short_date(ch.start)}–{_short_date(ch.end)}"
        else:
            meta += f"  ·  {_short_date(ch.start)}"
    return title, meta


class MapPreviewWindow(tk.Toplevel):
    def __init__(
        self,
        master,
        photos: list[Photo],
        plan: BookPlan,
        output_dir: Path,
        order: list[tuple[int, str, str]] | None = None,
        *,
        await_export: bool = False,
        on_confirm: Optional[Callable[[], None]] = None,
        on_cancel: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__(master)
        try:
            self.colors = theme_colors()
        except Exception:
            self.colors = {
                "bg": "#12141C",
                "surface": "#1C2030",
                "ink": "#E8EAF2",
                "muted": "#9AA3B5",
                "line": "#2C3348",
                "accent": "#7B6CFF",
                "accent_hover": "#6958F0",
                "accent_soft": "#2A2750",
                "hero_fg": "#FFFFFF",
                "map_canvas": "#161A28",
                "chip_bg": "#262C40",
            }
        self.title(t("map_title"))
        self.configure(bg=self.colors["bg"])
        place_window(
            self,
            frac_w=0.78,
            frac_h=0.82,
            min_width=960,
            min_height=620,
            width=1100,
            height=720,
        )
        self.photos = photos
        self.plan = plan
        self.output_dir = Path(output_dir)
        self.order = order
        self.await_export = await_export
        self.on_confirm = on_confirm
        self.on_cancel = on_cancel
        self.chapters = build_chapter_previews(photos, plan, order)
        self.map_path = write_chapter_map(photos, plan, self.output_dir, order)
        self._decided = False
        self._selected = 0
        self._world_view = False  # False = Reise-Ausschnitt mit Landkarte
        self._row_frames: list[tk.Frame] = []
        self._build()
        place_window(
            self,
            frac_w=0.78,
            frac_h=0.82,
            min_width=960,
            min_height=620,
            width=1100,
            height=720,
        )
        self.transient(master)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _build(self) -> None:
        c = self.colors
        pad = tk.Frame(self, bg=c["bg"], padx=20, pady=18)
        pad.pack(fill=tk.BOTH, expand=True)

        tk.Label(
            pad,
            text=t("map_title"),
            bg=c["bg"],
            fg=c["ink"],
            font=("Segoe UI Semibold", 18),
            anchor=tk.W,
        ).pack(anchor=tk.W)
        tk.Label(
            pad,
            text=t("map_subtitle_export") if self.await_export else t("map_subtitle"),
            bg=c["bg"],
            fg=c["muted"],
            font=("Segoe UI", 10),
            anchor=tk.W,
            wraplength=900,
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(6, 14))

        body = tk.Frame(pad, bg=c["bg"])
        body.pack(fill=tk.BOTH, expand=True)

        # Kapitel-Liste als Zeilen (Titel + Meta) – kein gequetschter Einzeiler
        list_outer = tk.Frame(body, bg=c["line"], padx=1, pady=1)
        list_outer.pack(side=tk.LEFT, fill=tk.Y)
        list_frame = tk.Frame(list_outer, bg=c["surface"], padx=12, pady=12)
        list_frame.pack(fill=tk.BOTH, expand=True)
        tk.Label(
            list_frame,
            text=t("map_chapters"),
            bg=c["surface"],
            fg=c["muted"],
            font=("Segoe UI Semibold", 9),
            anchor=tk.W,
        ).pack(anchor=tk.W, pady=(0, 8))

        list_host = tk.Frame(list_frame, bg=c["surface"])
        list_host.pack(fill=tk.BOTH, expand=True)
        canvas = tk.Canvas(
            list_host,
            bg=c["surface"],
            highlightthickness=0,
            width=300,
        )
        scroll = tk.Scrollbar(list_host, orient=tk.VERTICAL, command=canvas.yview)
        rows = tk.Frame(canvas, bg=c["surface"])
        rows.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        win_id = canvas.create_window((0, 0), window=rows, anchor=tk.NW)
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.bind(
            "<Configure>",
            lambda e: canvas.itemconfigure(win_id, width=e.width),
        )
        self._chapter_rows = rows

        if not self.chapters:
            tk.Label(
                rows,
                text=t("map_no_chapters"),
                bg=c["surface"],
                fg=c["muted"],
                font=("Segoe UI", 10),
                padx=10,
                pady=12,
            ).pack(anchor=tk.W)
        else:
            for i, ch in enumerate(self.chapters):
                self._add_chapter_row(rows, i, ch)

        map_outer = tk.Frame(body, bg=c["line"], padx=1, pady=1)
        map_outer.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(14, 0))
        map_frame = tk.Frame(map_outer, bg=c["surface"], padx=8, pady=8)
        map_frame.pack(fill=tk.BOTH, expand=True)
        self.canvas = tk.Canvas(
            map_frame,
            bg=c.get("map_canvas", "#161A28"),
            highlightthickness=0,
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.bind("<Configure>", lambda _e: self._draw_map())

        actions = tk.Frame(pad, bg=c["bg"])
        actions.pack(fill=tk.X, pady=(16, 0))
        PaddedButton(
            actions,
            t("map_browser"),
            c,
            command=self._open_browser,
            padx=16,
            pady=11,
        ).pack(side=tk.LEFT)
        self._view_btn = PaddedButton(
            actions,
            t("map_world"),
            c,
            command=self._toggle_world_view,
            padx=16,
            pady=11,
        )
        self._view_btn.pack(side=tk.LEFT, padx=(10, 0))

        if self.await_export:
            PaddedButton(
                actions,
                t("map_export"),
                c,
                command=self._confirm,
                primary=True,
                padx=18,
                pady=11,
            ).pack(side=tk.RIGHT)
            PaddedButton(
                actions,
                t("cancel"),
                c,
                command=self._cancel,
                padx=16,
                pady=11,
            ).pack(side=tk.RIGHT, padx=(0, 10))
        else:
            PaddedButton(
                actions,
                t("close"),
                c,
                command=self._close,
                primary=True,
                padx=18,
                pady=11,
            ).pack(side=tk.RIGHT)

        if self.chapters:
            self._select_chapter(0)

    def _add_chapter_row(self, parent: tk.Misc, index: int, ch: ChapterPreview) -> None:
        c = self.colors
        title, meta = _chapter_labels(ch)
        row = tk.Frame(parent, bg=c["surface"], padx=10, pady=10, cursor="hand2")
        row.pack(fill=tk.X, pady=(0, 6))
        swatch = tk.Frame(row, bg=ch.color, width=4)
        swatch.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        text = tk.Frame(row, bg=c["surface"])
        text.pack(side=tk.LEFT, fill=tk.X, expand=True)
        title_lbl = tk.Label(
            text,
            text=title,
            bg=c["surface"],
            fg=c["ink"],
            font=("Segoe UI Semibold", 10),
            anchor=tk.W,
            justify=tk.LEFT,
            wraplength=240,
        )
        title_lbl.pack(anchor=tk.W)
        meta_lbl = tk.Label(
            text,
            text=meta,
            bg=c["surface"],
            fg=c["muted"],
            font=("Segoe UI", 9),
            anchor=tk.W,
            pady=2,
        )
        meta_lbl.pack(anchor=tk.W)
        for w in (row, text, title_lbl, meta_lbl, swatch):
            w.bind("<Button-1>", lambda _e, i=index: self._select_chapter(i))
        row._title_lbl = title_lbl  # type: ignore[attr-defined]
        row._meta_lbl = meta_lbl  # type: ignore[attr-defined]
        row._text = text  # type: ignore[attr-defined]
        self._row_frames.append(row)

    def _select_chapter(self, index: int) -> None:
        self._selected = index
        c = self.colors
        for i, row in enumerate(self._row_frames):
            active = i == index
            bg = c["accent"] if active else c["surface"]
            fg = c.get("hero_fg", "#FFFFFF") if active else c["ink"]
            muted = c.get("hero_muted", fg) if active else c["muted"]
            row.configure(bg=bg)
            row._text.configure(bg=bg)  # type: ignore[attr-defined]
            row._title_lbl.configure(bg=bg, fg=fg)  # type: ignore[attr-defined]
            row._meta_lbl.configure(bg=bg, fg=muted)  # type: ignore[attr-defined]
        self._draw_map()

    def _toggle_world_view(self) -> None:
        self._world_view = not self._world_view
        try:
            self._view_btn.configure(
                text=t("map_trip") if self._world_view else t("map_world")
            )
        except tk.TclError:
            pass
        self._draw_map()

    def _draw_map(self) -> None:
        ui = self.colors
        c = self.canvas
        c.delete("all")
        w = max(c.winfo_width(), 40)
        h = max(c.winfo_height(), 40)
        pts: list[tuple[float, float, str, str, int]] = []
        for i, ch in enumerate(self.chapters):
            for lat, lon in ch.points:
                pts.append((lat, lon, ch.color, ch.title, i))
            if ch.mean_lat is not None and ch.mean_lon is not None:
                pts.append((ch.mean_lat, ch.mean_lon, ch.color, ch.title, i))

        if self._world_view or not pts:
            west, east, south, north = world_view_bounds()
        else:
            west, east, south, north = trip_bounds([(p[0], p[1]) for p in pts])

        draw_world_basemap(
            c,
            width=w,
            height=h,
            land_fill=ui.get("chip_bg", "#262C40"),
            land_outline=ui.get("line", "#2C3348"),
            water_fill=ui.get("map_canvas", "#161A28"),
            grid_color=ui.get("line", "#2C3348"),
            west=west,
            east=east,
            south=south,
            north=north,
        )

        if not pts:
            c.create_text(
                w / 2,
                h / 2,
                text=t("map_no_gps"),
                fill=ui["muted"],
                font=("Segoe UI", 11),
            )
            return

        def xy(lat: float, lon: float) -> tuple[float, float]:
            return lonlat_to_xy(
                lon,
                lat,
                width=w,
                height=h,
                west=west,
                east=east,
                south=south,
                north=north,
                pad=16.0,
            )

        region_centers = [
            (ch.mean_lat, ch.mean_lon)
            for ch in self.chapters
            if ch.kind == "region" and ch.mean_lat is not None and ch.mean_lon is not None
        ]
        if len(region_centers) >= 2:
            flat = []
            for lat, lon in region_centers:
                x, y = xy(lat, lon)  # type: ignore[arg-type]
                flat.extend([x, y])
            c.create_line(*flat, fill=ui["accent"], width=3, smooth=True)

        for lat, lon, color, _title, idx in pts:
            x, y = xy(lat, lon)
            r = 6 if idx == self._selected else 4
            c.create_oval(x - r, y - r, x + r, y + r, fill=color, outline="")

        for i, ch in enumerate(self.chapters):
            if ch.mean_lat is None or ch.mean_lon is None:
                continue
            x, y = xy(ch.mean_lat, ch.mean_lon)
            r = 12 if i == self._selected else 8
            width = 3 if i == self._selected else 2
            c.create_oval(
                x - r, y - r, x + r, y + r, outline=ch.color, width=width
            )
            if i == self._selected or self._world_view:
                label = ch.title.split(": ", 1)[-1][:22]
                c.create_text(
                    x,
                    y - (20 if i == self._selected else 14),
                    text=label,
                    fill=ui["ink"] if i == self._selected else ui["muted"],
                    font=("Segoe UI Semibold", 9) if i == self._selected else ("Segoe UI", 8),
                )

    def _open_browser(self) -> None:
        try:
            open_chapter_map_in_browser(self.map_path)
        except Exception as exc:
            messagebox.showerror(
                t("map"),
                f"Browser konnte nicht geöffnet werden:\n{exc}",
                parent=self,
            )

    def _confirm(self) -> None:
        self._decided = True
        cb = self.on_confirm
        self.grab_release()
        self.destroy()
        if cb:
            cb()

    def _cancel(self) -> None:
        self._decided = True
        cb = self.on_cancel
        self.grab_release()
        self.destroy()
        if cb:
            cb()

    def _close(self) -> None:
        if self.await_export and not self._decided:
            self._cancel()
            return
        self.grab_release()
        self.destroy()
