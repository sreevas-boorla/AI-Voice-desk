import React from 'react';
import { Mic, ShieldCheck, Activity, Stethoscope, Settings, LayoutDashboard, Sparkles, Clock } from 'lucide-react';

interface NavbarProps {
  activeTab: 'receptionist' | 'admin' | 'settings';
  setActiveTab: (tab: 'receptionist' | 'admin' | 'settings') => void;
  isDemoMode: boolean;
}

export const Navbar: React.FC<NavbarProps> = ({ activeTab, setActiveTab, isDemoMode }) => {
  return (
    <header className="sticky top-0 z-40 bg-navy-950/80 backdrop-blur-md border-b border-navy-800/80 px-4 lg:px-8 py-3.5 transition-all">
      <div className="max-w-7xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-4">
        
        {/* Brand */}
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-teal-600 to-teal-400 flex items-center justify-center shadow-lg shadow-teal-500/20 text-navy-950 font-bold">
            <Stethoscope className="w-5 h-5 text-navy-950" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-extrabold text-lg tracking-tight text-white">VoiceDesk</span>
              <span className="text-xs px-2 py-0.5 rounded-full bg-teal-500/10 text-teal-400 border border-teal-500/20 font-medium">
                CareBridge Clinic
              </span>
            </div>
            <p className="text-xs text-slate-400 flex items-center gap-1.5 mt-0.5">
              <span>Jubilee Hills, Hyderabad</span>
              <span className="w-1 h-1 rounded-full bg-slate-500"></span>
              <span className="flex items-center gap-1 text-teal-400/90 font-mono text-[11px]">
                <Clock className="w-3 h-3 inline" /> IST (UTC+5:30)
              </span>
            </p>
          </div>
        </div>

        {/* Center Nav */}
        <nav className="flex items-center gap-1 bg-navy-900/90 p-1.5 rounded-xl border border-navy-800">
          <button
            onClick={() => setActiveTab('receptionist')}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
              activeTab === 'receptionist'
                ? 'bg-teal-500 text-navy-950 shadow-md shadow-teal-500/20 font-semibold'
                : 'text-slate-300 hover:text-white hover:bg-navy-800/50'
            }`}
          >
            <Mic className="w-4 h-4" />
            <span>Receptionist</span>
          </button>
          
          <button
            onClick={() => setActiveTab('admin')}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
              activeTab === 'admin'
                ? 'bg-teal-500 text-navy-950 shadow-md shadow-teal-500/20 font-semibold'
                : 'text-slate-300 hover:text-white hover:bg-navy-800/50'
            }`}
          >
            <LayoutDashboard className="w-4 h-4" />
            <span>Admin Portal</span>
          </button>

          <button
            onClick={() => setActiveTab('settings')}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
              activeTab === 'settings'
                ? 'bg-teal-500 text-navy-950 shadow-md shadow-teal-500/20 font-semibold'
                : 'text-slate-300 hover:text-white hover:bg-navy-800/50'
            }`}
          >
            <Settings className="w-4 h-4" />
            <span>Clinic & Settings</span>
          </button>
        </nav>

        {/* Status Indicators */}
        <div className="flex items-center gap-2.5">
          <div className="hidden md:flex items-center gap-1.5 px-3 py-1 rounded-full bg-navy-900 border border-navy-800 text-xs text-slate-300">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
            <span>API Active</span>
          </div>

          <div className={`flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium border ${
            isDemoMode 
              ? 'bg-amber-500/10 text-amber-300 border-amber-500/30' 
              : 'bg-emerald-500/10 text-emerald-300 border-emerald-500/30'
          }`}>
            <Sparkles className="w-3.5 h-3.5" />
            <span>{isDemoMode ? 'Demo Mode (Simulated)' : 'Live AI Mode'}</span>
          </div>
        </div>

      </div>
    </header>
  );
};
