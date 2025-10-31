import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { documentsApi } from '@/lib/api';
import { useQuery, useMutation } from '@tanstack/react-query';

export default function PreviewPage() {
  const { documentId } = useParams<{ documentId: string }>();
  const navigate = useNavigate();
  const [sessionId, setSessionId] = useState<string | null>(null);

  // Get session from localStorage or create new
  useEffect(() => {
    if (documentId) {
      const stored = localStorage.getItem(`session_${documentId}`);
      if (stored) {
        setSessionId(stored);
      }
    }
  }, [documentId]);

  const { data: document } = useQuery({
    queryKey: ['document', documentId],
    queryFn: () => documentsApi.get(documentId!),
    enabled: !!documentId,
  });

  const renderMutation = useMutation({
    mutationFn: ({ documentId, sessionId }: { documentId: string; sessionId: string }) =>
      documentsApi.render(documentId, sessionId),
  });

  const { data: previewInfo } = useQuery({
    queryKey: ['preview', documentId],
    queryFn: () => documentsApi.getPreviewUrl(documentId!),
    enabled: !!documentId && renderMutation.isSuccess,
    refetchInterval: 2000,
  });

  const handleRender = () => {
    if (!documentId || !sessionId) return;
    renderMutation.mutate({ documentId, sessionId });
  };

  const downloadUrl = documentId ? documentsApi.download(documentId, 'docx') : '';
  const previewUrl = previewInfo?.preview_url
    ? `${import.meta.env.VITE_API_BASE}${previewInfo.preview_url}`
    : null;

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 dark">
      <div className="max-w-5xl mx-auto px-6 py-10">
        <div className="bg-slate-800/90 backdrop-blur-lg rounded-2xl shadow-2xl border border-slate-700/50 overflow-hidden">
          {/* Header */}
          <div className="bg-gradient-to-r from-blue-500 via-indigo-500 to-purple-500 px-8 py-6">
            <div className="flex items-center gap-4">
              <div className="w-14 h-14 bg-white/20 backdrop-blur-sm rounded-xl flex items-center justify-center">
                <svg className="w-8 h-8 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </div>
              <div>
                <h1 className="text-3xl font-bold text-white mb-1">Document Ready</h1>
                <p className="text-blue-100 text-sm">Your document has been filled successfully</p>
              </div>
            </div>
          </div>

          <div className="p-8">
            {document && (
              <div className="mb-8 p-5 bg-gradient-to-r from-slate-700/50 to-slate-800/50 rounded-xl border border-slate-600">
                <div className="flex items-start gap-3">
                  <div className="w-10 h-10 bg-blue-900/50 border border-blue-700/30 rounded-lg flex items-center justify-center flex-shrink-0">
                    <svg className="w-5 h-5 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                    </svg>
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-slate-400 mb-1">File Name</p>
                    <p className="text-slate-100 font-medium truncate">{document.filename}</p>
                    <div className="mt-2 flex items-center gap-2">
                      <span className="px-3 py-1 bg-green-900/50 text-green-300 border border-green-700/30 rounded-full text-xs font-medium">
                        {document.status}
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {!renderMutation.isSuccess && (
              <div className="mb-8">
                <button
                  onClick={handleRender}
                  disabled={!sessionId || renderMutation.isPending}
                  className={`px-8 py-4 rounded-xl font-semibold text-white transition-all duration-200 shadow-lg hover:shadow-xl flex items-center gap-3 ${
                    renderMutation.isPending || !sessionId
                      ? 'bg-slate-600 cursor-not-allowed shadow-none'
                      : 'bg-gradient-to-r from-blue-500 to-indigo-600 hover:from-blue-600 hover:to-indigo-700'
                  }`}
                >
                  {renderMutation.isPending ? (
                    <>
                      <svg className="animate-spin h-5 w-5" fill="none" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                      </svg>
                      Generating...
                    </>
                  ) : (
                    <>
                      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
                      </svg>
                      Generate Filled Document
                    </>
                  )}
                </button>
                {renderMutation.isError && (
                  <div className="mt-4 p-4 bg-red-900/30 border-l-4 border-red-500 rounded-lg">
                    <p className="text-red-300 font-medium">
                      {(renderMutation.error as any)?.response?.data?.detail || 'Rendering failed. Please try again.'}
                    </p>
                  </div>
                )}
              </div>
            )}

            {renderMutation.isSuccess && (
              <div className="space-y-6">
                <div className="p-5 bg-gradient-to-r from-green-900/30 to-emerald-900/30 border-l-4 border-green-500 rounded-xl">
                  <div className="flex items-center gap-3">
                    <svg className="w-6 h-6 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    <p className="text-green-300 font-semibold text-lg">Document rendered successfully!</p>
                  </div>
                </div>

                <div className="grid sm:grid-cols-2 gap-4">
                  <a
                    href={downloadUrl}
                    download
                    className="group px-6 py-4 bg-gradient-to-r from-blue-500 to-indigo-600 text-white rounded-xl hover:from-blue-600 hover:to-indigo-700 transition-all duration-200 text-center font-semibold shadow-lg hover:shadow-xl flex items-center justify-center gap-3"
                  >
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                    </svg>
                    Download .docx
                  </a>

                  {previewUrl && (
                    <a
                      href={previewUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="px-6 py-4 bg-slate-700 border-2 border-slate-600 text-slate-200 rounded-xl hover:border-slate-500 hover:bg-slate-600 transition-all duration-200 text-center font-semibold shadow-md hover:shadow-lg flex items-center justify-center gap-3"
                    >
                      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                      </svg>
                      Preview HTML
                    </a>
                  )}
                </div>

                {previewUrl && (
                  <div className="mt-6 rounded-xl overflow-hidden border-2 border-slate-700 shadow-lg bg-slate-900">
                    <div className="bg-slate-800 px-4 py-2 border-b border-slate-700 flex items-center gap-2">
                      <div className="w-3 h-3 rounded-full bg-red-500"></div>
                      <div className="w-3 h-3 rounded-full bg-yellow-500"></div>
                      <div className="w-3 h-3 rounded-full bg-green-500"></div>
                      <span className="ml-2 text-xs text-slate-400 font-medium">Document Preview</span>
                    </div>
                    <iframe
                      src={previewUrl}
                      className="w-full h-[600px] border-0 bg-white"
                      title="Document Preview"
                    />
                  </div>
                )}
              </div>
            )}

            <div className="mt-10 pt-6 border-t border-slate-700">
              <button
                onClick={() => navigate('/')}
                className="inline-flex items-center gap-2 text-blue-400 hover:text-blue-300 font-medium transition-colors duration-200 hover:bg-slate-700/50 px-4 py-2 rounded-lg"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
                </svg>
                Upload Another Document
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

