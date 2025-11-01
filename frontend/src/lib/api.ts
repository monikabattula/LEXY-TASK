import axios from 'axios';

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000';

const apiClient = axios.create({
  baseURL: API_BASE,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Documents API
export const documentsApi = {
  upload: async (file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    const response = await apiClient.post('/v1/documents/upload', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  },

  get: async (documentId: string) => {
    const response = await apiClient.get(`/v1/documents/${documentId}`);
    return response.data;
  },

  getPlaceholders: async (documentId: string) => {
    const response = await apiClient.get(`/v1/documents/${documentId}/placeholders`);
    return response.data;
  },

  render: async (documentId: string, sessionId: string) => {
    const response = await apiClient.post(`/v1/documents/${documentId}/render`, null, {
      params: { session_id: sessionId },
    });
    return response.data;
  },

  download: (documentId: string, fileType: string = 'docx') => {
    return `${API_BASE}/v1/documents/${documentId}/download?file_type=${fileType}`;
  },

  getPreviewUrl: async (documentId: string) => {
    const response = await apiClient.get(`/v1/documents/${documentId}/preview`);
    return response.data;
  },

  getLivePreviewUrl: (documentId: string, sessionId: string) => {
    return `${API_BASE}/v1/documents/${documentId}/live-preview?session_id=${sessionId}`;
  },
};

// Sessions API
export const sessionsApi = {
  create: async (documentId: string) => {
    const response = await apiClient.post('/v1/sessions', { document_id: documentId });
    return response.data;
  },

  get: async (sessionId: string) => {
    const response = await apiClient.get(`/v1/sessions/${sessionId}`);
    return response.data;
  },

  chat: async (sessionId: string, message: string) => {
    const response = await apiClient.post(`/v1/sessions/${sessionId}/chat`, { message });
    return response.data;
  },
};

