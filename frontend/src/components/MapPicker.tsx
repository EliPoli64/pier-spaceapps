import { useEffect } from "react";
import type { LatLngExpression } from "leaflet";
import { Crosshair } from "lucide-react";
import {
  CircleMarker,
  MapContainer,
  Popup,
  TileLayer,
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
  compact?: boolean;
  fillHeight?: boolean;
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
      className="absolute right-3 top-3 z-[400] inline-flex items-center gap-1.5 rounded-full border border-slate-300 bg-white/95 px-3 py-1.5 text-xs font-semibold text-slate-700 shadow-sm backdrop-blur transition hover:bg-white hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700"
    >
      <Crosshair className="h-3.5 w-3.5 text-emerald-700" aria-hidden="true" />
      <span className="hidden sm:inline">{label}</span>
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
  compact = false,
  fillHeight = false,
}: MapPickerProps) {
  const position: LatLngExpression = [lat, lon];
  const color = eventDot(eventType);

  const heightClass = fillHeight
    ? "h-[380px] lg:h-full lg:min-h-[460px]"
    : compact
      ? "h-[240px]"
      : "h-[400px]";

  return (
    <div
      className={`relative w-full overflow-hidden rounded-2xl border border-slate-200 bg-slate-100 transition-[height] duration-200 ${heightClass}`}
    >
      <MapContainer
        center={position}
        zoom={7}
        scrollWheelZoom
        className="h-full w-full"
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
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
        className="pointer-events-none absolute bottom-2.5 left-2.5 z-[400] flex flex-wrap items-center gap-2 rounded-full border border-slate-200/90 bg-white/92 px-3 py-1 text-[0.68rem] font-medium text-slate-700 shadow-sm backdrop-blur"
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
