import {clearSession, getValidAccessToken} from "@/lib/auth";

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
  salary?: string | null;
  application_start_date?: string | null;
  campus_category?: string | null;
  referral_available?: boolean | null;
  company_type?: string | null;
  match?: MatchInsight;
};

export type JobPage = {items: Job[]; page: number; page_size: number; total: number; total_pages: number};

export type Application = {
  id: string;
  job_id?: string | null;
  company: string;
  role?: string | null;
  location?: string | null;
  job_description?: string | null;
  status: string;
  application_date?: string | null;
  deadline?: string | null;
  notes?: string | null;
};

export type ResearchSourceType = "user_provided" | "official" | "external" | "campus" | "community" | "ai_inference";
export type ResearchClaimType = "fact" | "inference" | "grounded_synthesis";
export type ResearchSectionStatus = "available" | "unavailable";
export type ResearchGenerationStatus = "generated" | "partial" | "unavailable" | "failed" | "invalid_output";
export type InterviewReferenceStatus = "interview_reference" | "unavailable";

export type ResearchEvidence = {
  evidence_id: string;
  source_id: string;
  source_type: ResearchSourceType;
  evidence_type: string;
  text: string;
};

export type ResearchFetchedSource = {
  source_id: string;
  title: string;
  url: string;
  source_type: Exclude<ResearchSourceType, "user_provided" | "ai_inference">;
  published_at?: string | null;
  content_type?: string | null;
  extracted_text: string;
  fetch_status: "success" | "unavailable" | "skipped" | "failed";
  error?: string | null;
};

type GroundedResearchItem = {
  claim_type: ResearchClaimType;
  evidence_ids: string[];
};

export type CompanyResearchOutput = {
  application_id: string;
  company_name: string;
  job_title?: string | null;
  company_map: {
    status: ResearchSectionStatus;
    items: Array<GroundedResearchItem & {category: string; text: string}>;
  };
  role_decoder: {
    status: ResearchSectionStatus;
    items: Array<GroundedResearchItem & {category: string; text: string}>;
  };
  recent_signals: {
    status: ResearchSectionStatus;
    items: Array<GroundedResearchItem & {title: string; date?: string | null; why_it_matters_for_interview: string; role_relevance: "high" | "medium" | "low"}>;
  };
  competitive_context: {
    status: ResearchSectionStatus;
    items: Array<GroundedResearchItem & {context_type: "direct_competitor" | "comparable_reference"; competitor: string; comparison_dimension: string; observed_difference: string; interview_relevance: string; what_reference_does?: string | null; what_target_role_emphasizes?: string | null; interview_takeaway?: string | null}>;
  };
  likely_interview_focus: {
    status: ResearchSectionStatus;
    items: Array<GroundedResearchItem & {focus_area: string; why_likely: string; likely_questions: string[]; preparation_focus: string; confidence: "high" | "medium" | "low"}>;
  };
  why_company_why_role_60s: {
    status: ResearchSectionStatus;
    items: Array<GroundedResearchItem & {text: string}>;
  };
  reverse_questions: {
    status: ResearchSectionStatus;
    items: Array<GroundedResearchItem & {question: string; rationale: string}>;
  };
  fetched_sources: ResearchFetchedSource[];
  evidence: ResearchEvidence[];
  interview_references: {
    recent_signals_status: InterviewReferenceStatus;
    recent_signals: Array<{watch_topic: string; why_relevant: string; what_to_learn: string[]}>;
    competitive_context_status: InterviewReferenceStatus;
    competitive_context: Array<{entity_name: string; reference_type: "competitor_reference" | "comparable_product"; shared_dimension: string; why_relevant: string; interview_angle: string}>;
    why_company_role_status: InterviewReferenceStatus;
    why_company_role?: {company_reason: string; role_reason: string; personal_motivation_prompt: string; sample_answer: string} | null;
  };
  company_knowledge: {
    company_positioning?: string | null;
    core_business: string[];
    key_brands_and_products: string[];
    customer_and_market: string[];
    role_relevant_products_and_scenarios: Array<{name: string; type: "product" | "platform" | "brand" | "ecosystem" | "capability" | "business"; relevance_to_role: string; key_scenarios: string[]; things_to_understand: string[]}>;
    comparable_products: Array<{entity_name: string; reference_type: "competitor_reference" | "comparable_product"; why_relevant: string; comparison_dimensions: string[]}>;
  };
  company_knowledge_source_ids: Record<string, string[]>;
  company_knowledge_sources: Array<{source_id: string; title: string; url: string; source_type: "official" | "external" | "campus" | "community"; published_at?: string | null; category?: string | null}>;
  generation_status: ResearchGenerationStatus;
  company_profile_generated_at?: string | null;
  company_profile_refreshed_at?: string | null;
  company_profile_is_stale: boolean;
  company_profile_cache_hit: boolean;
};

