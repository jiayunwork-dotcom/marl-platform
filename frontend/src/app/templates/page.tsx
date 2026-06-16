'use client';

import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  ExperimentTemplate,
  BatchRun,
  BatchRunPreview,
  BatchRunStats,
  ParallelCoordsItem,
  HeatmapData,
} from '@/types';
import { templateApi, batchRunApi, environmentApi, experimentApi } from '@/lib/api';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ScatterChart,
  Scatter,
  ZAxis,
  Cell,
} from 'recharts';

function formatDuration(seconds: number | null): string {
  if (!seconds) return '未知';
  if (seconds < 60) return `${Math.round(seconds)}秒`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}分钟`;
  const h = Math.floor(seconds / 3600);
  const m = Math.round((seconds % 3600) / 60);
  return `${h}小时${m}分钟`;
}

function SimpleParallelCoordinates({
  data,
}: {
  data: ParallelCoordsItem[];
}) {
  if (!data || data.length === 0) return null;

  const allKeys = Object.keys(data[0]).filter(
    (k) => !['is_best', 'experiment_id'].includes(k)
  );
  const numKeys = allKeys.length;

  const normalizedData = data.map((item) => {
    const norm: any = { ...item };
    allKeys.forEach((key) => {
      const values = data.map((d) => d[key]);
      const numericValues = values.filter((v) => typeof v === 'number');
      if (numericValues.length > 0) {
        const min = Math.min(...numericValues);
        const max = Math.max(...numericValues);
        const v = item[key];
        norm[key] =
          typeof v === 'number' && max !== min
            ? ((v - min) / (max - min)) * 100
            : typeof v === 'number'
            ? 50
            : 50;
      } else {
        norm[key] = 50;
      }
    });
    return norm;
  });

  return (
    <div className="card">
      <h4 className="font-semibold mb-3">平行坐标图（高亮最高 Reward）</h4>
      <div className="relative w-full" style={{ height: 300 }}>
        <svg width="100%" height="100%" viewBox="0 0 800 300" preserveAspectRatio="xMidYMid meet">
          {allKeys.map((key, idx) => {
            const x = 50 + (idx * 700) / (numKeys - 1 || 1);
            return (
              <g key={key}>
                <line x1={x} y1={20} x2={x} y2={260} stroke="#475569" strokeWidth={1} />
                <text x={x} y={15} textAnchor="middle" fill="#cbd5e1" fontSize={11}>
                  {key}
                </text>
                <text x={x} y={280} textAnchor="middle" fill="#94a3b8" fontSize={9}>
                  0
                </text>
                <text x={x} y={22} textAnchor="middle" fill="#94a3b8" fontSize={9}>
                  1
                </text>
              </g>
            );
          })}
          {normalizedData.map((item, idx) => {
            const color = item.is_best ? '#22c55e' : '#3b82f6';
            const opacity = item.is_best ? 1 : 0.35;
            const strokeWidth = item.is_best ? 3 : 1.5;
            const points: string[] = [];
            allKeys.forEach((key, i) => {
              const x = 50 + (i * 700) / (numKeys - 1 || 1);
              const y = 260 - (item[key] / 100) * 240;
              points.push(`${x},${y}`);
            });
            return (
              <polyline
                key={idx}
                points={points.join(' ')}
                fill="none"
                stroke={color}
                strokeWidth={strokeWidth}
                opacity={opacity}
              />
            );
          })}
        </svg>
      </div>
    </div>
  );
}

function HeatmapChart({ data }: { data: HeatmapData }) {
  if (!data || !data.matrix) return null;

  const allValues = data.matrix.flat().filter((v): v is number => v !== null);
  const minVal = allValues.length ? Math.min(...allValues) : 0;
  const maxVal = allValues.length ? Math.max(...allValues) : 1;

  const getColor = (val: number | null): string => {
    if (val === null) return '#334155';
    const t = maxVal !== minVal ? (val - minVal) / (maxVal - minVal) : 0.5;
    const r = Math.round(59 + (34 - 59) * t);
    const g = Math.round(130 + (197 - 130) * t);
    const b = Math.round(246 + (94 - 246) * t);
    return `rgb(${r}, ${g}, ${b})`;
  };

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-3">
        <h4 className="font-semibold">热力图（{data.var_a} × {data.var_b}）</h4>
        <div className="text-xs text-slate-400">
          颜色越深表示平均 Reward 越高
        </div>
      </div>
      <div className="overflow-auto">
        <table className="text-xs">
          <thead>
            <tr>
              <th className="p-2 text-slate-400 font-normal"></th>
              {data.b_values.map((bv, i) => (
                <th key={i} className="p-2 text-slate-300 font-normal text-center min-w-[60px]">
                  {bv}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.matrix.map((row, i) => (
              <tr key={i}>
                <td className="p-2 text-slate-300 font-normal text-right pr-3">
                  {data.a_values[i]}
                </td>
                {row.map((cell, j) => (
                  <td
                    key={j}
                    className="p-1 text-center min-w-[60px]"
                    style={{ backgroundColor: getColor(cell) }}
                  >
                    <span className="text-xs text-white drop-shadow">
                      {cell !== null ? cell.toFixed(2) : '-'}
                    </span>
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-2 text-xs text-slate-500">
        行: {data.var_a} | 列: {data.var_b}
      </div>
    </div>
  );
}

export default function TemplatesPage() {
  const [templates, setTemplates] = useState<ExperimentTemplate[]>([]);
  const [environments, setEnvironments] = useState<any[]>([]);
  const [selectedTemplate, setSelectedTemplate] = useState<ExperimentTemplate | null>(null);
  const [templateVersions, setTemplateVersions] = useState<ExperimentTemplate[]>([]);
  const [isCreating, setIsCreating] = useState(false);
  const [showBatchPreview, setShowBatchPreview] = useState(false);
  const [batchPreview, setBatchPreview] = useState<BatchRunPreview | null>(null);
  const [batchRuns, setBatchRuns] = useState<BatchRun[]>([]);
  const [selectedBatchRun, setSelectedBatchRun] = useState<BatchRun | null>(null);
  const [batchStats, setBatchStats] = useState<BatchRunStats | null>(null);
  const [newTemplateName, setNewTemplateName] = useState('');
  const [newTemplateDesc, setNewTemplateDesc] = useState('');
  const [newTemplateTags, setNewTemplateTags] = useState('');
  const [newBatchName, setNewBatchName] = useState('');
  const [paramVarKey, setParamVarKey] = useState('');
  const [paramVarValues, setParamVarValues] = useState('');
  const [searchKeyword, setSearchKeyword] = useState('');
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [maxParallel, setMaxParallel] = useState(1);
  const [heatmapVarA, setHeatmapVarA] = useState<string | null>(null);
  const [heatmapVarB, setHeatmapVarB] = useState<string | null>(null);

  const allTags = useMemo(() => {
    const tagSet = new Set<string>();
    templates.forEach((t) => (t.tags || []).forEach((tag) => tagSet.add(tag)));
    return Array.from(tagSet).sort();
  }, [templates]);

  const fetchTemplates = useCallback(async () => {
    try {
      const params: { tags?: string; keyword?: string } = {};
      if (selectedTags.length > 0) params.tags = selectedTags.join(',');
      if (searchKeyword) params.keyword = searchKeyword;
      const res = await templateApi.list(params);
      setTemplates(res.data);
    } catch (e) {
      console.error(e);
    }
  }, [searchKeyword, selectedTags]);

  const fetchEnvironments = useCallback(async () => {
    try {
      const res = await environmentApi.list();
      setEnvironments(res.data);
    } catch (e) {
      console.error(e);
    }
  }, []);

  useEffect(() => {
    fetchTemplates();
    fetchEnvironments();
  }, [fetchTemplates, fetchEnvironments]);

  const fetchBatchRuns = useCallback(async (templateId: number) => {
    try {
      const res = await batchRunApi.listByTemplate(templateId);
      setBatchRuns(res.data);
    } catch (e) {
      console.error(e);
    }
  }, []);

  const fetchTemplateVersions = useCallback(async (templateId: number) => {
    try {
      const res = await templateApi.getVersions(templateId);
      setTemplateVersions(res.data);
    } catch (e) {
      console.error(e);
    }
  }, []);

  useEffect(() => {
    if (selectedTemplate) {
      fetchBatchRuns(selectedTemplate.id);
      fetchTemplateVersions(selectedTemplate.id);
    }
  }, [selectedTemplate, fetchBatchRuns, fetchTemplateVersions]);

  const fetchBatchStats = useCallback(async (batchRunId: number) => {
    try {
      const res = await batchRunApi.getStats(batchRunId, heatmapVarA || undefined, heatmapVarB || undefined);
      setBatchStats(res.data);
    } catch (e) {
      console.error(e);
    }
  }, [heatmapVarA, heatmapVarB]);

  useEffect(() => {
    if (selectedBatchRun) {
      fetchBatchStats(selectedBatchRun.id);
      const interval = setInterval(() => fetchBatchStats(selectedBatchRun.id), 5000);
      return () => clearInterval(interval);
    }
  }, [selectedBatchRun, fetchBatchStats]);

  const handleCreateTemplate = async () => {
    if (!newTemplateName) return;
    try {
      const tags = newTemplateTags
        .split(',')
        .map((t) => t.trim())
        .filter((t) => t);
      await templateApi.create({
        name: newTemplateName,
        description: newTemplateDesc,
        tags,
        algorithm: 'IQL',
        hyperparams: {
          algorithm: 'IQL',
          learning_rate: 0.001,
          gamma: 0.99,
          epsilon_start: 1.0,
          epsilon_end: 0.05,
          epsilon_decay_steps: 50000,
          replay_buffer_size: 50000,
          batch_size: 32,
          target_update_freq: 200,
          qmix_hidden_dim: 64,
          mappo_clip: 0.2,
          mappo_gae_lambda: 0.95,
          communication_enabled: false,
          comm_dim: 8,
        },
        communication_enabled: false,
        environment_id: environments[0]?.id || 1,
        agent_count: 2,
        total_episodes: 1000,
        param_variables: {},
      });
      setIsCreating(false);
      setNewTemplateName('');
      setNewTemplateDesc('');
      setNewTemplateTags('');
      fetchTemplates();
    } catch (e) {
      console.error(e);
    }
  };

  const handleDeleteTemplate = async (id: number) => {
    if (!confirm('确定删除该模板及其所有版本？')) return;
    try {
      await templateApi.delete(id);
      if (selectedTemplate?.id === id) {
        setSelectedTemplate(null);
      }
      fetchTemplates();
    } catch (e) {
      console.error(e);
    }
  };

  const handleAddVariable = async () => {
    if (!selectedTemplate || !paramVarKey || !paramVarValues) return;
    try {
      const values = paramVarValues.split(',').map((v) => {
        const num = parseFloat(v.trim());
        return isNaN(num) ? v.trim() : num;
      });

      const newVariables = {
        ...selectedTemplate.param_variables,
        [paramVarKey]: values,
      };

      const res = await templateApi.update(selectedTemplate.id, {
        param_variables: newVariables,
      });
      setSelectedTemplate(res.data);
      setParamVarKey('');
      setParamVarValues('');
      fetchTemplates();
      fetchTemplateVersions(selectedTemplate.id);
    } catch (e) {
      console.error(e);
    }
  };

  const handleRemoveVariable = async (key: string) => {
    if (!selectedTemplate) return;
    try {
      const newVariables = { ...selectedTemplate.param_variables };
      delete newVariables[key];

      const res = await templateApi.update(selectedTemplate.id, {
        param_variables: newVariables,
      });
      setSelectedTemplate(res.data);
      fetchTemplates();
      fetchTemplateVersions(selectedTemplate.id);
    } catch (e) {
      console.error(e);
    }
  };

  const handleRollback = async (versionId: number) => {
    if (!selectedTemplate) return;
    if (!confirm(`确定回滚到版本？这将创建一个新版本`)) return;
    try {
      const res = await templateApi.rollback(selectedTemplate.id, versionId);
      setSelectedTemplate(res.data);
      fetchTemplates();
      fetchTemplateVersions(selectedTemplate.id);
      alert('已回滚到指定版本');
    } catch (e: any) {
      alert(e.response?.data?.detail || '回滚失败');
    }
  };

  const handlePreviewBatch = async () => {
    if (!selectedTemplate) return;
    try {
      const res = await batchRunApi.preview(selectedTemplate.id, maxParallel);
      setBatchPreview(res.data);
      setShowBatchPreview(true);
      setNewBatchName(`${selectedTemplate.name} - 批量运行`);
    } catch (e: any) {
      alert(e.response?.data?.detail || '预览失败');
    }
  };

  const handleCreateBatchRun = async () => {
    if (!selectedTemplate || !newBatchName) return;
    try {
      const res = await batchRunApi.create({
        template_id: selectedTemplate.id,
        name: newBatchName,
        max_parallel: maxParallel,
      });
      await batchRunApi.start(res.data.id);
      setShowBatchPreview(false);
      setBatchPreview(null);
      fetchBatchRuns(selectedTemplate.id);
      alert('批量运行已创建并开始执行');
    } catch (e: any) {
      alert(e.response?.data?.detail || '创建失败');
    }
  };

  const handleCancelBatchRun = async (id: number) => {
    if (!confirm('确定取消该批量运行？')) return;
    try {
      await batchRunApi.cancel(id);
      if (selectedTemplate) {
        fetchBatchRuns(selectedTemplate.id);
      }
      if (selectedBatchRun?.id === id) {
        fetchBatchStats(id);
      }
    } catch (e) {
      console.error(e);
    }
  };

  const handleResumeBatchRun = async (id: number) => {
    if (!confirm('确定恢复该批量运行？')) return;
    try {
      await batchRunApi.resume(id);
      if (selectedTemplate) {
        fetchBatchRuns(selectedTemplate.id);
      }
      if (selectedBatchRun?.id === id) {
        fetchBatchStats(id);
      }
      alert('批量运行已恢复');
    } catch (e: any) {
      alert(e.response?.data?.detail || '恢复失败');
    }
  };

  const isStale = (br: BatchRun) => {
    if (br.status !== 'running') return false;
    if (!br.last_progress_at) return true;
    const last = new Date(br.last_progress_at).getTime();
    const now = Date.now();
    return now - last > 5 * 60 * 1000;
  };

  const getEnvName = (envId: number) => {
    const env = environments.find((e) => e.id === envId);
    return env?.name || `环境 ${envId}`;
  };

  const statusColors: Record<string, string> = {
    pending: 'bg-yellow-600',
    running: 'bg-green-600',
    completed: 'bg-blue-600',
    failed: 'bg-red-600',
  };

  const toggleTag = (tag: string) => {
    setSelectedTags((prev) =>
      prev.includes(tag) ? prev.filter((t) => t !== tag) : [...prev, tag]
    );
  };

  return (
    <div className="flex gap-4 h-full">
      <div className="flex-1 overflow-y-auto">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-2xl font-bold">实验模板</h1>
          <button onClick={() => setIsCreating(true)} className="btn-primary">
            + 新建模板
          </button>
        </div>

        <div className="mb-4 space-y-3">
          <input
            type="text"
            placeholder="按名称/描述搜索..."
            value={searchKeyword}
            onChange={(e) => setSearchKeyword(e.target.value)}
            className="input-field w-full"
          />
          {allTags.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {allTags.map((tag) => (
                <button
                  key={tag}
                  onClick={() => toggleTag(tag)}
                  className={`px-3 py-1 rounded-full text-xs transition-all ${
                    selectedTags.includes(tag)
                      ? 'bg-blue-600 text-white'
                      : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                  }`}
                >
                  #{tag}
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {templates.map((t) => (
            <div
              key={t.id}
              onClick={() => setSelectedTemplate(t)}
              className={`card cursor-pointer transition-all ${
                selectedTemplate?.id === t.id
                  ? 'border-blue-500 ring-2 ring-blue-500/30'
                  : 'hover:border-slate-600'
              }`}
            >
              <div className="flex items-start justify-between mb-2">
                <div>
                  <h3 className="font-semibold truncate">{t.name}</h3>
                  <span className="text-xs text-slate-500">v{t.version_number}</span>
                </div>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    handleDeleteTemplate(t.id);
                  }}
                  className="text-red-400 hover:text-red-300 text-sm"
                >
                  删除
                </button>
              </div>
              <p className="text-xs text-slate-400 mb-3 line-clamp-2">
                {t.description || '暂无描述'}
              </p>
              {(t.tags || []).length > 0 && (
                <div className="flex flex-wrap gap-1 mb-2">
                  {(t.tags || []).slice(0, 3).map((tag) => (
                    <span key={tag} className="px-2 py-0.5 bg-purple-600/30 text-purple-300 rounded text-xs">
                      #{tag}
                    </span>
                  ))}
                </div>
              )}
              <div className="flex flex-wrap gap-2 text-xs">
                <span className="px-2 py-0.5 bg-slate-700 rounded">{t.algorithm}</span>
                <span className="px-2 py-0.5 bg-slate-700 rounded">{t.agent_count} 智能体</span>
                <span className="px-2 py-0.5 bg-blue-600/30 text-blue-300 rounded">
                  {Object.keys(t.param_variables || {}).length} 个变量
                </span>
              </div>
            </div>
          ))}
          {templates.length === 0 && (
            <p className="text-slate-500 text-center py-8 col-span-full">暂无模板</p>
          )}
        </div>
      </div>

      {selectedTemplate && (
        <div className="w-[500px] border-l border-slate-700 pl-4 overflow-y-auto">
          <div className="mb-4">
            <div className="flex items-center justify-between mb-2">
              <h2 className="text-lg font-bold">{selectedTemplate.name}</h2>
              <span className="px-2 py-0.5 bg-blue-600/30 text-blue-300 rounded text-xs">
                v{selectedTemplate.version_number}
              </span>
            </div>
            <p className="text-sm text-slate-400 mb-3">{selectedTemplate.description || '暂无描述'}</p>
            {(selectedTemplate.tags || []).length > 0 && (
              <div className="flex flex-wrap gap-1 mb-3">
                {(selectedTemplate.tags || []).map((tag) => (
                  <span key={tag} className="px-2 py-0.5 bg-purple-600/30 text-purple-300 rounded text-xs">
                    #{tag}
                  </span>
                ))}
              </div>
            )}
            <div className="grid grid-cols-2 gap-2 text-xs text-slate-400">
              <div>算法: <span className="text-slate-200">{selectedTemplate.algorithm}</span></div>
              <div>环境: <span className="text-slate-200">{getEnvName(selectedTemplate.environment_id)}</span></div>
              <div>智能体: <span className="text-slate-200">{selectedTemplate.agent_count}</span></div>
              <div>回合数: <span className="text-slate-200">{selectedTemplate.total_episodes}</span></div>
            </div>
          </div>

          {templateVersions.length > 0 && (
            <div className="card mb-4">
              <h3 className="font-semibold mb-3">版本历史</h3>
              <div className="space-y-2 max-h-48 overflow-y-auto">
                {templateVersions.map((v) => (
                  <div
                    key={v.id}
                    className={`flex items-center justify-between text-sm p-2 rounded ${
                      v.id === selectedTemplate.id
                        ? 'bg-blue-600/20 border border-blue-500/50'
                        : 'hover:bg-slate-700/50'
                    }`}
                  >
                    <div>
                      <span className="font-medium">v{v.version_number}</span>
                      {v.is_current_version && (
                        <span className="ml-2 text-xs text-green-400">当前版本</span>
                      )}
                      <span className="ml-2 text-xs text-slate-500">
                        {new Date(v.created_at).toLocaleDateString()}
                      </span>
                    </div>
                    {v.id !== selectedTemplate.id && (
                      <button
                        onClick={() => handleRollback(v.id)}
                        className="text-xs text-blue-400 hover:text-blue-300"
                      >
                        回滚
                      </button>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="card mb-4">
            <h3 className="font-semibold mb-3">参数变量</h3>
            <div className="space-y-2 mb-4 max-h-60 overflow-y-auto">
              {Object.entries(selectedTemplate.param_variables || {}).map(([key, values]) => (
                <div key={key} className="flex items-center justify-between text-sm">
                  <span className="text-slate-300">
                    {key.split('/').pop()}
                    <span className="text-slate-500 text-xs ml-2">
                      ({(values as any[]).length} 个值)
                    </span>
                  </span>
                  <button
                    onClick={() => handleRemoveVariable(key)}
                    className="text-red-400 hover:text-red-300 text-xs"
                  >
                    移除
                  </button>
                </div>
              ))}
              {Object.keys(selectedTemplate.param_variables || {}).length === 0 && (
                <p className="text-slate-500 text-sm">暂无参数变量</p>
              )}
            </div>

            <div className="space-y-2 border-t border-slate-700 pt-3">
              <input
                placeholder="参数路径 (如 learning_rate)"
                value={paramVarKey}
                onChange={(e) => setParamVarKey(e.target.value)}
                className="input-field w-full text-sm"
              />
              <input
                placeholder="候选值 (逗号分隔, 如 0.001,0.01,0.1)"
                value={paramVarValues}
                onChange={(e) => setParamVarValues(e.target.value)}
                className="input-field w-full text-sm"
              />
              <button onClick={handleAddVariable} className="btn-secondary w-full text-sm">
                添加变量
              </button>
            </div>
          </div>

          <button onClick={handlePreviewBatch} className="btn-primary w-full mb-4">
            🚀 批量运行
          </button>

          <div>
            <h3 className="font-semibold mb-3">历史批量运行</h3>
            <div className="space-y-2">
              {batchRuns.map((br) => (
                <div
                  key={br.id}
                  onClick={() => setSelectedBatchRun(br)}
                  className={`card text-sm cursor-pointer transition-all ${
                    selectedBatchRun?.id === br.id
                      ? 'border-blue-500'
                      : 'hover:border-slate-600'
                  }`}
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-medium truncate">{br.name}</span>
                    <div className="flex items-center gap-1">
                      {isStale(br) && (
                        <span className="px-2 py-0.5 rounded text-xs text-white bg-orange-600 animate-pulse">
                          可能中断
                        </span>
                      )}
                      <span
                        className={`px-2 py-0.5 rounded text-xs text-white ${statusColors[br.status] || 'bg-slate-600'}`}
                      >
                        {br.status}
                      </span>
                    </div>
                  </div>
                  <p className="text-xs text-slate-400">
                    {br.experiment_ids?.length || 0} 个实验 · v{br.template_version} · 并行{br.max_parallel} · {new Date(br.created_at).toLocaleString()}
                  </p>
                  <div className="flex gap-2 mt-2">
                    {br.status === 'running' && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleCancelBatchRun(br.id);
                        }}
                        className="text-red-400 hover:text-red-300 text-xs"
                      >
                        取消
                      </button>
                    )}
                    {isStale(br) && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleResumeBatchRun(br.id);
                        }}
                        className="text-green-400 hover:text-green-300 text-xs"
                      >
                        恢复执行
                      </button>
                    )}
                  </div>
                </div>
              ))}
              {batchRuns.length === 0 && (
                <p className="text-slate-500 text-sm">暂无批量运行记录</p>
              )}
            </div>
          </div>
        </div>
      )}

      {selectedBatchRun && batchStats && (
        <div className="w-[600px] border-l border-slate-700 pl-4 overflow-y-auto">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-bold">{selectedBatchRun.name} - 结果</h2>
            <button
              onClick={() => setSelectedBatchRun(null)}
              className="text-slate-400 hover:text-slate-200"
            >
              ✕
            </button>
          </div>

          <div className="grid grid-cols-2 gap-3 mb-4">
            <div className="card">
              <div className="text-xs text-slate-400">状态</div>
              <div className={`font-bold ${
                batchStats.status === 'completed' ? 'text-green-400' :
                batchStats.status === 'running' ? 'text-yellow-400' :
                batchStats.status === 'failed' ? 'text-red-400' : 'text-slate-300'
              }`}>
                {batchStats.status}
              </div>
            </div>
            <div className="card">
              <div className="text-xs text-slate-400">进度</div>
              <div className="font-bold">
                {batchStats.completed_count}/{batchStats.total_experiments}
              </div>
            </div>
            <div className="card">
              <div className="text-xs text-slate-400">并行度</div>
              <div className="font-bold">{batchStats.max_parallel}</div>
            </div>
            <div className="card">
              <div className="text-xs text-slate-400">耗时</div>
              <div className="font-bold">{formatDuration(batchStats.total_duration_seconds)}</div>
            </div>
          </div>

          {batchStats.best_combination && (
            <div className="card mb-4 bg-green-900/20 border-green-700/50">
              <div className="text-xs text-green-400 mb-1">🏆 最佳参数组合</div>
              <div className="font-bold text-green-300 mb-2">
                Reward: {batchStats.best_combination.final_reward}
              </div>
              <div className="flex flex-wrap gap-1">
                {Object.entries(batchStats.best_combination.params).map(([k, v]) => (
                  <span key={k} className="px-2 py-0.5 bg-green-800/30 rounded text-xs">
                    {k.split('/').pop()}: {String(v)}
                  </span>
                ))}
              </div>
            </div>
          )}

          {batchStats.is_stale && (
            <div className="card mb-4 bg-orange-900/20 border-orange-700/50">
              <div className="text-xs text-orange-400 mb-1">⚠️ 可能中断</div>
              <div className="text-sm text-orange-300">
                该批量运行超过5分钟无进度更新，可能已中断。
              </div>
              <button
                onClick={() => handleResumeBatchRun(selectedBatchRun.id)}
                className="btn-success mt-2 text-sm"
              >
                恢复执行
              </button>
            </div>
          )}

          {batchStats.parallel_coords_data && (
            <div className="mb-4">
              <SimpleParallelCoordinates data={batchStats.parallel_coords_data} />
            </div>
          )}

          {batchStats.heatmap_data && (
            <div className="mb-4 space-y-3">
              {batchStats.heatmap_data.available_variables.length > 2 && (
                <div className="card">
                  <div className="text-xs text-slate-400 mb-2">选择热力图变量</div>
                  <div className="flex gap-2">
                    <select
                      value={heatmapVarA || batchStats.heatmap_data.var_a_path}
                      onChange={(e) => setHeatmapVarA(e.target.value)}
                      className="select-field text-sm flex-1"
                    >
                      {batchStats.heatmap_data.available_variables.map((v) => (
                        <option key={v.path} value={v.path}>行: {v.name}</option>
                      ))}
                    </select>
                    <select
                      value={heatmapVarB || batchStats.heatmap_data.var_b_path}
                      onChange={(e) => setHeatmapVarB(e.target.value)}
                      className="select-field text-sm flex-1"
                    >
                      {batchStats.heatmap_data.available_variables.map((v) => (
                        <option key={v.path} value={v.path}>列: {v.name}</option>
                      ))}
                    </select>
                  </div>
                </div>
              )}
              <HeatmapChart data={batchStats.heatmap_data} />
            </div>
          )}

          <div className="card">
            <h4 className="font-semibold mb-3">实验列表</h4>
            <div className="space-y-2 max-h-96 overflow-y-auto">
              {batchStats.experiments.map((exp) => (
                <div key={exp.id} className="text-sm border-b border-slate-700 pb-2">
                  <div className="flex items-center justify-between">
                    <span className="font-medium">{exp.name}</span>
                    <span className={`px-2 py-0.5 rounded text-xs text-white ${
                      exp.status === 'completed' ? 'bg-green-600' :
                      exp.status === 'running' ? 'bg-yellow-600' :
                      exp.status === 'error' || exp.status === 'stopped' ? 'bg-red-600' : 'bg-slate-600'
                    }`}>
                      {exp.status}
                    </span>
                  </div>
                  <div className="text-xs text-slate-400 mt-1">
                    {exp.final_reward !== null ? `Reward: ${exp.final_reward}` : `进度: ${exp.current_episode}/${exp.total_episodes}`}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {isCreating && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-slate-800 rounded-lg p-6 w-[500px]">
            <h3 className="text-lg font-bold mb-4">新建模板</h3>
            <div className="space-y-4">
              <div>
                <label className="text-sm text-slate-400">模板名称</label>
                <input
                  value={newTemplateName}
                  onChange={(e) => setNewTemplateName(e.target.value)}
                  className="input-field w-full mt-1"
                />
              </div>
              <div>
                <label className="text-sm text-slate-400">描述</label>
                <textarea
                  value={newTemplateDesc}
                  onChange={(e) => setNewTemplateDesc(e.target.value)}
                  className="input-field w-full mt-1"
                  rows={3}
                />
              </div>
              <div>
                <label className="text-sm text-slate-400">标签（逗号分隔）</label>
                <input
                  value={newTemplateTags}
                  onChange={(e) => setNewTemplateTags(e.target.value)}
                  placeholder="如: IQL,4agent,grid-search"
                  className="input-field w-full mt-1"
                />
              </div>
            </div>
            <div className="flex gap-2 mt-4">
              <button onClick={handleCreateTemplate} className="btn-primary">
                创建
              </button>
              <button onClick={() => setIsCreating(false)} className="btn-secondary">
                取消
              </button>
            </div>
          </div>
        </div>
      )}

      {showBatchPreview && batchPreview && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-slate-800 rounded-lg p-6 w-[750px] max-h-[85vh] overflow-y-auto">
            <h3 className="text-lg font-bold mb-2">批量运行预览</h3>
            <p className="text-sm text-slate-400 mb-4">
              共 {batchPreview.total_combinations} 个参数组合
              {batchPreview.estimated_duration_seconds && (
                <span className="ml-2 text-blue-400">
                  · 预估耗时: {formatDuration(batchPreview.estimated_duration_seconds)}
                </span>
              )}
            </p>

            <div className="mb-4">
              <label className="text-sm text-slate-400">批量运行名称</label>
              <input
                value={newBatchName}
                onChange={(e) => setNewBatchName(e.target.value)}
                className="input-field w-full mt-1"
              />
            </div>

            <div className="mb-4 card">
              <div className="flex items-center justify-between mb-2">
                <label className="text-sm text-slate-400">并行度</label>
                <span className="text-lg font-bold text-blue-400">{maxParallel}</span>
              </div>
              <input
                type="range"
                min={1}
                max={4}
                step={1}
                value={maxParallel}
                onChange={(e) => {
                  const val = parseInt(e.target.value);
                  setMaxParallel(val);
                  if (selectedTemplate) {
                    batchRunApi.preview(selectedTemplate.id, val).then((res) => {
                      setBatchPreview(res.data);
                    });
                  }
                }}
                className="w-full"
              />
              <div className="flex justify-between text-xs text-slate-500 mt-1">
                <span>1（顺序）</span>
                <span>2</span>
                <span>3</span>
                <span>4（最快）</span>
              </div>
            </div>

            <div className="card mb-4 max-h-80 overflow-y-auto">
              <h4 className="font-semibold mb-3">参数组合列表</h4>
              <div className="space-y-2">
                {batchPreview.param_combinations.map((combo, idx) => (
                  <div key={idx} className="flex items-center gap-3 text-sm">
                    <span className="text-slate-500 w-8">#{idx + 1}</span>
                    <div className="flex-1 flex flex-wrap gap-2">
                      {Object.entries(combo).map(([k, v]) => (
                        <span key={k} className="px-2 py-0.5 bg-slate-700 rounded text-xs">
                          {k.split('/').pop()}: {String(v)}
                        </span>
                      ))}
                      {Object.keys(combo).length === 0 && (
                        <span className="text-slate-500 text-xs">无变量参数</span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="flex gap-2">
              <button onClick={handleCreateBatchRun} className="btn-primary">
                确认创建并运行
              </button>
              <button onClick={() => setShowBatchPreview(false)} className="btn-secondary">
                取消
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
