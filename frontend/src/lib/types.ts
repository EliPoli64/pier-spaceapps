export type EventType = "flood" | "drought" | "none";

export interface Demo {
  name: string;
  label?: string | null;
  lat: number;
  lon: number;
  event_type: EventType;
  current_date: string;
  season_start?: string | null;
  season_end?: string | null;
  description?: string | null;
  demo_name: string;
}

export interface Crop {
  crop: string;
  role?: string;
  event_match: boolean;
  gdd_requirement: number;
  gdd_remaining: number;
  margin_pct: number;
  plant_by_date: string;
  days_until_deadline: number;
  rescue_confidence: number;
  composite_score: number;
}

export interface Exclusion {
  crop: string;
  motivo: string;
  explicacion: string;
}

export interface Rotation {
  rotation_sequence: string[];
  soil_health_score: number;
  n_fixation_total_kg_ha: number;
  residue_cover_avg_pct: number;
  rationale: string;
  prioridad: string;
}

export interface Savings {
  crop: string;
  price_per_unit: number;
  currency: string;
  expected_yield_tons_per_ha: number;
  estimated_revenue_usd_per_ha: number;
  estimated_savings_usd_per_ha: number;
  note: string;
  usd_por_ha: number;
  rendimiento_t_ha: number;
  es_estimado: boolean;
}

export interface Alert {
  nivel: "info" | "warning" | "critical";
  codigo: string;
  mensaje: string;
}

export interface PlanResponse {
  request_id: string;
  run_id?: string;
  plan_text: string;
  event_type: EventType;
  event_severity?: string | null;
  event_confidence: number;
  rescue_confidence?: number | null;
  gdd_accumulated?: number | null;
  gdd_remaining: number;
  frost_date?: string | null;
  fallback: boolean;
  no_action_needed: boolean;
  crops: Crop[];
  exclusiones: Exclusion[];
  rotacion?: Rotation | null;
  ahorro?: Savings | null;
  fuente_datos: string;
  ultima_actualizacion?: string | null;
  demo_mode: boolean;
  demo_name?: string | null;
  auto_detected: boolean;
  pesos_agricultor?: Record<string, number> | null;
  rendimiento_t_ha?: number;
  alertas: Alert[];
  event_details?: Record<string, unknown> | null;
  vista?: string;
  contrato?: string;
}

export interface PlanRequest {
  lat: number;
  lon: number;
  current_date: string;
  demo_mode: boolean;
  demo_name?: string | null;
  pesos_agricultor: Weights;
  rendimiento_t_ha: number;
}

export interface ResultMeta {
  lat: number;
  lon: number;
  date: string;
  demoMode: boolean;
  scenario: string;
  weights: Weights;
  yieldT: number;
}

export interface Scenario {
  id: string;
  labelKey: string;
  demo_name: string | null;
  lat: number;
  lon: number;
  current_date: string;
  description?: string;
}

export interface Weights {
  soil_protection: number;
  salvage_revenue: number;
  water_conservation: number;
}
