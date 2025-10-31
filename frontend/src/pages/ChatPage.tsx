import { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { documentsApi, sessionsApi } from '@/lib/api';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

interface Message {
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
}

export default function ChatPage() {
  const { documentId } = useParams<{ documentId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [initialMessageSent, setInitialMessageSent] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Create or get session
  const { data: session } = useQuery({
    queryKey: ['session', documentId],
    queryFn: async () => {
      if (!documentId) return null;
      try {
        // Check if session exists in localStorage
        const stored = localStorage.getItem(`session_${documentId}`);
        if (stored) {
          setSessionId(stored);
          return { session_id: stored };
        }
        // Create new session
        const result = await sessionsApi.create(documentId);
        setSessionId(result.session_id);
        localStorage.setItem(`session_${documentId}`, result.session_id);
        return result;
      } catch (err) {
        console.error('Failed to create session:', err);
        return null;
      }
    },
    enabled: !!documentId,
  });

  // Get placeholders
  const { data: placeholders } = useQuery({
    queryKey: ['placeholders', documentId],
    queryFn: () => documentsApi.getPlaceholders(documentId!),
    enabled: !!documentId,
    refetchInterval: 2000, // Poll for placeholders while parsing
  });

  // Chat mutation
  const chatMutation = useMutation({
    mutationFn: ({ sessionId, message }: { sessionId: string; message: string }) =>
      sessionsApi.chat(sessionId, message),
    onSuccess: (data) => {
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: data.assistant,
          timestamp: new Date(),
        },
      ]);
      // Preview updates automatically via iframe - no need to navigate
    },
  });

  useEffect(() => {
    if (session?.session_id && placeholders && placeholders.length > 0 && !initialMessageSent && sessionId) {
      setInitialMessageSent(true);
      // Send initial greeting via API to get first question
      sessionsApi.chat(sessionId, "Hello").then((data) => {
        setMessages([
          {
            role: 'assistant',
            content: data.assistant,
            timestamp: new Date(),
          },
        ]);
      }).catch(console.error);
    }
  }, [session, placeholders, initialMessageSent, sessionId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Calculate progress and preview URL before useEffects that use them
  const progress = chatMutation.data?.progress || { filled: 0, total: placeholders?.length || 0 };
  const progressPercentage = progress.total > 0 ? Math.round((progress.filled / progress.total) * 100) : 0;

  // Live preview URL - updates as fields are filled
  const previewUrl = documentId && sessionId 
    ? documentsApi.getLivePreviewUrl(documentId, sessionId)
    : null;

  // Refresh preview when progress changes (when a field is filled)
  useEffect(() => {
    // Force iframe refresh by updating key when progress changes
    if (previewUrl && progress.filled > 0) {
      // The iframe key will cause it to reload
    }
  }, [progress.filled, previewUrl]);

  const handleSend = async () => {
    if (!input.trim() || !sessionId) return;

    const userMessage: Message = {
      role: 'user',
      content: input,
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput('');

    chatMutation.mutate({ sessionId, message: input });
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="min-h-screen bg-[#f5f5f7] dark:bg-[#000000] flex flex-col transition-colors duration-300">
      {/* Header */}
      <div className="bg-white/80 dark:bg-[#1c1c1e]/80 backdrop-blur-xl border-b border-gray-200/50 dark:border-white/5 sticky top-0 z-10 shadow-sm">
        <div className="w-full px-8 py-5">
          <div className="flex items-center justify-between max-w-[1920px] mx-auto">
            <div className="flex items-center gap-4">
              <button
                onClick={() => navigate('/')}
                className="p-2 text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-white/10 rounded-xl transition-all duration-200 flex items-center gap-2 group"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 19.5L8.25 12l7.5-7.5" />
                </svg>
                <span className="text-sm font-medium hidden sm:inline">Back</span>
              </button>
              <div className="h-px w-6 bg-gray-200 dark:bg-white/10 hidden sm:block" />
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 bg-gradient-to-br from-blue-500 to-blue-600 rounded-2xl flex items-center justify-center shadow-sm">
                  <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
                  </svg>
                </div>
                <div>
                  <h1 className="text-lg font-semibold text-gray-900 dark:text-white">
                    Document Assistant
                  </h1>
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5 font-medium">
                    {placeholders ? `${progress.filled} of ${progress.total} fields completed` : 'Analyzing document...'}
                  </p>
                </div>
              </div>
            </div>
            
            <div className="flex items-center gap-4">
              {/* Progress Bar */}
              {placeholders && progress.total > 0 && (
                <div className="hidden md:flex items-center gap-3">
                  <div className="flex items-center gap-2">
                    <div className="w-32 bg-gray-200 dark:bg-white/10 rounded-full h-1.5 overflow-hidden">
                      <div
                        className="bg-blue-500 h-1.5 rounded-full transition-all duration-700 ease-out shadow-sm"
                        style={{ width: `${progressPercentage}%` }}
                      />
                    </div>
                    <span className="text-xs font-semibold text-gray-600 dark:text-gray-300 tabular-nums w-10">{progressPercentage}%</span>
                  </div>
                </div>
              )}
              
              {/* Download Button */}
              {progress.filled > 0 && documentId && sessionId && (
                <button
                  onClick={async () => {
                    try {
                      await documentsApi.render(documentId, sessionId);
                      setTimeout(() => {
                        const downloadUrl = documentsApi.download(documentId, 'docx');
                        const link = document.createElement('a');
                        link.href = downloadUrl;
                        link.download = '';
                        document.body.appendChild(link);
                        link.click();
                        document.body.removeChild(link);
                      }, 500);
                    } catch (err: any) {
                      console.error('Download failed:', err);
                      alert(err?.response?.data?.detail || 'Failed to download document. Please try again.');
                    }
                  }}
                  className="px-5 py-2.5 bg-blue-500 hover:bg-blue-600 text-white rounded-xl transition-all duration-200 font-medium text-sm shadow-sm hover:shadow-md active:scale-[0.98] flex items-center gap-2"
                  title={progress.filled < progress.total ? `Download document with ${progress.filled} of ${progress.total} fields filled` : 'Download completed document'}
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12L12 16.5m0 0L7.5 12m4.5 4.5V3" />
                  </svg>
                  {progress.filled < progress.total ? `${progress.filled}/${progress.total}` : 'Download'}
                </button>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Split Screen: Chat Left, Preview Right */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left: Chat Panel */}
        <div className="flex-1 flex flex-col border-r border-gray-200/50 dark:border-white/5 bg-white dark:bg-[#1c1c1e]">
          {/* Chat Messages */}
          <div className="flex-1 overflow-y-auto px-8 py-8">
            <div className="max-w-3xl mx-auto space-y-6">
              {messages.length === 0 && (
                <div className="text-center py-16">
                  <div className="inline-flex items-center justify-center w-20 h-20 rounded-3xl bg-blue-50 dark:bg-blue-500/10 mb-6">
                    <svg className="w-10 h-10 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.5}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M8.625 12a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H8.25m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H12m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0h-.375M21 12c0 4.556-4.03 8.25-9 8.25a9.764 9.764 0 01-2.555-.337L5.26 21l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.556 4.03-8.25 9-8.25s9 3.694 9 8.25z" />
                    </svg>
                  </div>
                  <p className="text-gray-600 dark:text-gray-400 text-lg font-medium">Start by answering the assistant's questions</p>
                </div>
              )}
              
              {messages.map((msg, idx) => (
                <div
                  key={idx}
                  className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'} items-start gap-3 animate-in fade-in slide-in-from-bottom-2 duration-300`}
                >
                  {msg.role === 'assistant' && (
                    <div className="w-8 h-8 rounded-2xl bg-blue-500 flex items-center justify-center flex-shrink-0 shadow-sm">
                      <svg className="w-4 h-4 text-white" fill="currentColor" viewBox="0 0 20 20">
                        <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-6-3a2 2 0 11-4 0 2 2 0 014 0zm-2 4a5 5 0 00-4.546 2.916A5.986 5.986 0 0010 16a5.986 5.986 0 004.546-2.084A5 5 0 0010 11z" clipRule="evenodd" />
                      </svg>
                    </div>
                  )}
                  
                  <div
                    className={`max-w-[75%] rounded-3xl px-5 py-3.5 shadow-sm ${
                      msg.role === 'user'
                        ? 'bg-blue-500 text-white'
                        : 'bg-gray-100 dark:bg-white/5 text-gray-900 dark:text-white'
                    }`}
                  >
                    <p className="text-[15px] leading-relaxed whitespace-pre-wrap font-medium">{msg.content}</p>
                  </div>
                  
                  {msg.role === 'user' && (
                    <div className="w-8 h-8 rounded-2xl bg-gray-300 dark:bg-gray-600 flex items-center justify-center flex-shrink-0">
                      <svg className="w-4 h-4 text-gray-600 dark:text-gray-300" fill="currentColor" viewBox="0 0 20 20">
                        <path fillRule="evenodd" d="M10 9a3 3 0 100-6 3 3 0 000 6zm-7 9a7 7 0 1114 0H3z" clipRule="evenodd" />
                      </svg>
                    </div>
                  )}
                </div>
              ))}
              
              {chatMutation.isPending && (
                <div className="flex justify-start items-start gap-3">
                  <div className="w-8 h-8 rounded-2xl bg-blue-500 flex items-center justify-center flex-shrink-0 shadow-sm">
                    <svg className="w-4 h-4 text-white" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-6-3a2 2 0 11-4 0 2 2 0 014 0zm-2 4a5 5 0 00-4.546 2.916A5.986 5.986 0 0010 16a5.986 5.986 0 004.546-2.084A5 5 0 0010 11z" clipRule="evenodd" />
                    </svg>
                  </div>
                  <div className="bg-gray-100 dark:bg-white/5 rounded-3xl px-5 py-3.5 shadow-sm">
                    <div className="flex space-x-1.5">
                      <div className="w-1.5 h-1.5 bg-blue-500 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                      <div className="w-1.5 h-1.5 bg-blue-500 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                      <div className="w-1.5 h-1.5 bg-blue-500 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                    </div>
                  </div>
                </div>
              )}
              
              <div ref={messagesEndRef} />
            </div>
          </div>

          {/* Input Area */}
          <div className="bg-white/80 dark:bg-[#1c1c1e]/80 backdrop-blur-xl border-t border-gray-200/50 dark:border-white/5">
            <div className="max-w-3xl mx-auto px-8 py-5">
              <div className="flex gap-3">
                <input
                  type="text"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyPress={handleKeyPress}
                  placeholder={sessionId ? "Type your answer..." : "Waiting for session..."}
                  disabled={!sessionId || chatMutation.isPending}
                  className="flex-1 px-5 py-3.5 bg-gray-100 dark:bg-white/5 border-0 rounded-2xl focus:outline-none focus:ring-2 focus:ring-blue-500/50 disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-200 text-[15px] placeholder:text-gray-400 dark:placeholder:text-gray-500 text-gray-900 dark:text-white font-medium"
                />
                <button
                  onClick={handleSend}
                  disabled={!sessionId || !input.trim() || chatMutation.isPending}
                  className="px-6 py-3.5 bg-blue-500 hover:bg-blue-600 text-white rounded-2xl disabled:bg-gray-300 dark:disabled:bg-gray-700 disabled:cursor-not-allowed transition-all duration-200 font-medium shadow-sm hover:shadow-md active:scale-[0.98] disabled:active:scale-100 flex items-center gap-2"
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M6 12L3.269 3.126A59.768 59.768 0 0121.485 12 59.77 59.77 0 013.27 20.876L5.999 12zm0 0h7.5" />
                  </svg>
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* Right: Document Preview */}
        <div className="flex-1 bg-gray-50 dark:bg-[#000000] flex flex-col border-l border-gray-200/50 dark:border-white/5">
          <div className="bg-white/80 dark:bg-[#1c1c1e]/80 backdrop-blur-xl border-b border-gray-200/50 dark:border-white/5 px-6 py-4">
            <h2 className="text-sm font-semibold text-gray-900 dark:text-white">Document Preview</h2>
          </div>
          <div className="flex-1 overflow-auto bg-white">
            {previewUrl ? (
              <iframe
                key={`preview-${sessionId}-${progress.filled}`}
                src={`${previewUrl}&_t=${progress.filled}`}
                className="w-full h-full border-0"
                title="Live Document Preview"
              />
            ) : (
              <div className="flex items-center justify-center h-full">
                <div className="text-center">
                  <div className="inline-flex items-center justify-center w-16 h-16 rounded-3xl bg-gray-100 dark:bg-white/5 mb-4">
                    <svg className="w-8 h-8 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.5}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
                    </svg>
                  </div>
                  <p className="text-gray-500 dark:text-gray-400 font-medium">Preview will appear here</p>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

