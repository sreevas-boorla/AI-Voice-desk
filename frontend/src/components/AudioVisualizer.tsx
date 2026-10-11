import React from 'react';
import { Mic, MicOff, Volume2, Loader2, AlertCircle } from 'lucide-react';

export type VoiceState = 'idle' | 'listening' | 'processing' | 'speaking' | 'muted' | 'error';

interface AudioVisualizerProps {
  state: VoiceState;
  errorMessage?: string;
  isMuted?: boolean;
}

export const AudioVisualizer: React.FC<AudioVisualizerProps> = ({ state, errorMessage, isMuted }) => {
  const getStatusBadge = () => {
    switch (state) {
      case 'listening':
        return {
          label: 'Listening...',
          color: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30',
          dot: 'bg-emerald-400 animate-ping'
        };
      case 'processing':
        return {
          label: 'Thinking & Executing Tools...',
          color: 'bg-teal-500/10 text-teal-300 border-teal-500/30',
          dot: 'bg-teal-400 animate-pulse'
        };
      case 'speaking':
        return {
          label: 'Receptionist Speaking...',
          color: 'bg-cyan-500/10 text-cyan-300 border-cyan-500/30',
          dot: 'bg-cyan-400 animate-bounce'
        };
      case 'muted':
        return {
          label: 'Microphone Muted',
          color: 'bg-slate-500/10 text-slate-400 border-slate-500/30',
          dot: 'bg-slate-400'
        };
      case 'error':
        return {
          label: 'Connection Error',
          color: 'bg-rose-500/10 text-rose-400 border-rose-500/30',
          dot: 'bg-rose-400'
        };
      default:
        return {
          label: 'Ready / Standby',
          color: 'bg-navy-800 text-slate-400 border-navy-700',
          dot: 'bg-slate-500'
        };
    }
  };

  const badge = getStatusBadge();

  return (
    <div className="flex flex-col items-center justify-center p-6 bg-navy-900/60 rounded-2xl border border-navy-800/80 backdrop-blur-sm relative overflow-hidden transition-all">
      {/* Background Glow */}
      <div className={`absolute inset-0 opacity-15 blur-2xl transition-all duration-700 pointer-events-none ${
        state === 'listening' ? 'bg-emerald-500' :
        state === 'processing' ? 'bg-teal-500' :
        state === 'speaking' ? 'bg-cyan-500' :
        state === 'error' ? 'bg-rose-500' : 'bg-transparent'
      }`} />

      {/* Wave Bars */}
      <div className="h-14 flex items-center justify-center gap-1.5 my-2">
        {state === 'listening' || state === 'speaking' ? (
          <>
            <div className="w-1.5 bg-teal-400 rounded-full animate-wave-1"></div>
            <div className="w-1.5 bg-teal-300 rounded-full animate-wave-2"></div>
            <div className="w-1.5 bg-teal-400 rounded-full animate-wave-3"></div>
            <div className="w-1.5 bg-cyan-400 rounded-full animate-wave-4"></div>
            <div className="w-1.5 bg-teal-300 rounded-full animate-wave-5"></div>
            <div className="w-1.5 bg-teal-400 rounded-full animate-wave-2"></div>
            <div className="w-1.5 bg-teal-300 rounded-full animate-wave-1"></div>
          </>
        ) : state === 'processing' ? (
          <div className="flex items-center gap-2 text-teal-400 text-sm">
            <Loader2 className="w-6 h-6 animate-spin text-teal-400" />
            <span className="font-mono text-xs tracking-wide">Processing query...</span>
          </div>
        ) : (
          <div className="flex items-center gap-1.5 opacity-40">
            <div className="w-1.5 h-2 bg-slate-600 rounded-full"></div>
            <div className="w-1.5 h-3 bg-slate-600 rounded-full"></div>
            <div className="w-1.5 h-2 bg-slate-600 rounded-full"></div>
            <div className="w-1.5 h-4 bg-slate-600 rounded-full"></div>
            <div className="w-1.5 h-2 bg-slate-600 rounded-full"></div>
          </div>
        )}
      </div>

      {/* Status Badge */}
      <div className="flex items-center gap-2 mt-1">
        <div className={`flex items-center gap-2 px-3 py-1 rounded-full text-xs font-medium border ${badge.color}`}>
          <span className={`w-2 h-2 rounded-full ${badge.dot}`}></span>
          <span>{badge.label}</span>
        </div>
      </div>

      {errorMessage && (
        <div className="flex items-center gap-1.5 text-xs text-rose-400 mt-2 bg-rose-500/10 px-3 py-1 rounded-lg border border-rose-500/20">
          <AlertCircle className="w-3.5 h-3.5 shrink-0" />
          <span>{errorMessage}</span>
        </div>
      )}
    </div>
  );
};
