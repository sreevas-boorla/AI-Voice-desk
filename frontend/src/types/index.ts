export interface ToolEvent {
  tool_name: string;
  status: 'executing' | 'success' | 'error';
  duration_ms: number;
  arguments: Record<string, any>;
  result_summary: string;
  timestamp: string;
}

export interface PendingAction {
  action_id: string;
  action_type: 'BOOK' | 'RESCHEDULE' | 'CANCEL';
  summary_text: string;
  expires_at: string;
  details: Record<string, any>;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  tool_events?: ToolEvent[];
  pending_action?: PendingAction;
  timestamp: string;
}

export interface Provider {
  id: number;
  name: string;
  title: string;
  specialty: string;
  bio: string;
  consultation_fee: number;
  avatar_url?: string;
  is_active: boolean;
  schedules?: any[];
}

export interface AppointmentItem {
  id: number;
  booking_reference: string;
  patient_name: string;
  patient_phone: string;
  provider_id: number;
  provider_name: string;
  provider_specialty: string;
  service_name: string;
  fee: number;
  start_time: string;
  end_time: string;
  formatted_date: string;
  formatted_time: string;
  status: 'CONFIRMED' | 'RESCHEDULED' | 'CANCELLED';
  verification_code?: string;
  notes?: string;
  created_at: string;
}

export interface AdminStats {
  total_appointments: number;
  confirmed_appointments: number;
  rescheduled_appointments: number;
  cancelled_appointments: number;
  today_appointments: number;
  open_handoffs: number;
  active_providers: number;
}

export interface HandoffItem {
  id: number;
  patient_name: string;
  patient_phone: string;
  reason: string;
  status: 'OPEN' | 'IN_PROGRESS' | 'RESOLVED';
  notes?: string;
  created_at: string;
  resolved_at?: string;
}

export interface SystemStatus {
  database: { status: string; type: string };
  voice_provider: { configured: boolean; provider: string; mode: string };
  llm_provider: { configured: boolean; provider: string; mode: string };
  environment: string;
  demo_mode: boolean;
}
