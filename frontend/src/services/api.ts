const API_BASE = '/api';

export async function sendChatMessage(message: string, sessionToken?: string, channel: string = 'text') {
  const res = await fetch(`${API_BASE}/agent/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, session_token: sessionToken, channel })
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Network request failed' }));
    throw new Error(err.detail || 'Chat request failed');
  }
  return res.json();
}

export async function confirmPendingAction(sessionToken: string, actionId: string, confirmed: boolean) {
  const res = await fetch(`${API_BASE}/agent/confirm`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_token: sessionToken, action_id: actionId, confirmed })
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Failed to confirm action' }));
    throw new Error(err.detail || 'Confirmation failed');
  }
  return res.json();
}

export async function verifyAppointmentAccess(bookingReference: string, verificationCode: string, sessionToken: string) {
  const res = await fetch(`${API_BASE}/appointments/verify`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      booking_reference: bookingReference,
      verification_code: verificationCode,
      session_token: sessionToken
    })
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Verification failed' }));
    throw new Error(err.detail || 'Verification failed');
  }
  return res.json();
}

export async function fetchProviders() {
  const res = await fetch(`${API_BASE}/appointments/providers`);
  return res.json();
}

export async function fetchClinicInfo() {
  const res = await fetch(`${API_BASE}/system/clinic-info`);
  return res.json();
}

export async function fetchSystemStatus() {
  const res = await fetch(`${API_BASE}/system/status`);
  return res.json();
}

export async function fetchVoiceStatus() {
  const res = await fetch(`${API_BASE}/voice/status`);
  return res.json();
}

export async function resetDemoData() {
  const res = await fetch(`${API_BASE}/system/reset-demo`, { method: 'POST' });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Reset failed' }));
    throw new Error(err.detail || 'Reset failed');
  }
  return res.json();
}

// Admin APIs
export async function adminLogin(username: string, password: string) {
  const res = await fetch(`${API_BASE}/admin/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password })
  });
  if (!res.ok) {
    throw new Error('Invalid credentials');
  }
  return res.json();
}

export async function fetchAdminStats(token: string) {
  const res = await fetch(`${API_BASE}/admin/stats`, {
    headers: { Authorization: `Bearer ${token}` }
  });
  if (!res.ok) throw new Error('Unauthorized');
  return res.json();
}

export async function fetchAdminAppointments(token: string, params: Record<string, string> = {}) {
  const query = new URLSearchParams(params).toString();
  const res = await fetch(`${API_BASE}/admin/appointments?${query}`, {
    headers: { Authorization: `Bearer ${token}` }
  });
  if (!res.ok) throw new Error('Unauthorized');
  return res.json();
}

export async function fetchAdminSchedules(token: string) {
  const res = await fetch(`${API_BASE}/admin/schedules`, {
    headers: { Authorization: `Bearer ${token}` }
  });
  if (!res.ok) throw new Error('Unauthorized');
  return res.json();
}

export async function fetchAdminHandoffs(token: string) {
  const res = await fetch(`${API_BASE}/admin/handoffs`, {
    headers: { Authorization: `Bearer ${token}` }
  });
  if (!res.ok) throw new Error('Unauthorized');
  return res.json();
}

export async function updateHandoffStatus(token: string, id: number, status: string, notes?: string) {
  const query = new URLSearchParams({ status, ...(notes ? { notes } : {}) }).toString();
  const res = await fetch(`${API_BASE}/admin/handoffs/${id}?${query}`, {
    method: 'PUT',
    headers: { Authorization: `Bearer ${token}` }
  });
  if (!res.ok) throw new Error('Failed to update handoff');
  return res.json();
}

export async function fetchAdminTranscripts(token: string) {
  const res = await fetch(`${API_BASE}/admin/transcripts`, {
    headers: { Authorization: `Bearer ${token}` }
  });
  if (!res.ok) throw new Error('Unauthorized');
  return res.json();
}

export async function fetchAdminAuditLogs(token: string) {
  const res = await fetch(`${API_BASE}/admin/audit-logs`, {
    headers: { Authorization: `Bearer ${token}` }
  });
  if (!res.ok) throw new Error('Unauthorized');
  return res.json();
}
