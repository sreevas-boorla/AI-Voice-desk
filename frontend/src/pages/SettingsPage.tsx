import React, { useState, useEffect } from 'react';
import {
  Settings, Stethoscope, Building2, Phone, MapPin, Clock,
  ShieldCheck, Activity, RotateCcw, AlertTriangle, CheckCircle2,
  Sparkles, IndianRupee, HelpCircle
} from 'lucide-react';
import { fetchClinicInfo, fetchSystemStatus, resetDemoData } from '../services/api';
import { SystemStatus } from '../types';

export const SettingsPage: React.FC = () => {
  const [clinicInfo, setClinicInfo] = useState<any>(null);
  const [systemStatus, setSystemStatus] = useState<SystemStatus | null>(null);
  const [isResetting, setIsResetting] = useState(false);
  const [resetMessage, setResetMessage] = useState<string | null>(null);
  const [showConfirmReset, setShowConfirmReset] = useState(false);

  useEffect(() => {
    fetchClinicInfo().then(setClinicInfo).catch(() => {});
    fetchSystemStatus().then(setSystemStatus).catch(() => {});
  }, []);

  const handleReset = async () => {
    setIsResetting(true);
    setResetMessage(null);
    try {
      const res = await resetDemoData();
      setResetMessage(res.message);
      setShowConfirmReset(false);
    } catch (e: any) {
      setResetMessage(`Reset failed: ${e.message}`);
    } finally {
      setIsResetting(false);
    }
  };

  return (
    <div className="max-w-5xl mx-auto px-4 lg:px-8 py-8 space-y-8">
      
      {/* Title */}
      <div>
        <h1 className="text-2xl font-black text-white tracking-tight flex items-center gap-2.5">
          <Settings className="w-6 h-6 text-teal-400" />
          <span>Clinic Information & System Settings</span>
        </h1>
        <p className="text-xs text-slate-400 mt-1">
          Review CareBridge Clinic configurations, provider connections, and demo controls.
        </p>
      </div>

      {resetMessage && (
        <div className="p-4 rounded-xl bg-teal-500/10 border border-teal-500/30 text-xs text-teal-300 flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4 text-teal-400 shrink-0" />
          <span>{resetMessage}</span>
        </div>
      )}

      {/* Grid: Clinic Details & System Health */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        
        {/* Clinic Info Card */}
        {clinicInfo && (
          <div className="p-6 rounded-2xl bg-navy-900 border border-navy-800 space-y-4 shadow-xl">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-teal-500/10 text-teal-400 flex items-center justify-center font-bold">
                <Building2 className="w-5 h-5" />
              </div>
              <div>
                <h2 className="text-base font-bold text-white">{clinicInfo.name}</h2>
                <p className="text-xs text-teal-400">{clinicInfo.tagline}</p>
              </div>
            </div>

            <div className="space-y-2.5 text-xs text-slate-300 pt-2 border-t border-navy-800">
              <div className="flex items-start gap-2.5">
                <MapPin className="w-4 h-4 text-teal-400 shrink-0 mt-0.5" />
                <span>{clinicInfo.address}</span>
              </div>
              <div className="flex items-center gap-2.5">
                <Phone className="w-4 h-4 text-teal-400 shrink-0" />
                <span>{clinicInfo.phone}</span>
              </div>
              <div className="flex items-center gap-2.5">
                <Clock className="w-4 h-4 text-teal-400 shrink-0" />
                <span>Timezone: {clinicInfo.timezone} (Indian Standard Time)</span>
              </div>
            </div>

            {/* Operating Hours */}
            <div className="pt-2 border-t border-navy-800">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">Operating Hours</h3>
              <div className="space-y-1.5 text-xs">
                {Object.entries(clinicInfo.hours).map(([days, timing]: any) => (
                  <div key={days} className="flex justify-between p-2 rounded bg-navy-950 text-slate-300">
                    <span className="font-medium">{days.replace(/_/g, ' ')}</span>
                    <span className="text-teal-300 font-mono text-[11px]">{timing}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* System Connections & Health */}
        {systemStatus && (
          <div className="p-6 rounded-2xl bg-navy-900 border border-navy-800 space-y-4 shadow-xl">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-emerald-500/10 text-emerald-400 flex items-center justify-center font-bold">
                <Activity className="w-5 h-5" />
              </div>
              <div>
                <h2 className="text-base font-bold text-white">Integration Status</h2>
                <p className="text-xs text-emerald-400">Security & provider diagnostics</p>
              </div>
            </div>

            <div className="space-y-3 pt-2 border-t border-navy-800 text-xs">
              
              <div className="p-3 rounded-xl bg-navy-950 border border-navy-850 space-y-1">
                <div className="flex items-center justify-between">
                  <span className="font-medium text-slate-300">Database Layer</span>
                  <span className="px-2 py-0.5 rounded text-[10px] bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-bold uppercase">
                    {systemStatus.database.status}
                  </span>
                </div>
                <div className="text-[11px] text-slate-500">{systemStatus.database.type}</div>
              </div>

              <div className="p-3 rounded-xl bg-navy-950 border border-navy-850 space-y-1">
                <div className="flex items-center justify-between">
                  <span className="font-medium text-slate-300">Voice Processing Engine</span>
                  <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase border ${
                    systemStatus.voice_provider.mode === 'live'
                      ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                      : 'bg-amber-500/10 text-amber-400 border-amber-500/20'
                  }`}>
                    {systemStatus.voice_provider.mode === 'live' ? 'Live WebRTC' : 'Demo Simulation'}
                  </span>
                </div>
                <div className="text-[11px] text-slate-500">{systemStatus.voice_provider.provider}</div>
              </div>

              <div className="p-3 rounded-xl bg-navy-950 border border-navy-850 space-y-1">
                <div className="flex items-center justify-between">
                  <span className="font-medium text-slate-300">LLM & Tool Calling</span>
                  <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase border ${
                    systemStatus.llm_provider.mode === 'live'
                      ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                      : 'bg-amber-500/10 text-amber-400 border-amber-500/20'
                  }`}>
                    {systemStatus.llm_provider.mode === 'live' ? 'Live LLM' : 'Simulator Engine'}
                  </span>
                </div>
                <div className="text-[11px] text-slate-500">{systemStatus.llm_provider.provider}</div>
              </div>

              <div className="text-[11px] text-slate-400 bg-navy-950/60 p-3 rounded-lg border border-navy-850">
                🔒 Security Note: API secrets are held in server-side environment variables and are never bundled into client responses or browser assets.
              </div>
            </div>
          </div>
        )}

      </div>

      {/* Services and Pricing Schedule */}
      {clinicInfo && clinicInfo.services && (
        <div className="p-6 rounded-2xl bg-navy-900 border border-navy-800 space-y-4 shadow-xl">
          <div className="flex items-center gap-2 text-sm font-bold text-white">
            <IndianRupee className="w-4 h-4 text-teal-400" />
            <span>Consultation Fee Schedule & Duration</span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {clinicInfo.services.map((s: any) => (
              <div key={s.id} className="p-3.5 rounded-xl bg-navy-950 border border-navy-800 space-y-1">
                <div className="flex items-center justify-between">
                  <div className="font-bold text-xs text-white">{s.name}</div>
                  <div className="font-mono font-bold text-teal-400 text-xs">₹{s.fee}</div>
                </div>
                <div className="text-[11px] text-slate-400">{s.duration_minutes} min consultation slot</div>
                <div className="text-[11px] text-slate-500 leading-snug pt-1">{s.description}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Demo Reset Panel */}
      <div className="p-6 rounded-2xl bg-amber-500/5 border border-amber-500/20 space-y-4 shadow-xl">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-amber-500/10 text-amber-400 flex items-center justify-center font-bold">
              <RotateCcw className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-base font-bold text-white">Demo Database Reset</h2>
              <p className="text-xs text-slate-400">Restore CareBridge Clinic to clean baseline seed data</p>
            </div>
          </div>

          {!showConfirmReset ? (
            <button
              onClick={() => setShowConfirmReset(true)}
              className="px-4 py-2 rounded-xl bg-amber-500 hover:bg-amber-400 text-navy-950 font-bold text-xs transition-colors shadow-md shadow-amber-500/20"
            >
              Reset Demo State
            </button>
          ) : (
            <div className="flex items-center gap-2">
              <button
                onClick={handleReset}
                disabled={isResetting}
                className="px-4 py-2 rounded-xl bg-rose-600 hover:bg-rose-500 text-white font-bold text-xs transition-colors shadow-md shadow-rose-600/20 disabled:opacity-50"
              >
                {isResetting ? 'Resetting...' : 'Confirm Reset Now'}
              </button>
              <button
                onClick={() => setShowConfirmReset(false)}
                className="px-3 py-2 rounded-xl bg-navy-800 text-slate-300 text-xs font-medium"
              >
                Cancel
              </button>
            </div>
          )}
        </div>

        <p className="text-xs text-slate-400 leading-relaxed">
          This operation clears mutated appointments and restores the synthetic appointments (CB-1001, CB-1002, CB-1003). 
          This action is permanently restricted to demo/development environments and cannot run in production.
        </p>
      </div>

    </div>
  );
};
