import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, Phone, Clock, TrendingUp, MessageSquare } from 'lucide-react';
import DashboardLayout from '../components/dashboard/DashboardLayout';
import { API_BASE_URL } from '../config';

interface CallData {
  id: string;
  to_number: string;
  from_number: string;
  status: string;
  duration: number;
  created_at: string;
  direction: string;
}

interface Analysis {
  summary: string;
  outcome: string;
  confidence_score: number;
  sentiment: string;
  key_points: string[];
  next_action: string;
}

interface Transcript {
  speaker: string;
  text: string;
  timestamp: string;
}

export default function CallDetails() {
  const { callId } = useParams();
  const navigate = useNavigate();
  const [call, setCall] = useState<CallData | null>(null);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [transcripts, setTranscripts] = useState<Transcript[]>([]);
  const [loading, setLoading] = useState(true);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);

  useEffect(() => {
    if (callId) {
      fetchCallDetails();
    }
    // Cleanup blob URL on unmount
    return () => {
      if (audioUrl) {
        URL.revokeObjectURL(audioUrl);
      }
    };
  }, [callId]);

  async function fetchCallDetails() {
    try {
      const token = localStorage.getItem('relayx_token');
      const headers: HeadersInit = {
        'Content-Type': 'application/json'
      };
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }

      // 1. Fetch Call Data
      const callRes = await fetch(`${API_BASE_URL}/calls/${callId}`, { headers });
      if (!callRes.ok) throw new Error(`Failed to fetch call: ${callRes.status}`);
      const callData = await callRes.json();
      setCall(callData);

      // 2. Fetch Analysis
      try {
        const analysisRes = await fetch(`${API_BASE_URL}/calls/${callId}/analysis`, { headers });
        if (analysisRes.ok) {
          const analysisData = await analysisRes.json();
          if (analysisData && analysisData.summary) {
            setAnalysis(analysisData);
          }
        }
      } catch (e) {
        console.log('Analysis load error:', e);
      }

      // 3. Fetch Transcripts
      try {
        const transcriptRes = await fetch(`${API_BASE_URL}/calls/${callId}/transcripts`, { headers });
        if (transcriptRes.ok) {
          const transcriptData = await transcriptRes.json();
          setTranscripts(transcriptData || []);
        }
      } catch (e) {
        console.log('Transcript load error:', e);
      }

      // 4. Fetch Recording (via Blob to handle Auth)
      try {
        // Use the new proxy endpoint we just created
        const audioRes = await fetch(`${API_BASE_URL}/calls/${callId}/recording`, { headers });
        if (audioRes.ok) {
          const blob = await audioRes.blob();
          const objUrl = URL.createObjectURL(blob);
          setAudioUrl(objUrl);
        } else {
          console.warn("Recording endpoint returned:", audioRes.status);
        }
      } catch (e) {
        console.log('Recording load error:', e);
      }

    } catch (error) {
      console.error('Failed to fetch call details:', error);
    } finally {
      setLoading(false);
    }
  }

  function getOutcomeBadge(outcome: string) {
    if (!outcome) return null;
    const isPositive = outcome.toLowerCase().includes('interested') || outcome.toLowerCase().includes('success');
    const isNegative = outcome.toLowerCase().includes('not') || outcome.toLowerCase().includes('declined');

    return (
      <span className={`inline-flex items-center px-3 py-1 rounded-full text-sm font-medium ${isPositive ? 'bg-green-900/30 text-green-300 border border-green-800' :
        isNegative ? 'bg-red-900/30 text-red-300 border border-red-800' :
          'bg-gray-800 text-gray-300 border border-gray-700'
        }`}>
        {outcome}
      </span>
    );
  }

  function formatDuration(seconds: number) {
    if (!seconds) return 'N/A';
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  }

  if (loading) {
    return (
      <DashboardLayout>
        <div className="animate-pulse space-y-4">
          <div className="h-8 bg-gray-800 rounded w-1/4"></div>
          <div className="h-64 bg-gray-800 rounded"></div>
        </div>
      </DashboardLayout>
    );
  }

  if (!call) {
    return (
      <DashboardLayout>
        <div className="text-center py-12">
          <p className="text-gray-400">Call not found</p>
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout>
      <div className="space-y-6">
        {/* Header */}
        <div className="flex items-center space-x-4">
          <button onClick={() => navigate('/dashboard')} className="p-2 hover:bg-white/5 rounded-lg text-gray-300 transition-colors">
            <ArrowLeft className="w-5 h-5" />
          </button>
          <div>
            <h1 className="text-3xl font-bold text-[#FAFAFA]">Call Details</h1>
            <p className="text-gray-400 mt-1">{call.to_number}</p>
          </div>
        </div>

        {/* Quick Stats Grid */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          {[
            { label: 'Duration', icon: Clock, color: 'text-blue-500', value: call.duration ? formatDuration(call.duration) : '--:--' },
            { label: 'Status', icon: Phone, color: 'text-green-500', value: call.status || 'Unknown', capitalize: true },
            { label: 'Confidence', icon: TrendingUp, color: 'text-purple-500', value: analysis?.confidence_score ? `${Math.round(analysis.confidence_score * 100)}%` : 'N/A' },
            { label: 'Sentiment', icon: MessageSquare, color: 'text-orange-500', value: analysis?.sentiment || 'N/A', capitalize: true }
          ].map((stat, i) => (
            <div key={i} className="bg-[#161616] rounded-xl border border-[#2A2A2A] p-5 shadow-sm">
              <div className="flex items-center space-x-2 mb-3">
                <stat.icon className={`w-5 h-5 ${stat.color}`} />
                <span className="text-sm font-medium text-gray-400">{stat.label}</span>
              </div>
              <p className={`text-2xl font-bold text-[#FAFAFA] ${stat.capitalize ? 'capitalize' : ''}`}>
                {stat.value}
              </p>
            </div>
          ))}
        </div>

        {/* Recording (Slim Bar) */}
        {audioUrl && (
          <div className="bg-[#161616] rounded-xl border border-[#2A2A2A] p-4 shadow-sm flex items-center space-x-4">
            <span className="text-sm font-bold text-gray-400 uppercase tracking-wider">Recording</span>
            <audio controls className="flex-1 h-8 outline-none" src={audioUrl}>
              Your browser does not support the audio element.
            </audio>
          </div>
        )}

        {/* Analysis Summary */}
        {analysis && (
          <div className="bg-[#161616] rounded-xl border border-[#2A2A2A] p-6 shadow-sm">
            <h2 className="text-xl font-bold mb-4 text-[#FAFAFA]">Call Summary</h2>
            <div className="space-y-6">
              <div>
                <h3 className="text-sm font-semibold mb-2 text-gray-400">Outcome</h3>
                {getOutcomeBadge(analysis.outcome)}
              </div>
              <div>
                <h3 className="text-sm font-semibold mb-2 text-gray-400">Summary</h3>
                <p className="leading-relaxed text-[#FAFAFA] text-sm">{analysis.summary}</p>
              </div>
              {analysis.key_points?.length > 0 && (
                <div>
                  <h3 className="text-sm font-semibold mb-2 text-gray-400">Key Points</h3>
                  <ul className="list-disc list-inside space-y-2">
                    {analysis.key_points.map((point, i) => (
                      <li key={i} className="text-[#FAFAFA] text-sm">{point}</li>
                    ))}
                  </ul>
                </div>
              )}
              {analysis.next_action && (
                <div>
                  <h3 className="text-sm font-semibold mb-2 text-gray-400">Recommended Next Step</h3>
                  <div className="bg-blue-900/20 p-4 rounded-lg border border-blue-900/50 text-blue-200 text-sm">
                    {analysis.next_action}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}



        {/* Transcript */}
        <div className="bg-[#161616] rounded-xl border border-[#2A2A2A] p-6 shadow-sm">
          <h2 className="text-xl font-bold mb-4 text-[#FAFAFA]">Conversation Transcript</h2>
          {transcripts.length === 0 ? (
            <p className="text-center py-8 text-gray-500 text-sm">No transcript available</p>
          ) : (
            <div className="space-y-4">
              {transcripts.map((transcript, i) => {
                const isAgent = transcript.speaker === 'agent';
                return (
                  <div key={i} className={`flex ${isAgent ? 'justify-end' : 'justify-start'}`}>
                    <div className={`max-w-[75%] rounded-2xl px-5 py-3 shadow-md ${isAgent
                      ? 'bg-blue-600 text-white rounded-br-none'
                      : 'bg-[#1F2937] border border-gray-700 text-gray-100 rounded-bl-none shadow-black/40'
                      }`}>
                      <div className="flex items-center space-x-2 mb-1">
                        <span className={`text-xs font-bold ${isAgent ? 'text-blue-100' : 'text-gray-400'}`}>
                          {isAgent ? 'Assistant' : 'Customer'}
                        </span>
                        <span className={`text-xs ${isAgent ? 'text-blue-200' : 'text-gray-500'}`}>
                          {new Date(transcript.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                        </span>
                      </div>
                      <p className={`text-sm leading-relaxed ${isAgent ? 'text-white' : 'text-gray-100'}`}>
                        {transcript.text}
                      </p>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </DashboardLayout>
  );
}
