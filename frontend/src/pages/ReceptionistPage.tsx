import React, { useState, useEffect, useRef, useMemo } from 'react';
import {
  Mic, MicOff, Send, PhoneOff, PhoneCall, Volume2, VolumeX,
  Sparkles, RefreshCw, AlertCircle, ShieldCheck, CheckCircle2,
  Calendar, Clock, User, MessageSquare, Terminal, ChevronRight,
  Radio, Square, Info
} from 'lucide-react';
import { Room, RoomEvent, Track, RemoteTrack, RemoteTrackPublication, RemoteParticipant } from 'livekit-client';
import { ChatMessage, ToolEvent, PendingAction } from '../types';
import {
  sendChatMessage,
  confirmPendingAction,
  fetchVoiceStatus,
  requestLiveKitToken,
  VoiceStatusResponse
} from '../services/api';
import { AudioVisualizer, VoiceState } from '../components/AudioVisualizer';
import { ConfirmationCard } from '../components/ConfirmationCard';
import { AgentActivityDrawer } from '../components/AgentActivityDrawer';
import { DemoReferencePanel } from '../components/DemoReferencePanel';

interface ReceptionistPageProps {
  isDemoMode: boolean;
}

type VoiceEngine = 'livekit' | 'browser';
type LiveKitConnectionState = 'unconfigured' | 'ready_to_connect' | 'connecting' | 'connected' | 'reconnecting' | 'failed' | 'disconnected';

