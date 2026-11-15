import { useEffect } from "react";
import type { LatLngExpression } from "leaflet";
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
import { eventDot, eventLabel, formatPercent } from "../lib/format";
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
    map.setView([lat, lon], map.getZoom(), { animate: true });
  }, [lat, lon, map]);

  return null;
}

export function MapPicker({
  lat,
  lon,
  eventType,
  confidence,
  lang,
  onPick,
}: MapPickerProps) {
  const position: LatLngExpression = [lat, lon];
  const color = eventDot(eventType);

  return (
    <div className="relative h-[420px] w-full overflow-hidden rounded-2xl border border-slate-200 bg-slate-100">
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
        <CircleMarker
          center={position}
          radius={11}
          pathOptions={{
            color,
            fillColor: color,
            fillOpacity: 0.25,
            weight: 3,
          }}
        >
          <Popup>
            <div className="space-y-1 text-sm text-slate-700">
              <p className="font-semibold text-slate-900">
                {t(lang, "selectedLocation")}
              </p>
              <p className="font-mono text-xs">
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
    </div>
  );
}
