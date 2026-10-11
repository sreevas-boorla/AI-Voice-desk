import React, { useState, useEffect } from 'react';
import { Navbar } from './components/Navbar';
import { ReceptionistPage } from './pages/ReceptionistPage';
import { AdminDashboard } from './pages/AdminDashboard';
import { SettingsPage } from './pages/SettingsPage';
import { fetchSystemStatus } from './services/api';
import { SystemStatus } from './types';

export function App() {
  const [activeTab, setActiveTab] = useState<'receptionist' | 'admin' | 'settings'>('receptionist');
  const [isDemoMode, setIsDemoMode] = useState(true);

  useEffect(() => {
    fetchSystemStatus()
      .then((status: SystemStatus) => {
        setIsDemoMode(status.demo_mode);
      })
      .catch(() => {
        setIsDemoMode(true);
      });
  }, []);

  return (
    <div className="min-h-screen bg-[#070D18] text-slate-100 flex flex-col font-sans selection:bg-teal-500 selection:text-navy-950">
      {/* Top Navigation */}
      <Navbar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        isDemoMode={isDemoMode}
      />

      {/* Main Content View */}
      <main className="flex-1 pb-12">
        {activeTab === 'receptionist' && <ReceptionistPage isDemoMode={isDemoMode} />}
        {activeTab === 'admin' && <AdminDashboard />}
        {activeTab === 'settings' && <SettingsPage />}
      </main>

      {/* Clean Footer */}
      <footer className="border-t border-navy-800/80 bg-navy-950 py-6 text-center text-xs text-slate-500">
        <div className="max-w-7xl mx-auto px-4 flex flex-col sm:flex-row items-center justify-between gap-3">
          <p>
            © 2026 <strong>CareBridge Clinic</strong>, Jubilee Hills, Hyderabad. Powered by <strong>VoiceDesk</strong>.
          </p>
          <div className="flex items-center gap-4 text-[11px] text-slate-400">
            <span>Asia/Kolkata Timezone (IST)</span>
            <span>•</span>
            <span>Safe Portfolio Environment</span>
            <span>•</span>
            <span>HIPAA-Compliant Design</span>
          </div>
        </div>
      </footer>
    </div>
  );
}

export default App;
