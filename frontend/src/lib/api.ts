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
  getLogs: (id: number, offset = 0, limit = 100, minEpisode?: number, maxEpisode?: number) => {
    let url = `/api/experiments/${id}/logs?offset=${offset}&limit=${limit}`;
    if (minEpisode !== undefined) url += `&min_episode=${minEpisode}`;
    if (maxEpisode !== undefined) url += `&max_episode=${maxEpisode}`;
    return api.get(url);
  },
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
  getLearningCurves: (expId: number, offset = 0, limit = 0) => {
    let url = `/api/visualization/${expId}/learning-curves?offset=${offset}`;
    if (limit > 0) url += `&limit=${limit}`;
    return api.get(url);
  },
  compareCurves: (expIds: number[]) => api.get(`/api/visualization/compare-curves?exp_ids=${expIds.join(',')}`),
};

export const reportApi = {
  createComparison: (expIds: number[]) => api.post('/api/reports/comparison', { experiment_ids: expIds }),
  exportPdf: (expIds: number[]) => api.post('/api/reports/export-pdf', { experiment_ids: expIds }, { responseType: 'blob' }),
};

export const algorithmApi = {
  list: () => api.get('/api/algorithms'),
};

export const policyApi = {
  list: () => api.get('/api/policies'),
  listGrouped: () => api.get('/api/policies/grouped'),
  get: (id: number) => api.get(`/api/policies/${id}`),
  create: (data: any) => api.post('/api/policies', data),
  start: (id: number) => api.post(`/api/policies/${id}/start`),
  stop: (id: number) => api.post(`/api/policies/${id}/stop`),
  delete: (id: number) => api.delete(`/api/policies/${id}`),
  infer: (id: number, data: any) => api.post(`/api/policies/${id}/infer`, data),
  getLogs: (id: number, offset = 0, limit = 50, startTime?: string, endTime?: string) => {
    let url = `/api/policies/${id}/logs?offset=${offset}&limit=${limit}`;
    if (startTime) url += `&start_time=${encodeURIComponent(startTime)}`;
    if (endTime) url += `&end_time=${encodeURIComponent(endTime)}`;
    return api.get(url);
  },
  getStats: (id: number) => api.get(`/api/policies/${id}/stats`),
  getResourceStats: (id: number) => api.get(`/api/policies/${id}/resource-stats`),
  abTest: (data: any) => api.post('/api/policies/ab-test', data),
};

export const templateApi = {
  list: (params?: { tags?: string; keyword?: string }) => {
    let url = '/api/templates';
    const qs: string[] = [];
    if (params?.tags) qs.push(`tags=${encodeURIComponent(params.tags)}`);
    if (params?.keyword) qs.push(`keyword=${encodeURIComponent(params.keyword)}`);
    if (qs.length) url += `?${qs.join('&')}`;
    return api.get(url);
  },
  get: (id: number) => api.get(`/api/templates/${id}`),
  getVersions: (id: number) => api.get(`/api/templates/${id}/versions`),
  create: (data: any) => api.post('/api/templates', data),
  update: (id: number, data: any) => api.put(`/api/templates/${id}`, data),
  rollback: (templateId: number, versionId: number) => api.post(`/api/templates/${templateId}/rollback`, { template_id: templateId, version_id: versionId }),
  delete: (id: number) => api.delete(`/api/templates/${id}`),
  createFromExperiment: (data: any) => api.post('/api/templates/from-experiment', data),
};

export const batchRunApi = {
  list: () => api.get('/api/batch-runs'),
  get: (id: number) => api.get(`/api/batch-runs/${id}`),
  create: (data: any) => api.post('/api/batch-runs', data),
  start: (id: number) => api.post(`/api/batch-runs/${id}/start`),
  resume: (id: number) => api.post(`/api/batch-runs/${id}/resume`),
  cancel: (id: number) => api.post(`/api/batch-runs/${id}/cancel`),
  getStats: (id: number, heatmapVarA?: string, heatmapVarB?: string) => {
    let url = `/api/batch-runs/${id}/stats`;
    const qs: string[] = [];
    if (heatmapVarA) qs.push(`heatmap_var_a=${encodeURIComponent(heatmapVarA)}`);
    if (heatmapVarB) qs.push(`heatmap_var_b=${encodeURIComponent(heatmapVarB)}`);
    if (qs.length) url += `?${qs.join('&')}`;
    return api.get(url);
  },
  preview: (templateId: number, maxParallel: number = 1) => api.post('/api/batch-runs/preview', { template_id: templateId, max_parallel: maxParallel }),
  listByTemplate: (templateId: number) => api.get(`/api/batch-runs/template/${templateId}`),
};

export default api;
