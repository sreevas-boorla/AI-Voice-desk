import React, { useState, useEffect, useRef } from 'react';
import {
  Mic, MicOff, Send, PhoneOff, PhoneCall, Volume2, VolumeX,
  Sparkles, RefreshCw, AlertCircle, ShieldCheck, CheckCircle2,
  Calendar, Clock, User, MessageSquare, Terminal, ChevronRight
} from 'lucide-react';
import { ChatMessage, ToolEvent, PendingAction } from '../types';
import { sendChatMessage, confirmPendingAction } from '../services/api';
import { AudioVisualizer, VoiceState } from '../components/AudioVisualizer';
import { ConfirmationCard } from '../components/ConfirmationCard';
import { AgentActivityDrawer } from '../components/AgentActivityDrawer';
import { DemoReferencePanel } from '../components/DemoReferencePanel';

interface ReceptionistPageProps {
  isDemoMode: boolean;
}

export const ReceptionistPage: React.FC<ReceptionistPageProps> = ({ isDemoMode }) => {
  const [mode, setMode] = useState<'text' | 'voice'>('voice');
  const [sessionToken, setSessionToken] = useState<string>(() => {
    return 'sess_' + crypto.randomUUID();
  });
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [voiceState, setVoiceState] = useState<VoiceState>('idle');
  const [isVoiceActive, setIsVoiceActive] = useState(false);
  const [isMuted, setIsMuted] = useState(false);
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const [allToolEvents, setAllToolEvents] = useState<ToolEvent[]>([]);
  const [activePendingAction, setActivePendingAction] = useState<PendingAction | null>(null);
  const [isConfirmingAction, setIsConfirmingAction] = useState(false);
  const [verifiedReference, setVerifiedReference] = useState<string | null>(null);

  const transcriptEndRef = useRef<HTMLDivElement>(null);
  const recognitionRef = useRef<any>(null);
  const synthRef = useRef<SpeechSynthesis | null>(typeof window !== 'undefined' ? window.speechSynthesis : null);

  const voiceActiveRef = useRef(false);
  const mutedRef = useRef(false);
  const busyRef = useRef(false);
  const submitRef = useRef<(text: string) => Promise<void>>(async () => {});
  useEffect(() => () => {
    voiceActiveRef.current = false;
    recognitionRef.current?.abort();
    synthRef.current?.cancel();
  }, []);

  // Auto-scroll transcript
  useEffect(() => {
    transcriptEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, activePendingAction]);

  // Initial greeting
  useEffect(() => {
    const initialGreeting: ChatMessage = {
      id: 'init-1',
      role: 'assistant',
      content:
        "Hello and welcome to CareBridge Clinic, Hyderabad! I'm your AI receptionist. " +
        "I can help you check doctor availability, book appointments, find or modify an existing booking, " +
        "or answer questions regarding our services and fees. How may I assist you today?",
      timestamp: new Date().toISOString()
    };
    setMessages([initialGreeting]);
  }, []);

  // Web Speech API Voice Implementation
  const initSpeechRecognition = () => {
    if (typeof window === 'undefined') return null;
    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRecognition) {
      setVoiceError("Your browser doesn't support Web Speech recognition. Switching to text mode.");
      setMode('text');
      return null;
    }

    try {
      const recognition = new SpeechRecognition();
      recognition.continuous = true;
      recognition.interimResults = false;
      recognition.lang = 'en-IN'; // Indian English / Asia Kolkata

      recognition.onstart = () => {
        setVoiceError(null);
        setVoiceState('listening');
      };

      recognition.onresult = (event: any) => {
        const lastIndex = event.results.length - 1;
        const transcript = event.results[lastIndex][0].transcript.trim();
        if (transcript) {
          void submitRef.current(transcript);
        }
      };

      recognition.onerror = (event: any) => {
        if (event.error === 'not-allowed') {
          setVoiceError('Microphone permission was denied. Please allow microphone access or use text mode.');
          setVoiceState('error');
          voiceActiveRef.current = false;
    setIsVoiceActive(false);
        } else if (event.error !== 'no-speech') {
          setVoiceError(`Audio input error: ${event.error}`);
          setVoiceState('error');
        }
      };

      recognition.onend = () => {
        if (voiceActiveRef.current && !mutedRef.current) {
          try {
            recognition.start();
          } catch (_) {}
        }
      };

      return recognition;
    } catch (e: any) {
      setVoiceError(e.message || 'Failed to initialize speech engine');
      return null;
    }
  };

  // Speak AI response with TTS
  const speakText = (text: string) => {
    if (!synthRef.current || isMuted || mode === 'text') return;

    // Interrupt previous speech
    synthRef.current.cancel();

    // Clean markdown asterisks and formatting before speaking
    const cleanSpeech = text
      .replace(/\*\*/g, '')
      .replace(/\*/g, '')
      .replace(/#/g, '')
      .replace(/\[.*?\]\(.*?\)/g, '')
      .replace(/- /g, '');

    const utterance = new SpeechSynthesisUtterance(cleanSpeech);
    utterance.rate = 1.0;
    utterance.pitch = 1.0;

    utterance.onstart = () => {
      setVoiceState('speaking');
    };

    utterance.onend = () => {
      if (isVoiceActive) {
        setVoiceState('listening');
      } else {
        setVoiceState('idle');
      }
    };

    utterance.onerror = () => {
      setVoiceState(isVoiceActive ? 'listening' : 'idle');
    };

    synthRef.current.speak(utterance);
  };

  const startVoiceConversation = () => {
    setVoiceError(null);
    voiceActiveRef.current = true;
    setIsVoiceActive(true);
    setVoiceState('listening');

    if (!recognitionRef.current) {
      recognitionRef.current = initSpeechRecognition();
    }
    if (recognitionRef.current) {
      try {
        recognitionRef.current.start();
      } catch (_) {}
    }
  };

  const endVoiceConversation = () => {
    voiceActiveRef.current = false;
    setIsVoiceActive(false);
    setVoiceState('idle');
    if (recognitionRef.current) {
      try {
        recognitionRef.current.stop();
      } catch (_) {}
    }
    if (synthRef.current) {
      synthRef.current.cancel();
    }
  };

  const toggleMute = () => {
    if (isMuted) {
      mutedRef.current = false;
      setIsMuted(false);
      if (isVoiceActive && recognitionRef.current) {
        try { recognitionRef.current.start(); } catch (_) {}
      }
      setVoiceState(isVoiceActive ? 'listening' : 'idle');
    } else {
      mutedRef.current = true;
      setIsMuted(true);
      if (recognitionRef.current) {
        try { recognitionRef.current.stop(); } catch (_) {}
      }
      if (synthRef.current) {
        synthRef.current.cancel();
      }
      setVoiceState('muted');
    }
  };

  // Core submission handler for both voice transcripts and typed messages
  const handleUserSubmission = async (textToSend: string) => {
    if (!textToSend.trim() || busyRef.current) return;
    busyRef.current = true;

    // If currently speaking, stop immediately to allow user interruption
    if (synthRef.current) {
      synthRef.current.cancel();
    }

    const userMessage: ChatMessage = {
      id: 'user-' + Date.now(),
      role: 'user',
      content: textToSend.trim(),
      timestamp: new Date().toISOString()
    };

    setMessages((prev) => [...prev, userMessage]);
    setInputValue('');
    setIsLoading(true);
    setVoiceState('processing');

    try {
      const response = await sendChatMessage(textToSend, sessionToken, mode);

      if (response.session_token) {
        setSessionToken(response.session_token);
      }
      if (response.verified_reference) {
        setVerifiedReference(response.verified_reference);
      }

      // Record any tool execution events
      if (response.tool_events && response.tool_events.length > 0) {
        setAllToolEvents((prev) => [...prev, ...response.tool_events]);
      }

      // Check if pending action was generated
      if (response.pending_action) {
        setActivePendingAction(response.pending_action);
      } else {
        setActivePendingAction(null);
      }

      const assistantMessage: ChatMessage = {
        id: 'asst-' + Date.now(),
        role: 'assistant',
        content: response.reply,
        tool_events: response.tool_events,
        pending_action: response.pending_action,
        timestamp: new Date().toISOString()
      };

      setMessages((prev) => [...prev, assistantMessage]);

      // Speak response in voice mode
      if (mode === 'voice' && isVoiceActive && !isMuted) {
        speakText(response.reply);
      } else {
        setVoiceState(isVoiceActive ? 'listening' : 'idle');
      }
    } catch (err: any) {
      const errorMsg = err.message || 'Something went wrong processing your request.';
      const errorResponse: ChatMessage = {
        id: 'err-' + Date.now(),
        role: 'assistant',
        content: `I encountered an issue: ${errorMsg}`,
        timestamp: new Date().toISOString()
      };
      setMessages((prev) => [...prev, errorResponse]);
      setVoiceState('idle');
    } finally {
      busyRef.current = false;
      setIsLoading(false);
    }
  };

  submitRef.current = handleUserSubmission;

  // Execute explicit action confirmation
  const handleConfirmAction = async (actionId: string, confirmed: boolean) => {
    setIsConfirmingAction(true);
    try {
      const res = await confirmPendingAction(sessionToken, actionId, confirmed);
      setActivePendingAction(null);

      const statusMsg: ChatMessage = {
        id: 'conf-' + Date.now(),
        role: 'assistant',
        content: res.message,
        timestamp: new Date().toISOString()
      };
      setMessages((prev) => [...prev, statusMsg]);

      if (mode === 'voice' && isVoiceActive && !isMuted) {
        speakText(res.message);
      }
    } catch (e: any) {
      const errMessage: ChatMessage = {
        id: 'conf-err-' + Date.now(),
        role: 'assistant',
        content: `Confirmation failed: ${e.message}`,
        timestamp: new Date().toISOString()
      };
      setMessages((prev) => [...prev, errMessage]);
    } finally {
      setIsConfirmingAction(false);
    }
  };

  return (
    <div className="max-w-7xl mx-auto px-4 lg:px-8 py-8 space-y-6">
      
      {/* Top Banner & Quick Reference Panel */}
      {isDemoMode && <DemoReferencePanel onSelectPrompt={handleUserSubmission} />}

      {/* Main Grid: Left Control & Voice Engine | Right Interactive Transcript */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        
        {/* Left Column: Voice / Controls / Activity Panel (5 cols) */}
        <div className="lg:col-span-5 space-y-5">
          
          {/* Mode Switcher */}
          <div className="bg-navy-900/90 p-1.5 rounded-xl border border-navy-800 flex items-center gap-1">
            <button
              onClick={() => {
                setMode('voice');
                if (!isVoiceActive) startVoiceConversation();
              }}
              className={`flex-1 py-2 rounded-lg text-xs font-bold transition-all flex items-center justify-center gap-2 ${
                mode === 'voice'
                  ? 'bg-teal-500 text-navy-950 shadow-md shadow-teal-500/20'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              <Mic className="w-3.5 h-3.5" />
              <span>Voice Mode</span>
            </button>
            <button
              onClick={() => {
                setMode('text');
                endVoiceConversation();
              }}
              className={`flex-1 py-2 rounded-lg text-xs font-bold transition-all flex items-center justify-center gap-2 ${
                mode === 'text'
                  ? 'bg-teal-500 text-navy-950 shadow-md shadow-teal-500/20'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              <MessageSquare className="w-3.5 h-3.5" />
              <span>Text Chat Mode</span>
            </button>
          </div>

          {/* Visualizer & Audio Controls */}
          <div className="bg-navy-900/80 rounded-2xl border border-navy-800 p-6 shadow-xl space-y-5 relative">
            <div className="flex items-center justify-between">
              <span className="text-xs uppercase tracking-wider font-bold text-slate-400">
                Receptionist Audio Channel
              </span>
              {verifiedReference && (
                <span className="flex items-center gap-1 text-[11px] px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-300 border border-emerald-500/20 font-mono">
                  <ShieldCheck className="w-3.5 h-3.5" /> Verified: {verifiedReference}
                </span>
              )}
            </div>

            <AudioVisualizer state={voiceState} errorMessage={voiceError || undefined} isMuted={isMuted} />

            {/* Audio Action Buttons */}
            <div className="flex items-center justify-center gap-3 pt-2">
              {mode === 'voice' && (
                <>
                  {!isVoiceActive ? (
                    <button
                      onClick={startVoiceConversation}
                      className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-teal-500 hover:bg-teal-400 text-navy-950 font-bold text-xs tracking-wide transition-all shadow-lg shadow-teal-500/20 hover:scale-[1.02]"
                    >
                      <PhoneCall className="w-4 h-4" />
                      <span>Start Voice Call</span>
                    </button>
                  ) : (
                    <button
                      onClick={endVoiceConversation}
                      className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-rose-500 hover:bg-rose-600 text-white font-bold text-xs tracking-wide transition-all shadow-lg shadow-rose-500/20 hover:scale-[1.02]"
                    >
                      <PhoneOff className="w-4 h-4" />
                      <span>End Voice Call</span>
                    </button>
                  )}

                  <button
                    onClick={toggleMute}
                    disabled={!isVoiceActive}
                    className={`p-2.5 rounded-xl border transition-all disabled:opacity-30 ${
                      isMuted
                        ? 'bg-amber-500/10 text-amber-400 border-amber-500/30'
                        : 'bg-navy-800 text-slate-300 border-navy-700 hover:text-white'
                    }`}
                    title={isMuted ? 'Unmute Microphone' : 'Mute Microphone'}
                  >
                    {isMuted ? <MicOff className="w-4 h-4" /> : <Mic className="w-4 h-4" />}
                  </button>
                </>
              )}
            </div>

            <div className="text-[11px] text-slate-400 text-center leading-relaxed">
              {mode === 'voice' ? (
                <span>
                  Speak naturally into your microphone. Say "Book Dr. Aisha tomorrow" or "Verify booking CB-1001 with code 4821".
                </span>
              ) : (
                <span>Text mode enabled. Type your questions or scheduling requests below.</span>
              )}
            </div>
          </div>

          {/* Real-time Agent Activity Drawer */}
          <AgentActivityDrawer events={allToolEvents} />

        </div>

        {/* Right Column: Live Conversation Transcript (7 cols) */}
        <div className="lg:col-span-7 bg-navy-900/80 rounded-2xl border border-navy-800 flex flex-col h-[680px] shadow-xl overflow-hidden">
          
          {/* Transcript Header */}
          <div className="px-6 py-4 bg-navy-850 border-b border-navy-800 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-full bg-teal-400"></span>
              <h2 className="text-sm font-bold text-white tracking-wide">Live Conversation Transcript</h2>
            </div>
            <span className="text-[11px] font-mono text-slate-400">
              Session: {sessionToken.substring(0, 10)}...
            </span>
          </div>

          {/* Scrollable Message List */}
          <div className="flex-1 p-6 overflow-y-auto space-y-4">
            {messages.map((msg) => {
              const isUser = msg.role === 'user';
              return (
                <div
                  key={msg.id}
                  className={`flex flex-col ${isUser ? 'items-end' : 'items-start'} space-y-1.5`}
                >
                  <div className="flex items-center gap-1.5 text-[11px] text-slate-400 px-1">
                    <span>{isUser ? 'You' : 'CareBridge AI Receptionist'}</span>
                    <span className="text-slate-600">•</span>
                    <span className="font-mono text-[10px]">
                      {new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </span>
                  </div>

                  <div
                    className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-relaxed shadow-md ${
                      isUser
                        ? 'bg-teal-500 text-navy-950 font-medium rounded-tr-sm'
                        : 'bg-navy-800/90 text-slate-100 border border-navy-700/80 rounded-tl-sm whitespace-pre-wrap'
                    }`}
                  >
                    {msg.content}
                  </div>
                </div>
              );
            })}

            {/* Active Pending Action Confirmation Card */}
            {activePendingAction && (
              <ConfirmationCard
                pendingAction={activePendingAction}
                onConfirm={handleConfirmAction}
                isSubmitting={isConfirmingAction}
              />
            )}

            {/* Loading Indicator in Chat */}
            {isLoading && (
              <div className="flex items-center gap-2 text-xs text-teal-400 bg-navy-850 px-3 py-2 rounded-xl border border-navy-800 w-fit">
                <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                <span>Checking CareBridge schedule & executing tools...</span>
              </div>
            )}

            <div ref={transcriptEndRef} />
          </div>

          {/* Chat Input Bar */}
          <div className="p-4 bg-navy-950/80 border-t border-navy-800">
            <form
              onSubmit={(e) => {
                e.preventDefault();
                handleUserSubmission(inputValue);
              }}
              className="flex items-center gap-2"
            >
              <input
                type="text"
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                placeholder={
                  mode === 'voice'
                    ? "Type a message or speak into your microphone..."
                    : "Ask about clinic hours, book an appointment, or verify existing..."
                }
                disabled={isLoading}
                className="flex-1 bg-navy-900 border border-navy-750 focus:border-teal-500 rounded-xl px-4 py-2.5 text-sm text-white placeholder-slate-500 focus:outline-none transition-colors"
              />
              <button
                type="submit"
                disabled={isLoading || !inputValue.trim()}
                className="px-4 py-2.5 rounded-xl bg-teal-500 hover:bg-teal-400 disabled:opacity-40 text-navy-950 font-semibold text-sm transition-all flex items-center gap-1.5 shadow-md shadow-teal-500/20"
              >
                <span>Send</span>
                <Send className="w-3.5 h-3.5" />
              </button>
            </form>
          </div>

        </div>

      </div>

    </div>
  );
};
