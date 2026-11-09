export interface Asset {
  id: string; href: string; datetime: string; run_id?: string | null;
  projection: string; proj4?: string; bounds: number[]; shape: number[];
  transform: number[]; nodata: number | 'NaN' | null; scale: number; offset: number;
}
export interface Variable {
  id: string; label: string; title: string; unit: string;
  range: [number, number]; palette: 'snow' | 'temperature' | 'difference' | 'temperature-difference'; assets: Asset[];
}
export interface Catalogue {
  version: number; title: string; generated_at: string; latest_time: string;
  window_days: number; sample_data: boolean; bounds: number[]; variables: Variable[];
  retention?: { daily_days: number; weekly_days: number | null; hydrological_year_start?: string; weekly_variables: string[]; week_starts: string };
  storage_bytes?: number;
}
export interface PointValue { time: string; value: number | null; error?: string }
