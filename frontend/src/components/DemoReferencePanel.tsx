import React, { useState, useEffect } from 'react';
import { KeyRound, Copy, Check, Sparkles, ChevronDown, ChevronUp, Send } from 'lucide-react';
import { fetchDemoReferences } from '../services/api';

interface DemoReferencePanelProps {
  onSelectPrompt: (promptText: string) => void;
}

export const DemoReferencePanel: React.FC<DemoReferencePanelProps> = ({ onSelectPrompt }) => {
  const [isOpen, setIsOpen] = useState(true);
  const [copiedCode, setCopiedCode] = useState<string | null>(null);
  const [sampleBookings, setSampleBookings] = useState<any[]>([
    {
      ref: 'CB-1001',
      code: '4821',
      patient: 'Rahul Sharma',
      provider: 'Dr. Aisha Rao (General Physician)',
      date: 'Next Available Weekday at 10:00 AM'
    },
    {
      ref: 'CB-1002',
      code: '7390',
      patient: 'Ananya Reddy',
      provider: 'Dr. Vikram Patel (Pediatrician)',
      date: 'Next Working Day at 11:30 AM'
    },
    {
      ref: 'CB-1003',
      code: '1945',
      patient: 'Karthik Verma',
      provider: 'Dr. Meera Nambiar (Dermatologist)',
      date: 'Next Working Day at 03:00 PM'
    }
  ]);

  useEffect(() => {
    fetchDemoReferences().then((data) => {
      if (data && data.length > 0) {
        setSampleBookings(data);
      }
    }).catch(() => {});
  }, []);

  const quickPrompts = [
    {
      label: 'Verify & Look Up CB-1001',
      text: 'Please verify booking CB-1001 with code 4821'
    },
    {
      label: 'Check Dr. Aisha Tomorrow Afternoon',
      text: "Check Dr. Aisha Rao's available slots tomorrow afternoon"
    },
    {
      label: 'Book Dr. Vikram for Child Checkup',
      text: 'Book Dr. Vikram Patel tomorrow for child checkup, patient Rohan, phone 9876543210'
    },
    {
      label: 'Reschedule Verified Booking',
      text: 'Reschedule CB-1001 to tomorrow afternoon'
    },
    {
      label: 'Ask Clinic Fees & Hours',
      text: 'What are your consultation fees and clinic operating hours in Hyderabad?'
    },
    {
      label: 'Speak with Human Receptionist',
      text: 'I want to speak with a human receptionist about emergency billing'
    }
  ];

  const handleCopy = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedCode(text);
    setTimeout(() => setCopiedCode(null), 2000);
  };

  return (
    <div className="border border-navy-800 rounded-2xl bg-navy-900/80 backdrop-blur-md overflow-hidden shadow-xl mb-6">
      {/* Top Banner */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center justify-between px-5 py-3.5 bg-navy-850 hover:bg-navy-800 transition-colors text-left"
      >
        <div className="flex items-center gap-2.5">
          <div className="w-6 h-6 rounded-md bg-amber-500/20 text-amber-400 flex items-center justify-center">
            <KeyRound className="w-3.5 h-3.5" />
          </div>
          <div>
            <div className="text-xs font-bold text-white flex items-center gap-2">
              <span>Synthetic Demo Credentials & Test Panel</span>
              <span className="text-[10px] px-2 py-0.5 rounded bg-amber-500/10 text-amber-300 border border-amber-500/20 font-mono">
                Safe Portfolio Data
              </span>
            </div>
            <div className="text-[11px] text-slate-400">
              Pre-seeded appointments for instant lookup, rescheduling, and cancellation testing
            </div>
          </div>
        </div>

        <div className="flex items-center gap-1.5 text-xs text-slate-400">
          <span>{isOpen ? 'Hide Panel' : 'Show Test Data'}</span>
          {isOpen ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
        </div>
      </button>

      {isOpen && (
        <div className="p-5 space-y-4 border-t border-navy-800/80 text-xs">
          {/* Seeded Credentials Grid */}
          <div>
            <div className="text-[11px] uppercase tracking-wider text-slate-400 font-semibold mb-2">
              Synthetic Patient Bookings (Reference & 4-Digit PIN)
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              {sampleBookings.map((b) => (
                <div
                  key={b.ref}
                  className="p-3 rounded-xl bg-navy-950/70 border border-navy-800 hover:border-teal-500/40 transition-all space-y-1.5 relative group"
                >
                  <div className="flex items-center justify-between">
                    <span className="font-mono font-bold text-teal-400 text-sm tracking-wide">
                      {b.ref}
                    </span>
                    <button
                      onClick={() => handleCopy(`${b.ref} code ${b.code}`)}
                      className="text-slate-400 hover:text-white p-1 rounded hover:bg-navy-800 transition-colors"
                      title="Copy reference and code"
                    >
                      {copiedCode === `${b.ref} code ${b.code}` ? (
                        <Check className="w-3.5 h-3.5 text-emerald-400" />
                      ) : (
                        <Copy className="w-3.5 h-3.5" />
                      )}
                    </button>
                  </div>

                  <div className="text-white font-medium">{b.patient}</div>
                  <div className="text-slate-400 text-[11px] truncate">{b.provider}</div>
                  
                  <div className="flex items-center justify-between pt-1 border-t border-navy-850">
                    <span className="text-slate-500 text-[10px]">PIN Code:</span>
                    <span className="font-mono font-semibold text-amber-400 bg-amber-400/10 px-1.5 py-0.5 rounded">
                      {b.code}
                    </span>
                  </div>

                  <button
                    onClick={() => onSelectPrompt(`Please verify booking ${b.ref} with code ${b.code}`)}
                    className="w-full mt-2 py-1 px-2 rounded bg-teal-500/10 hover:bg-teal-500/20 text-teal-300 font-semibold text-[11px] text-center border border-teal-500/20 transition-all flex items-center justify-center gap-1.5"
                  >
                    <Send className="w-3 h-3" />
                    <span>Test Lookup {b.ref}</span>
                  </button>
                </div>
              ))}
            </div>
          </div>

          {/* Quick Click Prompts */}
          <div>
            <div className="text-[11px] uppercase tracking-wider text-slate-400 font-semibold mb-2 flex items-center gap-1.5">
              <Sparkles className="w-3.5 h-3.5 text-teal-400" />
              <span>One-Click Voice / Text Scenarios</span>
            </div>
            <div className="flex flex-wrap gap-2">
              {quickPrompts.map((p, idx) => (
                <button
                  key={idx}
                  onClick={() => onSelectPrompt(p.text)}
                  className="px-3 py-1.5 rounded-lg bg-navy-850 hover:bg-teal-500/10 text-slate-300 hover:text-teal-300 border border-navy-750 hover:border-teal-500/30 text-xs transition-all text-left flex items-center gap-1.5"
                >
                  <span className="w-1.5 h-1.5 rounded-full bg-teal-400"></span>
                  <span>{p.label}</span>
                </button>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
