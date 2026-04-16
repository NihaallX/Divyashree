import { API_BASE_URL } from "@/lib/config"

export type AuthResponse = {
  access_token: string
  refresh_token: string
  token_type: string
  user: Record<string, unknown>
}

export type Agent = {
  id: string
  name: string
  prompt_text?: string
  template_source?: string
  llm_model?: string
  temperature?: number
  max_tokens?: number
  is_active?: boolean
  user_id?: string
  updated_at?: string
}

export type Contact = {
  id: string
  user_id: string
  name: string
  phone: string
  email?: string
  company?: string
  created_at?: string
}

export type Campaign = {
  id: string
  name: string
  state: string
  timezone?: string
  agent_id?: string
  agent_name?: string
  stats?: {
    total?: number
    completed?: number
    failed?: number
    pending?: number
    calling?: number
    success_rate?: number
  }
  created_at?: string
}

export type DashboardStats = {
  totalCalls: number
  interestedCalls: number
  notInterestedCalls: number
  avgConfidence: number
  todayCalls: number
}

export type AnalyticsPoint = {
  date: string
  count: number
  completed: number
  failed: number
}

export type AnalyticsResponse = {
  dailyCalls: AnalyticsPoint[]
  outcomeDistribution: {
    interested: number
    notInterested: number
    noAnswer: number
    other: number
  }
  hourlyBreakdown: Array<{ hour: number; count: number }>
  averageDuration: number
  successRate: number
  totalCalls: number
  completedCalls: number
  dateRange: {
    start: string
    end: string
    days: number
  }
}

export type CallRecord = {
  id: string
  agent_id?: string
  to_number?: string
  from_number?: string
  status?: string
  duration?: number
  created_at?: string
  recording_url?: string
  [key: string]: unknown
}

export type TemplateRecord = {
  id: string
  name: string
  description?: string
  category?: string
  content?: string
}

export type KnowledgeRecord = {
  id: string
  title: string
  source_file?: string
  source_url?: string
  file_type?: string
  metadata?: Record<string, unknown>
  created_at?: string
}

export type UserProfile = {
  id: string
  email?: string
  name?: string
  phone?: string
  company?: string
  created_at?: string
  updated_at?: string
}

function buildAuthHeaders(token?: string): HeadersInit {
  if (!token) return { "Content-Type": "application/json" }
  return {
    "Content-Type": "application/json",
    Authorization: `Bearer ${token}`,
  }
}

async function parseResponse<T>(res: Response): Promise<T> {
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    const detail = (data as { detail?: string }).detail || "Request failed"
    throw new Error(detail)
  }
  return data as T
}

export async function signup(payload: {
  email: string
  password: string
  name?: string
}): Promise<AuthResponse> {
  const res = await fetch(`${API_BASE_URL}/auth/signup`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  })
  return parseResponse<AuthResponse>(res)
}

