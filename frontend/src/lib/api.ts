import axios from 'axios';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

const api = axios.create({ baseURL: API_BASE });

export const environmentApi = {
  list: () => api.get('/api/environments'),
  get: (id: number) => api.get(`/api/environments/${id}`),
  create: (data: any) => api.post('/api/environments', data),
  update: (id: number, data: any) => api.put(`/api/environments/${id}`, data),
  delete: (id: number) => api.delete(`/api/environments/${id}`),
  createPreset: (data: any) => api.post('/api/environments/preset', data),
  saveMap: (id: number) => api.post(`/api/environments/${id}/save-map`),
  loadMap: (filepath: string) => api.post(`/api/environments/load-map?filepath=${encodeURIComponent(filepath)}`),
};

export const experimentApi = {
  list: () => api.get('/api/experiments'),
  get: (id: number) => api.get(`/api/experiments/${id}`),
  create: (data: any) => api.post('/api/experiments', data),
  start: (id: number) => api.post(`/api/experiments/${id}/start`),
  pause: (id: number) => api.post(`/api/experiments/${id}/pause`),
  resume: (id: number) => api.post(`/api/experiments/${id}/resume`),
  stop: (id: number) => api.post(`/api/experiments/${id}/stop`),
  getLogs: (id: number, skip = 0, limit = 100) => api.get(`/api/experiments/${id}/logs?skip=${skip}&limit=${limit}`),
  getProgress: (id: number) => api.get(`/api/experiments/${id}/progress`),
  getCheckpoints: (id: number) => api.get(`/api/experiments/${id}/checkpoints`),
};

export const evaluationApi = {
  create: (data: any) => api.post('/api/evaluations', data),
  list: () => api.get('/api/evaluations'),
  get: (id: number) => api.get(`/api/evaluations/${id}`),
  getReplay: (id: number, episodeIdx: number) => api.get(`/api/evaluations/${id}/replay/${episodeIdx}`),
};

export const visualizationApi = {
  getTrajectoryHeatmap: (expId: number) => api.get(`/api/visualization/${expId}/trajectory-heatmap`),
  getQValueMap: (expId: number, agentId: number = 0) => api.get(`/api/visualization/${expId}/q-value-map?agent_id=${agentId}`),
  getLearningCurves: (expId: number) => api.get(`/api/visualization/${expId}/learning-curves`),
  compareCurves: (expIds: number[]) => api.get(`/api/visualization/compare-curves?exp_ids=${expIds.join(',')}`),
};

export const reportApi = {
  createComparison: (expIds: number[]) => api.post('/api/reports/comparison', { experiment_ids: expIds }),
  exportPdf: (expIds: number[]) => api.post('/api/reports/export-pdf', { experiment_ids: expIds }, { responseType: 'blob' }),
};

export const algorithmApi = {
  list: () => api.get('/api/algorithms'),
};

export default api;
