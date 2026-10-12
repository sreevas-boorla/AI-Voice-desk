import React, { useState, useEffect } from 'react';
import {
  LayoutDashboard, Calendar, Users, PhoneCall, ShieldAlert,
  Search, Filter, CheckCircle2, AlertCircle, Clock, RefreshCw,
  Lock, LogIn, ArrowRight, Stethoscope, ChevronRight, Check, FileText,
  MessageSquare
} from 'lucide-react';
import {
  adminLogin, fetchAdminStats, fetchAdminAppointments,
  fetchAdminSchedules, fetchAdminHandoffs, updateHandoffStatus,
  fetchAdminTranscripts, fetchAdminAuditLogs
} from '../services/api';
import { AdminStats, AppointmentItem, HandoffItem } from '../types';

export const AdminDashboard: React.FC = () => {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem('voicedesk_admin_token'));
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loginError, setLoginError] = useState<string | null>(null);
  const [isLoggingIn, setIsLoggingIn] = useState(false);

  const [activeTab, setActiveTab] = useState<'appointments' | 'schedules' | 'handoffs' | 'transcripts' | 'audit'>('appointments');
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [appointments, setAppointments] = useState<AppointmentItem[]>([]);
  const [schedules, setSchedules] = useState<any[]>([]);
  const [handoffs, setHandoffs] = useState<HandoffItem[]>([]);
  const [transcripts, setTranscripts] = useState<any[]>([]);
  const [auditLogs, setAuditLogs] = useState<any[]>([]);

  // Filters
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('ALL');
  const [dateFilter, setDateFilter] = useState('');
  const [isLoadingData, setIsLoadingData] = useState(false);

  // Authenticate Admin
  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoggingIn(true);
    setLoginError(null);
    try {
      const res = await adminLogin(username, password);
      localStorage.setItem('voicedesk_admin_token', res.access_token);
      setToken(res.access_token);
    } catch (err: any) {
      setLoginError('Invalid admin credentials. Use admin / CareBridge2026!');
    } finally {
      setIsLoggingIn(false);
    }
  };

  const handleLogout = () => {
    localStorage.removeItem('voicedesk_admin_token');
    setToken(null);
  };

  // Load Admin Data
  const loadDashboardData = async () => {
    if (!token) return;
    setIsLoadingData(true);
    try {
      const [sRes, aRes, scRes, hRes, tRes, auRes] = await Promise.all([
        fetchAdminStats(token),
        fetchAdminAppointments(token, {
          search: searchQuery,
          status: statusFilter,
          ...(dateFilter ? { date_filter: dateFilter } : {})
        }),
        fetchAdminSchedules(token),
        fetchAdminHandoffs(token),
        fetchAdminTranscripts(token),
        fetchAdminAuditLogs(token)
      ]);

      setStats(sRes);
      setAppointments(aRes.items || []);
      setSchedules(scRes || []);
      setHandoffs(hRes || []);
      setTranscripts(tRes || []);
      setAuditLogs(auRes || []);
    } catch (err: any) {
      if (err.message === 'Unauthorized') {
        handleLogout();
      }
    } finally {
      setIsLoadingData(false);
    }
  };

  useEffect(() => {
    if (token) {
      loadDashboardData();
    }
  }, [token, statusFilter, dateFilter]);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    loadDashboardData();
  };

  const handleUpdateHandoff = async (id: number, newStatus: string) => {
    if (!token) return;
    try {
      await updateHandoffStatus(token, id, newStatus);
      loadDashboardData();
    } catch (err) {
      alert('Failed to update handoff status.');
    }
  };

  // Login Form Screen if not logged in
  if (!token) {
    return (
      <div className="max-w-md mx-auto my-16 p-8 bg-navy-900 border border-navy-800 rounded-2xl shadow-2xl space-y-6">
        <div className="text-center space-y-2">
          <div className="w-12 h-12 bg-teal-500/10 text-teal-400 rounded-2xl border border-teal-500/20 flex items-center justify-center mx-auto">
            <Lock className="w-6 h-6" />
          </div>
          <h2 className="text-xl font-bold text-white tracking-tight">CareBridge Staff Portal</h2>
          <p className="text-xs text-slate-400">Restricted administrative access. Enter your credentials to proceed.</p>
        </div>

        {loginError && (
          <div className="p-3 bg-rose-500/10 border border-rose-500/20 rounded-xl text-xs text-rose-300 flex items-center gap-2">
            <AlertCircle className="w-4 h-4 shrink-0" />
            <span>{loginError}</span>
          </div>
        )}

        <form onSubmit={handleLogin} className="space-y-4 text-sm">
          <div>
            <label className="block text-xs font-semibold text-slate-300 mb-1.5">Username</label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full bg-navy-950 border border-navy-800 rounded-xl px-4 py-2.5 text-white focus:outline-none focus:border-teal-500 text-sm"
              required
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-300 mb-1.5">Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full bg-navy-950 border border-navy-800 rounded-xl px-4 py-2.5 text-white focus:outline-none focus:border-teal-500 text-sm"
              required
            />
          </div>

          <button
            type="submit"
            disabled={isLoggingIn}
            className="w-full py-2.5 rounded-xl bg-teal-500 hover:bg-teal-400 text-navy-950 font-bold text-sm transition-all shadow-md shadow-teal-500/20 flex items-center justify-center gap-2"
          >
            {isLoggingIn ? <RefreshCw className="w-4 h-4 animate-spin" /> : <LogIn className="w-4 h-4" />}
            <span>Sign In to Dashboard</span>
          </button>
        </form>

        <div className="text-[11px] text-slate-400 text-center bg-navy-950/60 p-3 rounded-xl border border-navy-850">
          🔒 Protected Access: Authorized CareBridge Clinic administrative personnel only.
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto px-4 lg:px-8 py-8 space-y-6">
      
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 pb-4 border-b border-navy-800">
        <div>
          <h1 className="text-2xl font-black text-white tracking-tight flex items-center gap-2.5">
            <LayoutDashboard className="w-6 h-6 text-teal-400" />
            <span>Clinic Administration Dashboard</span>
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            Real-time management for CareBridge Clinic appointments, schedules, and patient escalations.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={loadDashboardData}
            disabled={isLoadingData}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-navy-800 hover:bg-navy-750 text-slate-300 hover:text-white text-xs border border-navy-700 transition-colors"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isLoadingData ? 'animate-spin' : ''}`} />
            <span>Refresh</span>
          </button>

          <button
            onClick={handleLogout}
            className="px-3 py-1.5 rounded-lg bg-rose-500/10 hover:bg-rose-500/20 text-rose-300 text-xs border border-rose-500/20 font-medium transition-colors"
          >
            Sign Out
          </button>
        </div>
      </div>

      {/* Metrics Row */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3">
          <div className="p-4 rounded-xl bg-navy-900 border border-navy-800 space-y-1">
            <div className="text-[11px] text-slate-400 uppercase tracking-wider font-semibold">Total</div>
            <div className="text-2xl font-bold text-white font-mono">{stats.total_appointments}</div>
          </div>
          <div className="p-4 rounded-xl bg-navy-900 border border-navy-800 space-y-1">
            <div className="text-[11px] text-emerald-400 uppercase tracking-wider font-semibold">Confirmed</div>
            <div className="text-2xl font-bold text-emerald-400 font-mono">{stats.confirmed_appointments}</div>
          </div>
          <div className="p-4 rounded-xl bg-navy-900 border border-navy-800 space-y-1">
            <div className="text-[11px] text-amber-400 uppercase tracking-wider font-semibold">Rescheduled</div>
            <div className="text-2xl font-bold text-amber-400 font-mono">{stats.rescheduled_appointments}</div>
          </div>
          <div className="p-4 rounded-xl bg-navy-900 border border-navy-800 space-y-1">
            <div className="text-[11px] text-rose-400 uppercase tracking-wider font-semibold">Cancelled</div>
            <div className="text-2xl font-bold text-rose-400 font-mono">{stats.cancelled_appointments}</div>
          </div>
          <div className="p-4 rounded-xl bg-navy-900 border border-navy-800 space-y-1">
            <div className="text-[11px] text-cyan-400 uppercase tracking-wider font-semibold">Today</div>
            <div className="text-2xl font-bold text-cyan-400 font-mono">{stats.today_appointments}</div>
          </div>
          <div className="p-4 rounded-xl bg-navy-900 border border-navy-800 space-y-1">
            <div className="text-[11px] text-purple-400 uppercase tracking-wider font-semibold">Handoffs</div>
            <div className="text-2xl font-bold text-purple-400 font-mono">{stats.open_handoffs}</div>
          </div>
          <div className="p-4 rounded-xl bg-navy-900 border border-navy-800 space-y-1">
            <div className="text-[11px] text-teal-400 uppercase tracking-wider font-semibold">Doctors</div>
            <div className="text-2xl font-bold text-teal-400 font-mono">{stats.active_providers}</div>
          </div>
        </div>
      )}

      {/* Sub Tabs */}
      <div className="flex border-b border-navy-800 text-xs font-semibold space-x-1">
        {[
          { id: 'appointments', label: 'Appointments Book', icon: Calendar },
          { id: 'schedules', label: 'Provider Schedules', icon: Users },
          { id: 'handoffs', label: 'Handoff Requests', icon: PhoneCall },
          { id: 'transcripts', label: 'Transcripts (Redacted)', icon: MessageSquare },
          { id: 'audit', label: 'Audit Trail', icon: FileText }
        ].map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id as any)}
              className={`flex items-center gap-2 px-4 py-2.5 border-b-2 transition-all ${
                isActive
                  ? 'border-teal-400 text-teal-400 bg-teal-500/5'
                  : 'border-transparent text-slate-400 hover:text-white hover:bg-navy-850'
              }`}
            >
              <Icon className="w-3.5 h-3.5" />
              <span>{tab.label}</span>
            </button>
          );
        })}
      </div>

      {/* TAB 1: APPOINTMENTS TABLE */}
      {activeTab === 'appointments' && (
        <div className="space-y-4">
          {/* Filters Bar */}
          <div className="flex flex-col sm:flex-row items-center gap-3">
            <form onSubmit={handleSearchSubmit} className="relative flex-1 w-full">
              <Search className="w-4 h-4 absolute left-3 top-3 text-slate-500" />
              <input
                type="text"
                placeholder="Search patient, phone, or reference (e.g. CB-1001)..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full bg-navy-900 border border-navy-800 rounded-xl pl-9 pr-4 py-2 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-teal-500"
              />
            </form>

            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="bg-navy-900 border border-navy-800 rounded-xl px-3 py-2 text-xs text-slate-300 focus:outline-none focus:border-teal-500"
            >
              <option value="ALL">All Statuses</option>
              <option value="CONFIRMED">Confirmed</option>
              <option value="RESCHEDULED">Rescheduled</option>
              <option value="CANCELLED">Cancelled</option>
            </select>

            <input
              type="date"
              value={dateFilter}
              onChange={(e) => setDateFilter(e.target.value)}
              className="bg-navy-900 border border-navy-800 rounded-xl px-3 py-2 text-xs text-slate-300 focus:outline-none focus:border-teal-500"
            />
          </div>

          {/* Table Container */}
          <div className="bg-navy-900 border border-navy-800 rounded-2xl overflow-hidden shadow-xl">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-navy-950 text-slate-400 uppercase tracking-wider font-semibold border-b border-navy-800">
                  <tr>
                    <th className="px-4 py-3">Reference</th>
                    <th className="px-4 py-3">Patient</th>
                    <th className="px-4 py-3">Doctor</th>
                    <th className="px-4 py-3">Date & Time (IST)</th>
                    <th className="px-4 py-3">Fee</th>
                    <th className="px-4 py-3">Status</th>
                    <th className="px-4 py-3">PIN</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-navy-800 text-slate-200">
                  {appointments.length === 0 ? (
                    <tr>
                      <td colSpan={7} className="text-center py-8 text-slate-500">
                        No appointments found matching your search criteria.
                      </td>
                    </tr>
                  ) : (
                    appointments.map((app) => (
                      <tr key={app.id} className="hover:bg-navy-850/60 transition-colors">
                        <td className="px-4 py-3.5 font-mono font-bold text-teal-400">
                          {app.booking_reference}
                        </td>
                        <td className="px-4 py-3.5">
                          <div className="font-semibold text-white">{app.patient_name}</div>
                          <div className="text-[11px] text-slate-400">{app.patient_phone}</div>
                        </td>
                        <td className="px-4 py-3.5">
                          <div className="font-medium">{app.provider_name}</div>
                          <div className="text-[11px] text-slate-400">{app.provider_specialty}</div>
                        </td>
                        <td className="px-4 py-3.5">
                          <div>{app.formatted_date}</div>
                          <div className="text-teal-300 font-mono text-[11px]">{app.formatted_time}</div>
                        </td>
                        <td className="px-4 py-3.5 font-mono font-medium text-emerald-400">
                          ₹{app.fee}
                        </td>
                        <td className="px-4 py-3.5">
                          <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider border ${
                            app.status === 'CONFIRMED' ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' :
                            app.status === 'RESCHEDULED' ? 'bg-amber-500/10 text-amber-400 border-amber-500/20' :
                            'bg-rose-500/10 text-rose-400 border-rose-500/20'
                          }`}>
                            {app.status}
                          </span>
                        </td>
                        <td className="px-4 py-3.5 font-mono text-slate-400 text-[11px]">
                          {app.verification_code}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* TAB 2: SCHEDULES */}
      {activeTab === 'schedules' && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {schedules.map((item) => (
            <div key={item.provider_id} className="p-5 rounded-2xl bg-navy-900 border border-navy-800 space-y-4">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-teal-500/10 text-teal-400 flex items-center justify-center font-bold">
                  <Stethoscope className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="font-bold text-white text-sm">{item.provider_name}</h3>
                  <p className="text-xs text-teal-400">{item.specialty}</p>
                </div>
              </div>

              <div className="space-y-2">
                <div className="text-[11px] uppercase tracking-wider text-slate-400 font-semibold">
                  Weekly Working Hours
                </div>
                <div className="space-y-1.5 text-xs">
                  {item.schedules.map((s: any) => (
                    <div key={s.id} className="flex justify-between p-2 rounded bg-navy-950 text-slate-300">
                      <span className="font-medium">{s.day_name}</span>
                      <span className="font-mono text-teal-300">
                        {s.start_time} - {s.end_time}
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              {item.blocked_slots.length > 0 && (
                <div className="space-y-1.5 pt-2 border-t border-navy-800">
                  <div className="text-[11px] uppercase tracking-wider text-rose-400 font-semibold">
                    Blocked Out Intervals
                  </div>
                  {item.blocked_slots.map((b: any) => (
                    <div key={b.id} className="p-2 rounded bg-rose-500/10 border border-rose-500/20 text-xs text-rose-300">
                      <div>{b.reason}</div>
                      <div className="font-mono text-[10px] text-rose-400/80 mt-0.5">
                        {b.start_time.substring(0, 16)}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* TAB 3: HANDOFFS */}
      {activeTab === 'handoffs' && (
        <div className="space-y-4">
          <div className="bg-navy-900 border border-navy-800 rounded-2xl overflow-hidden shadow-xl">
            <table className="w-full text-left text-xs">
              <thead className="bg-navy-950 text-slate-400 uppercase tracking-wider font-semibold border-b border-navy-800">
                <tr>
                  <th className="px-4 py-3">Patient</th>
                  <th className="px-4 py-3">Callback Phone</th>
                  <th className="px-4 py-3">Reason / Complaint</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-navy-800 text-slate-200">
                {handoffs.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="text-center py-8 text-slate-500">
                      No open handoff requests from reception.
                    </td>
                  </tr>
                ) : (
                  handoffs.map((h) => (
                    <tr key={h.id} className="hover:bg-navy-850/60 transition-colors">
                      <td className="px-4 py-3.5 font-bold text-white">{h.patient_name}</td>
                      <td className="px-4 py-3.5 font-mono text-teal-300">{h.patient_phone}</td>
                      <td className="px-4 py-3.5 max-w-xs">{h.reason}</td>
                      <td className="px-4 py-3.5">
                        <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider border ${
                          h.status === 'OPEN' ? 'bg-rose-500/10 text-rose-400 border-rose-500/20' :
                          h.status === 'IN_PROGRESS' ? 'bg-amber-500/10 text-amber-400 border-amber-500/20' :
                          'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                        }`}>
                          {h.status}
                        </span>
                      </td>
                      <td className="px-4 py-3.5 space-x-2">
                        {h.status !== 'RESOLVED' && (
                          <button
                            onClick={() => handleUpdateHandoff(h.id, 'RESOLVED')}
                            className="px-2.5 py-1 rounded bg-teal-500 hover:bg-teal-400 text-navy-950 font-semibold text-[11px] transition-colors"
                          >
                            Mark Resolved
                          </button>
                        )}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* TAB 4: REDACTED TRANSCRIPTS */}
      {activeTab === 'transcripts' && (
        <div className="space-y-4">
          <div className="p-3 bg-navy-850 rounded-xl border border-navy-800 text-xs text-slate-400 flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
            <span>
              Sensitive data protection active: 4-digit verification PINs and patient phone numbers are automatically redacted.
            </span>
          </div>

          <div className="space-y-3">
            {transcripts.map((t) => (
              <div key={t.session_id} className="p-4 rounded-xl bg-navy-900 border border-navy-800 space-y-2">
                <div className="flex items-center justify-between text-xs text-slate-400 pb-2 border-b border-navy-850">
                  <span className="font-mono text-teal-400">Session {t.session_token}</span>
                  <span>{new Date(t.created_at).toLocaleString()}</span>
                </div>
                <div className="space-y-2 pt-1">
                  {t.messages.map((m: any) => (
                    <div key={m.id} className="text-xs">
                      <strong className={m.role === 'user' ? 'text-teal-300' : 'text-slate-300'}>
                        {m.role === 'user' ? 'User: ' : 'Receptionist: '}
                      </strong>
                      <span className="text-slate-300">{m.content}</span>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* TAB 5: AUDIT TRAIL */}
      {activeTab === 'audit' && (
        <div className="bg-navy-900 border border-navy-800 rounded-2xl overflow-hidden shadow-xl">
          <table className="w-full text-left text-xs">
            <thead className="bg-navy-950 text-slate-400 uppercase tracking-wider font-semibold border-b border-navy-800">
              <tr>
                <th className="px-4 py-3">Timestamp (UTC)</th>
                <th className="px-4 py-3">Action</th>
                <th className="px-4 py-3">Entity</th>
                <th className="px-4 py-3">Actor</th>
                <th className="px-4 py-3">Details</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-navy-800 text-slate-200 font-mono text-[11px]">
              {auditLogs.map((log) => (
                <tr key={log.id} className="hover:bg-navy-850/60 transition-colors">
                  <td className="px-4 py-3 text-slate-400">{log.created_at}</td>
                  <td className="px-4 py-3 font-bold text-teal-400">{log.action}</td>
                  <td className="px-4 py-3">{log.entity_type} {log.entity_id ? `(${log.entity_id})` : ''}</td>
                  <td className="px-4 py-3 text-slate-300">{log.actor_type}</td>
                  <td className="px-4 py-3 text-slate-400 max-w-sm truncate">{log.details || '-'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

    </div>
  );
};
