export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export type Job = {
  id: string;
  company: string;
  role?: string | null;
  location?: string | null;
  industry?: string | null;
  job_type?: string | null;
  deadline?: string | null;
  graduation_cohort?: string | null;
  job_url?: string | null;
  description?: string | null;
  match?: MatchInsight;
};

export type Application = {
  id: string;
  company: string;
  role?: string | null;
  location?: string | null;
  status: string;
  application_date?: string | null;
  deadline?: string | null;
  notes?: string | null;
};

export type Resume = {
  id: string;
  name: string;
  file_url: string;
  extracted_text?: string | null;
  structured_content?: Record<string, unknown>;
  is_default: boolean;
  created_at?: string;
};

export type Experience = {
  id: string;
  title: string;
  type: string;
  description?: string | null;
  situation?: string | null;
  task?: string | null;
  action?: string | null;
  result?: string | null;
  skills?: string[];
  technologies?: string[];
};

export type MatchInsight = {
  level: "scored" | "limited";
  label: string;
  score?: number | null;
  confidence: string;
  matched_skills: string[];
  missing_skills: string[];
  location_match: string[];
  job_type_match: string[];
  education_match: string[];
  reason: string;
  components?: Record<string, number>;
};

export type DashboardOverview = {
  applications_count: number;
  interviews_count: number;
  offers_count: number;
  rejections_count: number;
  upcoming_deadlines: number;
  applications_by_status: Record<string, number>;
};

export async function apiGet<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {cache: "no-store"});
  if (!response.ok) {
    throw new Error(`API request failed: ${response.status}`);
  }
  return response.json();
}

export async function apiSend<T>(path: string, method: string, body?: unknown): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers: {"Content-Type": "application/json"},
    body: body === undefined ? undefined : JSON.stringify(body)
  });
  if (!response.ok) {
    throw new Error(`API request failed: ${response.status}`);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return response.json();
}
