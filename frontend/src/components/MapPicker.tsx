import { useEffect, useRef } from "react";
import type { LatLngExpression } from "leaflet";
import { Crosshair } from "lucide-react";
import {
  CircleMarker,
  MapContainer,
  Popup,
  TileLayer,
  ZoomControl,
  useMap,
  useMapEvents,
} from "react-leaflet";
import type { EventType } from "../lib/types";
import type { Lang } from "../lib/i18n";
import {
  eventDot,
  eventLabel,
  formatPercent,
  prefersReducedMotion,
} from "../lib/format";
import { t } from "../lib/i18n";

interface MapPickerProps {
  lat: number;
  lon: number;
  eventType: EventType;
  confidence: number;
  lang: Lang;
  onPick: (lat: number, lon: number) => void;
}

function ClickHandler({
  onPick,
}: {
  onPick: (lat: number, lon: number) => void;
}) {
  useMapEvents({
    click(event) {
      onPick(event.latlng.lat, event.latlng.lng);
    },
  });
  return null;
}

function Recenter({ lat, lon }: { lat: number; lon: number }) {
  const map = useMap();

  useEffect(() => {
    map.setView([lat, lon], map.getZoom(), {
      animate: !prefersReducedMotion(),
    });
  }, [lat, lon, map]);

  return null;
}

function AutoResize({
  containerRef,
}: {
  containerRef: React.RefObject<HTMLDivElement | null>;
}) {
  const map = useMap();

  useEffect(() => {
    const el = containerRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => {
      map.invalidateSize({ animate: false });
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, [containerRef, map]);

  return null;
}

function RecenterControl({
  lat,
  lon,
  label,
}: {
  lat: number;
  lon: number;
  label: string;
}) {
  const map = useMap();

  return (
    <button
      type="button"
      onClick={(event) => {
        event.stopPropagation();
        map.setView([lat, lon], Math.max(map.getZoom(), 7), {
          animate: !prefersReducedMotion(),
        });
      }}
      aria-label={label}
      title={label}
      className="absolute bottom-[98px] right-[10px] z-[400] inline-flex h-[30px] w-[30px] items-center justify-center rounded bg-white text-slate-700 shadow-md ring-1 ring-slate-900/15 transition hover:bg-slate-50 hover:text-slate-950 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700"
    >
      <Crosshair className="h-4 w-4 text-emerald-700" aria-hidden="true" />
    </button>
  );
}

export function MapPicker({
  lat,
  lon,
  eventType,
  confidence,
  lang,
  onPick,
}: MapPickerProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const position: LatLngExpression = [lat, lon];
  const color = eventDot(eventType);

  return (
    <div ref={containerRef} className="relative h-full w-full bg-slate-200">
      <MapContainer
        center={position}
        zoom={7}
        zoomControl={false}
        scrollWheelZoom
        className="h-full w-full"
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <ZoomControl position="bottomright" />
        <AutoResize containerRef={containerRef} />
        <Recenter lat={lat} lon={lon} />
        <ClickHandler onPick={onPick} />
        <RecenterControl lat={lat} lon={lon} label={t(lang, "mapRecenter")} />
        <CircleMarker
          center={position}
          radius={11}
          pathOptions={{
            color,
            fillColor: color,
            fillOpacity: 0.28,
            weight: 3,
          }}
        >
          <Popup>
            <div className="space-y-1 text-sm text-slate-700">
              <p className="font-semibold text-slate-900">
                {t(lang, "selectedLocation")}
              </p>
              <p className="font-mono text-xs tabular-nums">
                {lat.toFixed(4)}, {lon.toFixed(4)}
              </p>
              <p>
                {t(lang, "event")}: {eventLabel(eventType, lang)}
              </p>
              <p>
                {t(lang, "detectionConfidence")}: {formatPercent(confidence)}
              </p>
            </div>
          </Popup>
        </CircleMarker>
      </MapContainer>

      <div
        aria-hidden="true"
        className="pointer-events-none absolute bottom-3 left-3 z-[400] flex flex-wrap items-center gap-2.5 rounded-full bg-white/95 px-3 py-1 text-[0.68rem] font-medium text-slate-700 shadow-md ring-1 ring-slate-900/10 backdrop-blur"
      >
        <span className="inline-flex items-center gap-1">
          <span className="h-2 w-2 rounded-full bg-[#0284c7]" />
          {t(lang, "eventFlood")}
        </span>
        <span className="inline-flex items-center gap-1">
          <span className="h-2 w-2 rounded-full bg-[#b45309]" />
          {t(lang, "eventDrought")}
        </span>
        <span className="inline-flex items-center gap-1">
          <span className="h-2 w-2 rounded-full bg-[#15803d]" />
          {t(lang, "noEvent")}
        </span>
      </div>
    </div>
  );
}