export type Resume = {
  id: string;
  name: string;
  file_url: string;
  file_type: "pdf" | "docx";
  extracted_text?: string | null;
  structured_content?: Record<string, unknown>;
  detected_skills: DetectedResumeInformation;
  is_default: boolean;
  created_at?: string;
  updated_at?: string;
};

export type DetectedSkills = {
  technical_skills: string[];
  product_skills: string[];
  soft_skills: string[];
  tools: string[];
  languages: string[];
};

export type DetectedEducation = {
  university: string | null;
  degree: "Bachelor" | "Master" | "PhD" | "Other" | null;
  major: string | null;
  specialisation: string | null;
  graduation_year: number | null;
};

export type DetectedResumeInformation = DetectedSkills & {
  education: DetectedEducation;
};

export type CareerProfile = {
  display_name?: string | null;
  university?: string | null;
  degree?: string | null;
  major?: string | null;
  specialisation?: string | null;
  graduation_year?: number | null;
  target_roles?: string[];
  target_locations?: string[];
  target_industries?: string[];
  preferred_job_types?: string[];
  technical_skills?: string[];
  product_skills?: string[];
  soft_skills?: string[];
  tools?: string[];
  languages?: string[];
  ai_response_language?: string;
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
  reflection?: string | null;
  skills?: string[];
  technologies?: string[];
};

export type ExperienceRecommendation = {
  experience_id: string; title: string; type: string; similarity: number;
  relevance: "high" | "medium" | "lower"; reason: string;
  skills: string[]; technologies: string[]; selected: false;
};

export type MatchInsight = {
  status: "ready" | "scored" | "semantic_only" | "limited_data" | "no_resume";
  overall_score?: number | null;
  semantic_score?: number | null;
  matched_skills: string[];
  missing_skills: string[];
  signals: string[];
  missing_jd: boolean;
  explanation: string;
  components: Record<string, number | null>;
  cached?: boolean;
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
  const response = await authenticatedFetch(`${API_BASE_URL}${path}`, {cache: "no-store"});
  if (!response.ok) throw new Error(await responseError(response));
  return response.json();
}

export async function apiSend<T>(path: string, method: string, body?: unknown): Promise<T> {
  const response = await authenticatedFetch(`${API_BASE_URL}${path}`, {
    method,
    headers: {"Content-Type": "application/json"},
    body: body === undefined ? undefined : JSON.stringify(body)
  });
  if (!response.ok) throw new Error(await responseError(response));
  if (response.status === 204) {
    return undefined as T;
  }
  return response.json();
}

export async function apiUpload<T>(path: string, body: FormData): Promise<T> {
  const response = await authenticatedFetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    body,
  });
  if (!response.ok) throw new Error(await responseError(response));
  return response.json();
}

async function authenticatedFetch(input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> {
  const send = async (token: string | null) => {
    const headers = new Headers(init.headers);
    if (token) headers.set("Authorization", `Bearer ${token}`);
    return fetch(input, {...init, headers});
  };

  const response = await send(await getValidAccessToken());
  if (response.status !== 401) return response;

  const refreshedToken = await getValidAccessToken(true);
  if (!refreshedToken) return response;
  const retried = await send(refreshedToken);
  if (retried.status === 401) clearSession();
  return retried;
}

async function responseError(response: Response): Promise<string> {
  const payload = await response.json().catch(() => null);
  const detail = payload?.detail;
  if (typeof detail === "string") return detail;
  if (typeof detail?.error?.message === "string") return detail.error.message;
  if (Array.isArray(detail) && typeof detail[0]?.msg === "string") return detail[0].msg;
  return response.status === 401 ? "Your session has expired. Please log in again." : `Request failed (${response.status}). Please try again.`;
}