export async function login(payload: {
  email: string
  password: string
}): Promise<AuthResponse> {
  const res = await fetch(`${API_BASE_URL}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  })
  return parseResponse<AuthResponse>(res)
}

export async function getHealth(): Promise<Record<string, unknown>> {
  const res = await fetch(`${API_BASE_URL}/health`)
  return parseResponse<Record<string, unknown>>(res)
}

export async function getAgents(params: {
  userId?: string
  isActive?: boolean
  token?: string
} = {}): Promise<Agent[]> {
  const query = new URLSearchParams()
  if (params.userId) query.set("user_id", params.userId)
  if (params.isActive !== undefined) query.set("is_active", String(params.isActive))

  const suffix = query.toString() ? `?${query.toString()}` : ""
  const res = await fetch(`${API_BASE_URL}/agents${suffix}`, {
    headers: buildAuthHeaders(params.token),
  })
  return parseResponse<Agent[]>(res)
}

export async function getCampaigns(token: string): Promise<Campaign[]> {
  const res = await fetch(`${API_BASE_URL}/campaigns`, {
    headers: buildAuthHeaders(token),
  })
  const data = await parseResponse<{ campaigns?: Campaign[] }>(res)
  return data.campaigns || []
}

export async function startCampaign(campaignId: string, token: string): Promise<{ message: string }> {
  const res = await fetch(`${API_BASE_URL}/campaigns/${campaignId}/start`, {
    method: "POST",
    headers: buildAuthHeaders(token),
  })
  return parseResponse<{ message: string }>(res)
}

export async function pauseCampaign(campaignId: string, token: string): Promise<{ message: string }> {
  const res = await fetch(`${API_BASE_URL}/campaigns/${campaignId}/pause`, {
    method: "POST",
    headers: buildAuthHeaders(token),
  })
  return parseResponse<{ message: string }>(res)
}

export async function getContacts(token: string, userId: string): Promise<Contact[]> {
  const query = new URLSearchParams({ user_id: userId })
  const res = await fetch(`${API_BASE_URL}/api/contacts?${query.toString()}`, {
    headers: buildAuthHeaders(token),
  })
  const data = await parseResponse<{ contacts?: Contact[] }>(res)
  return data.contacts || []
}

export async function getDashboardStats(token: string): Promise<DashboardStats> {
  const res = await fetch(`${API_BASE_URL}/dashboard/stats`, {
    headers: buildAuthHeaders(token),
  })
  return parseResponse<DashboardStats>(res)
}

export async function getAnalytics(token: string, days = 14): Promise<AnalyticsResponse> {
  const query = new URLSearchParams({ days: String(days) })
  const res = await fetch(`${API_BASE_URL}/analytics?${query.toString()}`, {
    headers: buildAuthHeaders(token),
  })
  return parseResponse<AnalyticsResponse>(res)
}

export async function getCalls(token: string, userId?: string): Promise<CallRecord[]> {
  const query = new URLSearchParams()
  if (userId) query.set("user_id", userId)
  const suffix = query.toString() ? `?${query.toString()}` : ""
  const res = await fetch(`${API_BASE_URL}/calls${suffix}`, {
    headers: buildAuthHeaders(token),
  })
  return parseResponse<CallRecord[]>(res)
}

export async function getCallById(callId: string, token: string): Promise<CallRecord> {
  const res = await fetch(`${API_BASE_URL}/calls/${callId}`, {
    headers: buildAuthHeaders(token),
  })
  return parseResponse<CallRecord>(res)
}

export async function getCallTranscripts(callId: string, token: string): Promise<Array<Record<string, unknown>>> {
  const res = await fetch(`${API_BASE_URL}/calls/${callId}/transcripts`, {
    headers: buildAuthHeaders(token),
  })
  return parseResponse<Array<Record<string, unknown>>>(res)
}

export async function getCallAnalysis(callId: string, token: string): Promise<Record<string, unknown>> {
  const res = await fetch(`${API_BASE_URL}/calls/${callId}/analysis`, {
    headers: buildAuthHeaders(token),
  })
  return parseResponse<Record<string, unknown>>(res)
}

export async function getTemplates(token: string): Promise<TemplateRecord[]> {
  const res = await fetch(`${API_BASE_URL}/api/templates`, {
    headers: buildAuthHeaders(token),
  })
  return parseResponse<TemplateRecord[]>(res)
}

export async function previewTemplatePrompt(
  token: string,
  payload: { prompt_text: string; sample_user_input: string; temperature?: number; max_tokens?: number }
): Promise<{ preview_response: string; prompt_used: string; tokens_used: string }> {
  const res = await fetch(`${API_BASE_URL}/api/preview`, {
    method: "POST",
    headers: buildAuthHeaders(token),
    body: JSON.stringify(payload),
  })
  return parseResponse<{ preview_response: string; prompt_used: string; tokens_used: string }>(res)
}

export async function getAgentKnowledge(agentId: string, token: string): Promise<KnowledgeRecord[]> {
  const res = await fetch(`${API_BASE_URL}/api/agents/${agentId}/knowledge`, {
    headers: buildAuthHeaders(token),
  })
  return parseResponse<KnowledgeRecord[]>(res)
}

export async function getCalStatus(token: string): Promise<Record<string, unknown>> {
  const res = await fetch(`${API_BASE_URL}/cal/status`, {
    headers: buildAuthHeaders(token),
  })
  return parseResponse<Record<string, unknown>>(res)
}

export async function getCalBookings(token: string): Promise<{ bookings: Array<Record<string, unknown>> }> {
  const res = await fetch(`${API_BASE_URL}/cal/bookings`, {
    headers: buildAuthHeaders(token),
  })
  return parseResponse<{ bookings: Array<Record<string, unknown>> }>(res)
}

export async function getUpcomingEvents(token: string): Promise<{ events: Array<Record<string, unknown>> }> {
  const res = await fetch(`${API_BASE_URL}/events/upcoming`, {
    headers: buildAuthHeaders(token),
  })
  return parseResponse<{ events: Array<Record<string, unknown>> }>(res)
}

export async function getCurrentUser(token: string): Promise<UserProfile> {
  const res = await fetch(`${API_BASE_URL}/auth/me`, {
    headers: buildAuthHeaders(token),
  })
  return parseResponse<UserProfile>(res)
}
