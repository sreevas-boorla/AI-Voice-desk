import React, { useState } from 'react';
import { Activity, CheckCircle, AlertCircle, ChevronDown, ChevronUp, Clock, Terminal } from 'lucide-react';
import { ToolEvent } from '../types';

interface AgentActivityDrawerProps {
  events: ToolEvent[];
}

export const AgentActivityDrawer: React.FC<AgentActivityDrawerProps> = ({ events }) => {
  const [isOpen, setIsOpen] = useState(false);
  const [expandedIndex, setExpandedIndex] = useState<number | null>(null);

  if (events.length === 0) return null;

  return (
    <div className="border border-navy-800 rounded-xl bg-navy-900/90 overflow-hidden shadow-lg mt-4 transition-all">
      {/* Header bar */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center justify-between px-4 py-3 bg-navy-850 hover:bg-navy-800 transition-colors text-left"
      >
        <div className="flex items-center gap-2 text-xs font-semibold text-slate-300">
          <Terminal className="w-4 h-4 text-teal-400" />
          <span>Agent Activity & Tool Executions</span>
          <span className="px-2 py-0.5 rounded-full bg-teal-500/10 text-teal-400 border border-teal-500/20 text-[11px] font-mono">
            {events.length} event{events.length > 1 ? 's' : ''}
          </span>
        </div>
        <div className="flex items-center gap-1 text-slate-400 text-xs">
          <span>{isOpen ? 'Collapse' : 'Inspect'}</span>
          {isOpen ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
        </div>
      </button>

      {/* Body */}
      {isOpen && (
        <div className="p-3 max-h-80 overflow-y-auto space-y-2 divide-y divide-navy-800/60 font-mono text-xs">
          {events.map((ev, idx) => {
            const isExpanded = expandedIndex === idx;
            const isSuccess = ev.status === 'success';

            return (
              <div key={idx} className="pt-2 first:pt-0">
                <div
                  onClick={() => setExpandedIndex(isExpanded ? null : idx)}
                  className="flex items-center justify-between cursor-pointer py-1.5 px-2 rounded hover:bg-navy-800/60 transition-colors"
                >
                  <div className="flex items-center gap-2">
                    {isSuccess ? (
                      <CheckCircle className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                    ) : (
                      <AlertCircle className="w-3.5 h-3.5 text-rose-400 shrink-0" />
                    )}
                    <span className="font-semibold text-teal-300">{ev.tool_name}</span>
                  </div>
                  <div className="flex items-center gap-3 text-slate-400 text-[11px]">
                    <span className="flex items-center gap-1">
                      <Clock className="w-3 h-3 text-slate-500" /> {ev.duration_ms}ms
                    </span>
                    <span className={`px-1.5 py-0.2 rounded text-[10px] uppercase font-bold ${
                      isSuccess ? 'bg-emerald-500/10 text-emerald-400' : 'bg-rose-500/10 text-rose-400'
                    }`}>
                      {ev.status}
                    </span>
                  </div>
                </div>

                <div className="text-slate-300 px-2 py-1 text-[11px] font-sans">
                  {ev.result_summary}
                </div>

                {/* Expanded parameter inspector */}
                {isExpanded && (
                  <div className="mt-2 bg-navy-950 p-2.5 rounded border border-navy-800 space-y-2">
                    <div>
                      <div className="text-[10px] text-slate-500 uppercase font-semibold mb-1">Arguments:</div>
                      <pre className="text-[11px] text-amber-300/90 overflow-x-auto whitespace-pre-wrap">
                        {JSON.stringify(ev.arguments, null, 2)}
                      </pre>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