export const ReceptionistPage: React.FC<ReceptionistPageProps> = ({ isDemoMode }) => {
  const [mode, setMode] = useState<'text' | 'voice'>('voice');
  const [voiceEngine, setVoiceEngine] = useState<VoiceEngine>('browser');
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

  // LiveKit connection state
  const [liveKitState, setLiveKitState] = useState<LiveKitConnectionState>('unconfigured');
  const [serverVoiceStatus, setServerVoiceStatus] = useState<VoiceStatusResponse | null>(null);

  // Derive browser speech recognition support dynamically in the browser
  const isBrowserSpeechSupported = useMemo(() => {
    return typeof window !== 'undefined' && Boolean(
      (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
    );
  }, []);

  const transcriptEndRef = useRef<HTMLDivElement>(null);
  const recognitionRef = useRef<any>(null);
  const synthRef = useRef<SpeechSynthesis | null>(typeof window !== 'undefined' ? window.speechSynthesis : null);
  const roomRef = useRef<Room | null>(null);
  const audioElementsRef = useRef<HTMLAudioElement[]>([]);

  const voiceActiveRef = useRef(false);
  const mutedRef = useRef(false);
  const busyRef = useRef(false);
  const isSpeakingRef = useRef(false);
  const currentSpeakingTextRef = useRef<string>('');
  const lastSubmissionRef = useRef<{ text: string; time: number }>({ text: '', time: 0 });
  const sessionTokenRef = useRef(sessionToken);
  sessionTokenRef.current = sessionToken;
  const modeRef = useRef(mode);
  modeRef.current = mode;
  const voiceEngineRef = useRef(voiceEngine);
  voiceEngineRef.current = voiceEngine;

  const submitRef = useRef<(text: string) => Promise<void>>(async () => {});

  // Fetch initial server voice status on load
  useEffect(() => {
    let mounted = true;
    fetchVoiceStatus().then((status) => {
      if (!mounted) return;
      setServerVoiceStatus(status);
      if (status.livekit_ready) {
        setLiveKitState('ready_to_connect');
        setVoiceEngine('livekit');
      } else {
        setLiveKitState('unconfigured');
        setVoiceEngine('browser');
      }
    });
    return () => {
      mounted = false;
    };
  }, []);

  // Cleanup all audio and rooms on unmount
  useEffect(() => {
    return () => {
      voiceActiveRef.current = false;
      isSpeakingRef.current = false;
      try { recognitionRef.current?.abort(); } catch (_) {}
      try { synthRef.current?.cancel(); } catch (_) {}
      if (roomRef.current) {
        try { roomRef.current.disconnect(); } catch (_) {}
        roomRef.current = null;
      }
      audioElementsRef.current.forEach((el) => el.remove());
      audioElementsRef.current = [];
    };
  }, []);

  // Gracefully shutdown active voice engine when switching to text
  useEffect(() => {
    if (mode === 'text') {
      endVoiceConversation();
    }
  }, [mode]);

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

  // Web Speech API Voice Implementation (Browser Fallback)
  const initSpeechRecognition = () => {
    if (typeof window === 'undefined') return null;
    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRecognition) {
      setVoiceError("Your browser doesn't support Web Speech recognition. Text chat remains available.");
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
        if (!transcript) return;

        // Interruption & Echo Handling:
        // If the assistant is currently speaking:
        if (isSpeakingRef.current || synthRef.current?.speaking) {
          const speakingClean = currentSpeakingTextRef.current.toLowerCase();
          const transcriptLower = transcript.toLowerCase();

          // Check if the recognized speech is simply an acoustic echo of the assistant's own output
          const words = transcriptLower.split(/\s+/);
          const isPureEcho = words.length >= 3 && speakingClean.includes(transcriptLower);

          if (isPureEcho) {
            // Echo detected from external speakers; discard
            return;
          }

          // User spoke an intentional interruption!
          // Immediately stop speech synthesis and process user turn
          try {
            synthRef.current?.cancel();
          } catch (_) {}
          isSpeakingRef.current = false;
          currentSpeakingTextRef.current = '';
        }

        void submitRef.current(transcript);
      };

      recognition.onerror = (event: any) => {
        if (event.error === 'not-allowed') {
          setVoiceError('Microphone permission was denied. Please allow microphone access or use text mode.');
          setVoiceState('error');
          voiceActiveRef.current = false;
          setIsVoiceActive(false);
        } else if (event.error === 'network') {
          setVoiceError('Browser speech recognition network service unavailable. Text Chat Mode remains fully functional.');
          setVoiceState('error');
        } else if (event.error !== 'no-speech') {
          setVoiceError(`Audio input error: ${event.error}. You can retry or switch to Text Mode.`);
          setVoiceState('error');
        }
      };

      recognition.onend = () => {
        if (voiceActiveRef.current && !mutedRef.current && voiceEngineRef.current === 'browser') {
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

  // Speak AI response with Browser SpeechSynthesis (Used in Browser Fallback Mode)
  const speakText = (text: string) => {
    if (!synthRef.current || isMuted || modeRef.current === 'text' || voiceEngineRef.current !== 'browser') return;

    // Interrupt previous speech
    try { synthRef.current.cancel(); } catch (_) {}

    // Clean markdown asterisks and formatting before speaking
    const cleanSpeech = text
      .replace(/\*\*/g, '')
      .replace(/\*/g, '')
      .replace(/#/g, '')
      .replace(/\[.*?\]\(.*?\)/g, '')
      .replace(/- /g, '');

    currentSpeakingTextRef.current = cleanSpeech;
    const utterance = new SpeechSynthesisUtterance(cleanSpeech);
    utterance.rate = 1.0;
    utterance.pitch = 1.0;

    utterance.onstart = () => {
      isSpeakingRef.current = true;
      setVoiceState('speaking');
    };

    utterance.onend = () => {
      isSpeakingRef.current = false;
      currentSpeakingTextRef.current = '';
      if (voiceActiveRef.current) {
        setVoiceState('listening');
      } else {
        setVoiceState('idle');
      }
    };

    utterance.onerror = () => {
      isSpeakingRef.current = false;
      currentSpeakingTextRef.current = '';
      setVoiceState(voiceActiveRef.current ? 'listening' : 'idle');
    };

    synthRef.current.speak(utterance);
  };

  // Explicit Stop Speaking (Interrupt) handler
  const handleStopSpeaking = () => {
    if (synthRef.current) {
      try { synthRef.current.cancel(); } catch (_) {}
    }
    isSpeakingRef.current = false;
    currentSpeakingTextRef.current = '';
    if (voiceActiveRef.current) {
      setVoiceState('listening');
    }
  };

  // Connect to LiveKit Room
  const startLiveKitCall = async () => {
    setVoiceError(null);
    setLiveKitState('connecting');
    setVoiceState('processing');

    try {
      const tokenData = await requestLiveKitToken(sessionTokenRef.current, 'Patient');

      // Create LiveKit Room instance
      const room = new Room({
        adaptiveStream: true,
        dynacast: true,
        audioCaptureDefaults: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true
        }
      });
      roomRef.current = room;

      // Listen for Agent audio tracks
      room.on(RoomEvent.TrackSubscribed, (track: RemoteTrack, publication: RemoteTrackPublication, participant: RemoteParticipant) => {
        if (track.kind === Track.Kind.Audio) {
          const audioElement = track.attach();
          audioElementsRef.current.push(audioElement);
          audioElement.style.display = 'none';
          document.body.appendChild(audioElement);
        }
      });

      room.on(RoomEvent.TrackUnsubscribed, (track: RemoteTrack) => {
        track.detach().forEach((el) => el.remove());
      });

      // Listen for structured data messages from Agent Worker (Transcripts, Tools, Pending Actions)
      room.on(RoomEvent.DataReceived, (payload: Uint8Array) => {
        try {
          const text = new TextDecoder().decode(payload);
          const data = JSON.parse(text);

          if (data.type === 'agent_response') {
            if (data.user_text) {
              const uMsg: ChatMessage = {
                id: 'lk-user-' + Date.now(),
                role: 'user',
                content: data.user_text,
                timestamp: new Date().toISOString()
              };
              setMessages((prev) => [...prev, uMsg]);
            }

            if (data.tool_events && data.tool_events.length > 0) {
              setAllToolEvents((prev) => [...prev, ...data.tool_events]);
            }

            if (data.pending_action) {
              setActivePendingAction(data.pending_action);
            }

            if (data.reply) {
              const aMsg: ChatMessage = {
                id: 'lk-asst-' + Date.now(),
                role: 'assistant',
                content: data.reply,
                tool_events: data.tool_events,
                pending_action: data.pending_action,
                timestamp: new Date().toISOString()
              };
              setMessages((prev) => [...prev, aMsg]);
            }
          } else if (data.type === 'error') {
            setVoiceError(data.message || 'Voice worker error.');
          }
        } catch (err) {
          console.error('Error handling LiveKit room data packet:', err);
        }
      });

      room.on(RoomEvent.Connected, () => {
        setLiveKitState('connected');
        setVoiceState('listening');
        setIsVoiceActive(true);
        voiceActiveRef.current = true;
      });

      room.on(RoomEvent.Reconnecting, () => {
        setLiveKitState('reconnecting');
        setVoiceState('processing');
      });

      room.on(RoomEvent.Reconnected, () => {
        setLiveKitState('connected');
        setVoiceState('listening');
      });

      room.on(RoomEvent.Disconnected, () => {
        setLiveKitState('disconnected');
        setVoiceState('idle');
        setIsVoiceActive(false);
        voiceActiveRef.current = false;
      });

      // Connect to LiveKit server with room token
      await room.connect(tokenData.livekit_url, tokenData.token);

      // Publish local microphone audio track
      await room.localParticipant.setMicrophoneEnabled(!isMuted);

    } catch (err: any) {
      console.error('LiveKit connection error:', err);
      setLiveKitState('failed');
      setVoiceError(
        err.message || 'Failed to connect to LiveKit streaming room. You can switch to Browser Web Speech fallback.'
      );
      setVoiceState('error');
      setIsVoiceActive(false);
      voiceActiveRef.current = false;
    }
  };

  // Start Voice Conversation (Dispatches to selected active engine)
  const startVoiceConversation = async () => {
    setVoiceError(null);

    if (voiceEngine === 'livekit') {
      await startLiveKitCall();
    } else {
      // Browser Web Speech Engine
      if (!isBrowserSpeechSupported) {
        setVoiceError("Your browser does not support Web Speech recognition. Switching to text chat.");
        setMode('text');
        return;
      }

      voiceActiveRef.current = true;
      setIsVoiceActive(true);
      setVoiceState('listening');

      if (!recognitionRef.current) {
        recognitionRef.current = initSpeechRecognition();
      }
      if (recognitionRef.current) {
        try {
          recognitionRef.current.start();
        } catch (_) {
          try {
            recognitionRef.current.stop();
            setTimeout(() => {
              if (voiceActiveRef.current && voiceEngineRef.current === 'browser') {
                try { recognitionRef.current?.start(); } catch (_) {}
              }
            }, 150);
          } catch (_) {}
        }
      }
    }
  };

  // End Voice Conversation (Cleans up current active engine)
  const endVoiceConversation = () => {
    voiceActiveRef.current = false;
    isSpeakingRef.current = false;
    currentSpeakingTextRef.current = '';
    setIsVoiceActive(false);
    setVoiceState('idle');

    // Clean LiveKit
    if (roomRef.current) {
      try {
        roomRef.current.disconnect();
      } catch (_) {}
      roomRef.current = null;
    }
    audioElementsRef.current.forEach((el) => el.remove());
    audioElementsRef.current = [];
    if (liveKitState === 'connected' || liveKitState === 'connecting') {
      setLiveKitState('disconnected');
    }

    // Clean Browser Speech
    if (recognitionRef.current) {
      try {
        recognitionRef.current.stop();
        recognitionRef.current.abort();
      } catch (_) {}
    }
    if (synthRef.current) {
      try { synthRef.current.cancel(); } catch (_) {}
    }
  };

  // Toggle Microphone Mute
  const toggleMute = async () => {
    const nextMuted = !isMuted;
    setIsMuted(nextMuted);
    mutedRef.current = nextMuted;

    if (voiceEngine === 'livekit' && roomRef.current) {
      try {
        await roomRef.current.localParticipant.setMicrophoneEnabled(!nextMuted);
      } catch (err) {
        console.error('Failed to toggle mic in LiveKit:', err);
      }
      setVoiceState(nextMuted ? 'muted' : 'listening');
    } else {
      // Browser Speech
      if (nextMuted) {
        if (recognitionRef.current) {
          try { recognitionRef.current.stop(); } catch (_) {}
        }
        if (synthRef.current) {
          try { synthRef.current.cancel(); } catch (_) {}
        }
        setVoiceState('muted');
      } else {
        if (isVoiceActive && recognitionRef.current) {
          try { recognitionRef.current.start(); } catch (_) {}
        }
        setVoiceState(isVoiceActive ? 'listening' : 'idle');
      }
    }
  };

  // Core submission handler for both voice transcripts and typed messages
  const handleUserSubmission = async (textToSend: string) => {
    const cleanText = textToSend.trim();
    if (!cleanText || busyRef.current) return;

    // Deduplicate rapid repeat of exact same text within 2.5s (prevents double triggers)
    const now = Date.now();
    const normalized = cleanText.toLowerCase();
    if (lastSubmissionRef.current.text === normalized && now - lastSubmissionRef.current.time < 2500) {
      return;
    }
    lastSubmissionRef.current = { text: normalized, time: now };
    busyRef.current = true;

    // If currently speaking in browser mode, stop immediately to allow user interruption
    if (synthRef.current) {
      try { synthRef.current.cancel(); } catch (_) {}
      isSpeakingRef.current = false;
      currentSpeakingTextRef.current = '';
    }

    const userMessage: ChatMessage = {
      id: 'user-' + Date.now(),
      role: 'user',
      content: cleanText,
      timestamp: new Date().toISOString()
    };

    setMessages((prev) => [...prev, userMessage]);
    setInputValue('');
    setIsLoading(true);
    setVoiceState('processing');

    try {
      const response = await sendChatMessage(cleanText, sessionTokenRef.current, modeRef.current);

      if (response.session_token) {
        setSessionToken(response.session_token);
        sessionTokenRef.current = response.session_token;
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

      // If in browser voice mode, speak response with SpeechSynthesis
      if (modeRef.current === 'voice' && voiceActiveRef.current && !mutedRef.current && voiceEngineRef.current === 'browser') {
        speakText(response.reply);
      } else {
        setVoiceState(voiceActiveRef.current ? 'listening' : 'idle');
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
      setVoiceState(voiceActiveRef.current ? 'listening' : 'idle');
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
        if (voiceEngine === 'browser') {
          speakText(res.message);
        } else if (voiceEngine === 'livekit' && roomRef.current && roomRef.current.state === 'connected') {
          try {
            const payload = JSON.stringify({
              type: 'confirmation_result',
              action_id: actionId
            });
            const encoder = new TextEncoder();
            await roomRef.current.localParticipant.publishData(encoder.encode(payload), { reliable: true });
          } catch (pubErr) {
            console.warn('Failed to deliver confirmation result to LiveKit room:', pubErr);
          }
        }
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
          
          {/* Channel Mode Switcher (Voice vs Text) */}
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

          {/* Voice Engine Selector (Only visible in Voice Mode) */}
          {mode === 'voice' && (
            <div className="bg-navy-900/70 p-3 rounded-xl border border-navy-800 space-y-2">
              <div className="flex items-center justify-between text-xs">
                <span className="font-bold text-slate-300 flex items-center gap-1.5">
                  <Radio className="w-3.5 h-3.5 text-teal-400" /> Voice Engine:
                </span>
                <span className="text-[11px] font-mono text-slate-400">
                  {voiceEngine === 'livekit' ? (
                    liveKitState === 'connected' ? (
                      <span className="text-emerald-400 font-semibold">● Connected</span>
                    ) : liveKitState === 'connecting' ? (
                      <span className="text-amber-400 font-semibold">◌ Connecting...</span>
                    ) : serverVoiceStatus?.livekit_ready ? (
                      <span className="text-teal-400">Configured</span>
                    ) : (
                      <span className="text-slate-500">Unconfigured</span>
                    )
                  ) : (
                    <span className="text-slate-300">Browser Speech</span>
                  )}
                </span>
              </div>

              <div className="grid grid-cols-2 gap-2 text-xs">
                <button
                  type="button"
                  disabled={isVoiceActive}
                  onClick={() => {
                    setVoiceEngine('livekit');
                    setVoiceError(null);
                  }}
                  className={`p-2 rounded-lg border text-left transition-all ${
                    voiceEngine === 'livekit'
                      ? 'bg-teal-500/10 border-teal-500/40 text-teal-300'
                      : 'bg-navy-800/40 border-navy-700/60 text-slate-400 hover:text-slate-200'
                  } ${isVoiceActive ? 'opacity-50 cursor-not-allowed' : ''}`}
                >
                  <div className="font-semibold">LiveKit WebRTC</div>
                  <div className="text-[10px] text-slate-400">
                    {serverVoiceStatus?.livekit_ready ? 'Streaming ready' : 'Requires credentials'}
                  </div>
                </button>

                <button
                  type="button"
                  disabled={isVoiceActive}
                  onClick={() => {
                    setVoiceEngine('browser');
                    setVoiceError(null);
                  }}
                  className={`p-2 rounded-lg border text-left transition-all ${
                    voiceEngine === 'browser'
                      ? 'bg-teal-500/10 border-teal-500/40 text-teal-300'
                      : 'bg-navy-800/40 border-navy-700/60 text-slate-400 hover:text-slate-200'
                  } ${isVoiceActive ? 'opacity-50 cursor-not-allowed' : ''}`}
                >
                  <div className="font-semibold">Browser Web Speech</div>
                  <div className="text-[10px] text-slate-400">
                    {isBrowserSpeechSupported ? 'Fallback ready' : 'Not supported'}
                  </div>
                </button>
              </div>

              {voiceEngine === 'livekit' && !serverVoiceStatus?.livekit_ready && (
                <div className="flex items-start gap-1.5 p-2 bg-amber-500/10 border border-amber-500/20 rounded-lg text-[11px] text-amber-300/90 leading-tight">
                  <Info className="w-3.5 h-3.5 shrink-0 mt-0.5" />
                  <span>
                    LiveKit server credentials are not configured on backend. Starting a call in this mode will prompt to switch to Browser Web Speech fallback.
                  </span>
                </div>
              )}
            </div>
          )}

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

                  {/* Explicit "Stop Speaking" (Interrupt) button for browser speech playback */}
                  {voiceEngine === 'browser' && isVoiceActive && voiceState === 'speaking' && (
                    <button
                      onClick={handleStopSpeaking}
                      className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-amber-500/20 text-amber-300 border border-amber-500/40 text-xs font-semibold hover:bg-amber-500/30 transition-all shadow"
                      title="Interrupt assistant spoken response"
                    >
                      <Square className="w-3.5 h-3.5 fill-current" />
                      <span>Stop Speaking</span>
                    </button>
                  )}
                </>
              )}
            </div>

            <div className="text-[11px] text-slate-400 text-center leading-relaxed">
              {mode === 'voice' ? (
                voiceEngine === 'livekit' ? (
                  <span>
                    LiveKit WebRTC active with server-side VAD and echo cancellation. Speak into your microphone.
                  </span>
                ) : (
                  <span>
                    Browser Speech Fallback: Speak naturally or click "Stop Speaking" to interrupt assistant audio.
                  </span>
                )
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
              <span className="w-2.5 h-2.5 rounded-full bg-teal-400 animate-pulse"></span>
              <h2 className="text-xs font-bold uppercase tracking-wider text-slate-300">
                Live Conversation Session
              </h2>
            </div>
            <span className="text-[11px] font-mono text-slate-400 bg-navy-900 px-2 py-0.5 rounded border border-navy-750">
              Session: {sessionToken.substring(0, 13)}...
            </span>
          </div>

          {/* Transcript Messages Body */}
          <div className="flex-1 overflow-y-auto p-6 space-y-4">
            {messages.map((msg) => (
              <div
                key={msg.id}
                className={`flex gap-3 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                {msg.role === 'assistant' && (
                  <div className="w-8 h-8 rounded-full bg-teal-500/20 border border-teal-500/30 flex items-center justify-center shrink-0 text-teal-300 font-bold text-xs">
                    CD
                  </div>
                )}

                <div className={`space-y-2 max-w-[85%] ${msg.role === 'user' ? 'items-end' : 'items-start'}`}>
                  <div
                    className={`rounded-2xl px-4 py-3 text-sm leading-relaxed ${
                      msg.role === 'user'
                        ? 'bg-teal-500 text-navy-950 font-medium rounded-tr-none'
                        : 'bg-navy-800 text-slate-200 border border-navy-750 rounded-tl-none whitespace-pre-wrap'
                    }`}
                  >
                    {msg.content}
                  </div>

                  {/* Render Pending Action Confirmation Card if attached to message */}
                  {msg.pending_action && (
                    <ConfirmationCard
                      pendingAction={msg.pending_action}
                      onConfirm={handleConfirmAction}
                      isSubmitting={isConfirmingAction}
                    />
                  )}

                  <div className={`text-[10px] text-slate-400 px-1 ${msg.role === 'user' ? 'text-right' : 'text-left'}`}>
                    {new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                  </div>
                </div>

                {msg.role === 'user' && (
                  <div className="w-8 h-8 rounded-full bg-navy-800 border border-navy-700 flex items-center justify-center shrink-0 text-slate-300 font-bold text-xs">
                    <User className="w-4 h-4" />
                  </div>
                )}
              </div>
            ))}

            {/* Render Standalone Pending Action Confirmation Card if active and not attached to a specific message */}
            {activePendingAction && !messages.some((m) => m.pending_action?.action_id === activePendingAction.action_id) && (
              <div className="pt-2">
                <ConfirmationCard
                  pendingAction={activePendingAction}
                  onConfirm={handleConfirmAction}
                  isSubmitting={isConfirmingAction}
                />
              </div>
            )}

            {isLoading && (
              <div className="flex gap-3 items-center text-xs text-slate-400 animate-pulse">
                <div className="w-8 h-8 rounded-full bg-teal-500/10 border border-teal-500/20 flex items-center justify-center">
                  <RefreshCw className="w-4 h-4 animate-spin text-teal-400" />
                </div>
                <span>CareBridge Receptionist is processing your request...</span>
              </div>
            )}

            <div ref={transcriptEndRef} />
          </div>

          {/* Text Input Footer (Available in both modes for accessibility & quick corrections) */}
          <div className="p-4 bg-navy-850 border-t border-navy-800">
            <form
              onSubmit={(e) => {
                e.preventDefault();
                if (inputValue.trim()) {
                  void handleUserSubmission(inputValue);
                }
              }}
              className="flex items-center gap-2"
            >
              <input
                type="text"
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                placeholder={
                  mode === 'voice'
                    ? 'Type here to speak or clarify any detail...'
                    : 'Ask about doctors, hours, or schedule appointments...'
                }
                disabled={isLoading}
                className="flex-1 bg-navy-900 border border-navy-750 rounded-xl px-4 py-2.5 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-teal-500 focus:ring-1 focus:ring-teal-500 transition-all"
              />
              <button
                type="submit"
                disabled={isLoading || !inputValue.trim()}
                className="flex items-center gap-1.5 px-4 py-2.5 rounded-xl bg-teal-500 text-navy-950 font-bold hover:bg-teal-400 disabled:opacity-40 transition-all shadow-md shadow-teal-500/20 text-xs"
                title="Send message"
              >
                <Send className="w-3.5 h-3.5" />
                <span>Send</span>
              </button>
            </form>
          </div>

        </div>

      </div>

    </div>
  );
};
