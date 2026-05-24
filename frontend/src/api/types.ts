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
  source_type: string;
  url?: string;
  local_ref?: string;
  snippet: string;
  confidence: number;
  collected_at: string;
};

export type Claim = {
  claim_id: string;
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
  };
  claims: Claim[];
  qa_result?: QaResult;
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
