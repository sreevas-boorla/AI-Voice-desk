import React from 'react';
import { Calendar, Clock, User, Stethoscope, CheckCircle2, XCircle, AlertTriangle, IndianRupee, Loader2 } from 'lucide-react';
import { PendingAction } from '../types';

interface ConfirmationCardProps {
  pendingAction: PendingAction;
  onConfirm: (actionId: string, confirmed: boolean) => Promise<void>;
  isSubmitting: boolean;
}

export const ConfirmationCard: React.FC<ConfirmationCardProps> = ({
  pendingAction,
  onConfirm,
  isSubmitting
}) => {
  const { action_type, summary_text, details, action_id } = pendingAction;

  const isBook = action_type === 'BOOK';
  const isReschedule = action_type === 'RESCHEDULE';
  const isCancel = action_type === 'CANCEL';

  return (
    <div className="my-4 rounded-xl border border-teal-500/40 bg-gradient-to-br from-navy-900 to-navy-850 p-5 shadow-xl shadow-teal-950/40 relative overflow-hidden">
      {/* Accent Header Ribbon */}
      <div className="flex items-center justify-between pb-3 mb-3 border-b border-navy-800">
        <div className="flex items-center gap-2">
          <span className={`px-2.5 py-0.5 rounded text-xs font-bold uppercase tracking-wider ${
            isBook ? 'bg-teal-500/20 text-teal-400 border border-teal-500/30' :
            isReschedule ? 'bg-amber-500/20 text-amber-400 border border-amber-500/30' :
            'bg-rose-500/20 text-rose-400 border border-rose-500/30'
          }`}>
            {action_type} Request
          </span>
          <span className="text-xs text-slate-400">Explicit Confirmation Required</span>
        </div>
        <div className="flex items-center gap-1 text-[11px] text-amber-400 bg-amber-500/10 px-2 py-0.5 rounded font-mono">
          <Clock className="w-3 h-3 inline" /> Expires in 10m
        </div>
      </div>

      {/* Main Details */}
      <div className="space-y-2.5 mb-4 text-sm">
        <div className="flex items-start gap-2.5 text-slate-200">
          <Stethoscope className="w-4 h-4 text-teal-400 mt-0.5 shrink-0" />
          <div>
            <span className="font-semibold text-white">{details.provider_name}</span>
            {details.provider_specialty && (
              <span className="text-xs text-slate-400 ml-2">({details.provider_specialty})</span>
            )}
          </div>
        </div>

        {isBook && (
          <>
            <div className="flex items-center gap-2.5 text-slate-300">
              <Calendar className="w-4 h-4 text-teal-400 shrink-0" />
              <span>{details.formatted_date}</span>
            </div>
            <div className="flex items-center gap-2.5 text-slate-300">
              <Clock className="w-4 h-4 text-teal-400 shrink-0" />
              <span className="font-medium text-teal-300">{details.formatted_time}</span>
            </div>
            <div className="flex items-center gap-2.5 text-slate-300">
              <User className="w-4 h-4 text-teal-400 shrink-0" />
              <span>Patient: <strong className="text-white">{details.patient_name}</strong> ({details.patient_phone})</span>
            </div>
            {details.fee && (
              <div className="flex items-center gap-2.5 text-slate-300 font-medium">
                <IndianRupee className="w-4 h-4 text-teal-400 shrink-0" />
                <span>Consultation Fee: <strong className="text-emerald-400">₹{details.fee}</strong></span>
              </div>
            )}
          </>
        )}

        {isReschedule && (
          <div className="bg-navy-950/60 p-3 rounded-lg border border-navy-800 text-xs space-y-2">
            <div className="text-slate-400 line-through">
              Previous: {details.old_formatted_date}
            </div>
            <div className="text-emerald-300 font-semibold flex items-center gap-1.5">
              <Clock className="w-3.5 h-3.5 text-emerald-400" />
              New Slot: {details.new_formatted_date} at {details.new_formatted_time}
            </div>
          </div>
        )}

        {isCancel && (
          <div className="bg-rose-950/20 p-3 rounded-lg border border-rose-900/30 text-xs text-rose-300">
            Booking reference <strong className="text-white">{details.booking_reference}</strong> will be permanently cancelled.
          </div>
        )}
      </div>

      <p className="text-xs text-slate-400 mb-4 bg-navy-950/40 p-2.5 rounded border border-navy-800/80">
        {summary_text}
      </p>

      {/* Buttons */}
      <div className="flex items-center gap-3">
        <button
          onClick={() => onConfirm(action_id, true)}
          disabled={isSubmitting}
          className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-teal-500 hover:bg-teal-400 text-navy-950 font-semibold text-sm transition-all shadow-md shadow-teal-500/20 disabled:opacity-50"
        >
          {isSubmitting ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <CheckCircle2 className="w-4 h-4" />
          )}
          <span>Confirm & Persist</span>
        </button>

        <button
          onClick={() => onConfirm(action_id, false)}
          disabled={isSubmitting}
          className="px-4 py-2.5 rounded-lg bg-navy-800 hover:bg-navy-750 text-slate-300 hover:text-white font-medium text-sm transition-all border border-navy-700 disabled:opacity-50"
        >
          <XCircle className="w-4 h-4 inline mr-1 text-slate-400" />
          Decline
        </button>
      </div>
    </div>
  );
};
