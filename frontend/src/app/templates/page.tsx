'use client';

import { useState, useEffect, useCallback } from 'react';
import { ExperimentTemplate, BatchRun, BatchRunPreview } from '@/types';
import { templateApi, batchRunApi, environmentApi, experimentApi } from '@/lib/api';

export default function TemplatesPage() {
  const [templates, setTemplates] = useState<ExperimentTemplate[]>([]);
  const [environments, setEnvironments] = useState<any[]>([]);
  const [selectedTemplate, setSelectedTemplate] = useState<ExperimentTemplate | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [showBatchPreview, setShowBatchPreview] = useState(false);
  const [batchPreview, setBatchPreview] = useState<BatchRunPreview | null>(null);
  const [batchRuns, setBatchRuns] = useState<BatchRun[]>([]);
  const [newTemplateName, setNewTemplateName] = useState('');
  const [newTemplateDesc, setNewTemplateDesc] = useState('');
  const [newBatchName, setNewBatchName] = useState('');
  const [paramVarKey, setParamVarKey] = useState('');
  const [paramVarValues, setParamVarValues] = useState('');

  const fetchTemplates = useCallback(async () => {
    try {
      const res = await templateApi.list();
      setTemplates(res.data);
    } catch (e) {
      console.error(e);
    }
  }, []);

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

  useEffect(() => {
    if (selectedTemplate) {
      fetchBatchRuns(selectedTemplate.id);
    }
  }, [selectedTemplate, fetchBatchRuns]);

  const handleCreateTemplate = async () => {
    if (!newTemplateName) return;
    try {
      await templateApi.create({
        name: newTemplateName,
        description: newTemplateDesc,
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
      fetchTemplates();
    } catch (e) {
      console.error(e);
    }
  };

  const handleDeleteTemplate = async (id: number) => {
    if (!confirm('确定删除该模板？')) return;
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
    } catch (e) {
      console.error(e);
    }
  };

  const handlePreviewBatch = async () => {
    if (!selectedTemplate) return;
    try {
      const res = await batchRunApi.preview(selectedTemplate.id);
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
    } catch (e) {
      console.error(e);
    }
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

  return (
    <div className="flex gap-4 h-full">
      <div className="flex-1">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-2xl font-bold">实验模板</h1>
          <button onClick={() => setIsCreating(true)} className="btn-primary">
            + 新建模板
          </button>
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
                <h3 className="font-semibold truncate">{t.name}</h3>
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
        <div className="w-[420px] border-l border-slate-700 pl-4 overflow-y-auto">
          <div className="mb-4">
            <h2 className="text-lg font-bold mb-2">{selectedTemplate.name}</h2>
            <p className="text-sm text-slate-400 mb-3">{selectedTemplate.description || '暂无描述'}</p>
            <div className="grid grid-cols-2 gap-2 text-xs text-slate-400">
              <div>算法: <span className="text-slate-200">{selectedTemplate.algorithm}</span></div>
              <div>环境: <span className="text-slate-200">{getEnvName(selectedTemplate.environment_id)}</span></div>
              <div>智能体: <span className="text-slate-200">{selectedTemplate.agent_count}</span></div>
              <div>回合数: <span className="text-slate-200">{selectedTemplate.total_episodes}</span></div>
            </div>
          </div>

          <div className="card mb-4">
            <h3 className="font-semibold mb-3">参数变量</h3>
            <div className="space-y-2 mb-4 max-h-60 overflow-y-auto">
              {Object.entries(selectedTemplate.param_variables || {}).map(([key, values]) => (
                <div key={key} className="flex items-center justify-between text-sm">
                  <span className="text-slate-300">
                    {key.split('/').pop()}
                    <span className="text-slate-500 text-xs ml-2">
                      ({values.length} 个值)
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
                <div key={br.id} className="card text-sm">
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-medium truncate">{br.name}</span>
                    <span
                      className={`px-2 py-0.5 rounded text-xs text-white ${statusColors[br.status] || 'bg-slate-600'}`}
                    >
                      {br.status}
                    </span>
                  </div>
                  <p className="text-xs text-slate-400">
                    {br.experiment_ids?.length || 0} 个实验 | {new Date(br.created_at).toLocaleString()}
                  </p>
                  {br.status === 'running' && (
                    <button
                      onClick={() => handleCancelBatchRun(br.id)}
                      className="text-red-400 hover:text-red-300 text-xs mt-1"
                    >
                      取消运行
                    </button>
                  )}
                </div>
              ))}
              {batchRuns.length === 0 && (
                <p className="text-slate-500 text-sm">暂无批量运行记录</p>
              )}
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
          <div className="bg-slate-800 rounded-lg p-6 w-[700px] max-h-[80vh] overflow-y-auto">
            <h3 className="text-lg font-bold mb-2">批量运行预览</h3>
            <p className="text-sm text-slate-400 mb-4">
              共 {batchPreview.total_combinations} 个参数组合
            </p>

            <div className="mb-4">
              <label className="text-sm text-slate-400">批量运行名称</label>
              <input
                value={newBatchName}
                onChange={(e) => setNewBatchName(e.target.value)}
                className="input-field w-full mt-1"
              />
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
