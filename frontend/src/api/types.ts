export type Task = {
  task_id: string;
  product_name: string;
  competitors: string[];
  region: string;
  industry: string;
  status: string;
  rework_count: number;
  created_at: string;
  updated_at: string;
};

export type Evidence = {
  evidence_id: string;
  competitor?: string;
  source_type: string;
  url?: string;
  local_ref?: string;
  snippet: string;
  confidence: number;
  source_domain?: string;
  source_quality?: "official" | "documentation" | "media" | "review" | "unknown" | "low_quality";
  collected_at: string;
};

export type Claim = {
  claim_id: string;
  competitor?: string;
  text: string;
  category: string;
  evidence_ids: string[];
  confidence: number;
};

export type Report = {
  report_id: string;
  task_id: string;
  markdown: string;
  json_report: {
    knowledge?: Record<string, unknown>;
    claims?: Claim[];
    writer_diagnostics?: WriterDiagnostics;
  };
  claims: Claim[];
  qa_result?: QaResult;
};

export type WriterDiagnostics = {
  writer_mode_requested?: string;
  writer_mode_used?: string;
  llm_enabled?: boolean;
  llm_provider?: string;
  llm_model?: string;
  llm_base_url_configured?: boolean;
  has_api_key?: boolean;
  llm_call_attempted?: boolean;
  llm_call_success?: boolean;
  llm_elapsed_time_ms?: number;
  llm_error_type?: string;
  llm_error_message?: string;
  llm_response_preview?: string;
  fallback_used?: boolean;
  llm_fallback_reason?: string;
};

export type LlmStatus = {
  llm_provider: string;
  llm_model: string;
  base_url_configured: boolean;
  api_key_configured: boolean;
  llm_enabled: boolean;
  last_check_status: "not_checked" | "success" | "failed";
  last_error?: string | null;
  suggested_action: string;
};

export type CollectorStatus = {
  search_provider: string;
  api_key_configured: boolean;
  base_url_configured: boolean;
  timeout: number;
  max_results: number;
  enabled: boolean;
};

export type SearchTestResult = {
  success: boolean;
  provider: string;
  query: string;
  result_count: number;
  results_preview: Array<{ title: string; url: string; snippet: string }>;
  error_type?: string | null;
  error_message?: string | null;
};

export type CollectorDiagnostics = {
  collector_mode_requested?: string;
  collector_mode_used?: string;
  web_search_attempted?: boolean;
  web_search_success?: boolean;
  query_count?: number;
  evidence_count?: number;
  fallback_used?: boolean;
  fallback_reason?: string;
  elapsed_time_ms?: number;
};

export type QaResult = {
  task_id: string;
  status: "passed" | "failed" | "manual_review";
  hard_errors: string[];
  soft_suggestions: string[];
  rework_instructions: Array<{
    target_agent: string;
    error_type: string;
    reason: string;
    suggested_action: string;
    claim_id?: string;
    failed_claim?: string;
    failed_schema?: string;
  }>;
  rework_history: Array<{
    round: number;
    from_status: string;
    error_type: string;
    route_to?: string;
    action: string;
    result_status?: string;
  }>;
  route_to?: string;
  rework_count: number;
};

export type TraceRecord = {
  trace_id: string;
  task_id: string;
  agent_name: string;
  input_summary: string;
  output_summary: string;
  schema_validation_result: string;
  elapsed_time_ms: number;
  retry_count: number;
  error_message?: string;
  model_name?: string;
  token_usage?: number;
};

export type Dag = {
  nodes: Array<{ id: string; label: string; status: string }>;
  edges: Array<{ source: string; target: string; label: string }>;
};
