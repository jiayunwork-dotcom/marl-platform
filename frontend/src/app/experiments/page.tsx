'use client';

import { useState, useEffect, useCallback } from 'react';
import { Environment, Experiment, AlgorithmConfig } from '@/types';
import { experimentApi, environmentApi, algorithmApi } from '@/lib/api';

const defaultAlgoConfig: AlgorithmConfig = {
  algorithm: 'IQL', learning_rate: 0.001, gamma: 0.99,
  epsilon_start: 1.0, epsilon_end: 0.05, epsilon_decay_steps: 50000,
  replay_buffer_size: 50000, batch_size: 32, target_update_freq: 200,
  qmix_hidden_dim: 64, mappo_clip: 0.2, mappo_gae_lambda: 0.95,
  communication_enabled: false, comm_dim: 8,
};

export default function ExperimentsPage() {
  const [experiments, setExperiments] = useState<Experiment[]>([]);
  const [environments, setEnvironments] = useState<Environment[]>([]);
  const [algorithms, setAlgorithms] = useState<any[]>([]);
  const [isCreating, setIsCreating] = useState(false);
  const [expName, setExpName] = useState('');
  const [selectedEnvId, setSelectedEnvId] = useState<number | null>(null);
  const [totalEpisodes, setTotalEpisodes] = useState(1000);
  const [algoConfig, setAlgoConfig] = useState<AlgorithmConfig>(defaultAlgoConfig);

  const fetchData = useCallback(async () => {
    try {
      const [expRes, envRes, algoRes] = await Promise.all([
        experimentApi.list(),
        environmentApi.list(),
        algorithmApi.list(),
      ]);
      setExperiments(expRes.data);
      setEnvironments(envRes.data);
      setAlgorithms(algoRes.data.algorithms || []);
    } catch (e) {
      console.error(e);
    }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handleCreate = async () => {
    if (!selectedEnvId) return;
    try {
      await experimentApi.create({
        name: expName,
        environment_id: selectedEnvId,
        algorithm_config: algoConfig,
        total_episodes: totalEpisodes,
      });
      setIsCreating(false);
      setExpName('');
      fetchData();
    } catch (e) {
      console.error(e);
    }
  };

  const handleStart = async (id: number) => {
    try {
      await experimentApi.start(id);
      fetchData();
    } catch (e) {
      console.error(e);
    }
  };

  const handlePause = async (id: number) => {
    try { await experimentApi.pause(id); fetchData(); } catch (e) { console.error(e); }
  };

  const handleResume = async (id: number) => {
    try { await experimentApi.resume(id); fetchData(); } catch (e) { console.error(e); }
  };

  const handleStop = async (id: number) => {
    try { await experimentApi.stop(id); fetchData(); } catch (e) { console.error(e); }
  };

  const statusColors: Record<string, string> = {
    created: 'bg-slate-600', queued: 'bg-yellow-600', running: 'bg-green-600',
    paused: 'bg-orange-600', completed: 'bg-blue-600', stopped: 'bg-red-600', error: 'bg-red-800',
  };

  const selectedAlgo = algorithms.find((a) => a.id === algoConfig.algorithm);

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">实验管理</h1>
        <button onClick={() => setIsCreating(true)} className="btn-primary">+ 新建实验</button>
      </div>

      <div className="space-y-3">
        {experiments.map((exp) => (
          <div key={exp.id} className="card flex items-center justify-between">
            <div className="flex-1">
              <div className="flex items-center gap-2">
                <h3 className="font-semibold">{exp.name}</h3>
                <span className={`px-2 py-0.5 rounded text-xs text-white ${statusColors[exp.status] || 'bg-slate-600'}`}>
                  {exp.status}
                </span>
              </div>
              <p className="text-xs text-slate-400 mt-1">
                {exp.algorithm} | Episode {exp.current_episode}/{exp.total_episodes}
                {exp.started_at && ` | 开始: ${new Date(exp.started_at).toLocaleString()}`}
              </p>
            </div>
            <div className="flex gap-2">
              {exp.status === 'created' && <button onClick={() => handleStart(exp.id)} className="btn-success text-sm">开始训练</button>}
              {exp.status === 'running' && <button onClick={() => handlePause(exp.id)} className="btn-secondary text-sm">暂停</button>}
              {exp.status === 'paused' && <button onClick={() => handleResume(exp.id)} className="btn-success text-sm">恢复</button>}
              {(exp.status === 'running' || exp.status === 'paused') && (
                <button onClick={() => handleStop(exp.id)} className="btn-danger text-sm">终止</button>
              )}
            </div>
          </div>
        ))}
        {experiments.length === 0 && <p className="text-slate-500 text-center py-8">暂无实验</p>}
      </div>

      {isCreating && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-slate-800 rounded-lg p-6 w-[600px] max-h-[80vh] overflow-y-auto">
            <h3 className="text-lg font-bold mb-4">新建实验</h3>
            <div className="space-y-4">
              <div>
                <label className="text-sm text-slate-400">实验名称</label>
                <input value={expName} onChange={(e) => setExpName(e.target.value)} className="input-field w-full mt-1" />
              </div>

              <div>
                <label className="text-sm text-slate-400">选择环境</label>
                <select value={selectedEnvId || ''} onChange={(e) => setSelectedEnvId(parseInt(e.target.value))} className="select-field w-full mt-1">
                  <option value="">请选择...</option>
                  {environments.map((env) => (
                    <option key={env.id} value={env.id}>{env.name} ({env.width}×{env.height})</option>
                  ))}
                </select>
              </div>

              <div>
                <label className="text-sm text-slate-400">训练总回合数</label>
                <input type="number" value={totalEpisodes} onChange={(e) => setTotalEpisodes(parseInt(e.target.value))} className="input-field w-full mt-1" />
              </div>

              <div className="card">
                <h4 className="font-semibold mb-3">算法选择与超参数配置</h4>
                <div className="grid grid-cols-2 gap-3 mb-3">
                  <div className="col-span-2">
                    <label className="text-sm text-slate-400">算法</label>
                    <select
                      value={algoConfig.algorithm}
                      onChange={(e) => setAlgoConfig((prev) => ({ ...prev, algorithm: e.target.value }))}
                      className="select-field w-full mt-1"
                    >
                      {algorithms.map((a) => (
                        <option key={a.id} value={a.id}>{a.name}</option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="text-sm text-slate-400">学习率</label>
                    <input type="number" step="0.0001" value={algoConfig.learning_rate}
                      onChange={(e) => setAlgoConfig((p) => ({ ...p, learning_rate: parseFloat(e.target.value) }))}
                      className="input-field w-full mt-1" />
                  </div>
                  <div>
                    <label className="text-sm text-slate-400">折扣因子 γ</label>
                    <input type="number" step="0.01" value={algoConfig.gamma}
                      onChange={(e) => setAlgoConfig((p) => ({ ...p, gamma: parseFloat(e.target.value) }))}
                      className="input-field w-full mt-1" />
                  </div>
                  <div>
                    <label className="text-sm text-slate-400">经验回放池大小</label>
                    <input type="number" value={algoConfig.replay_buffer_size}
                      onChange={(e) => setAlgoConfig((p) => ({ ...p, replay_buffer_size: parseInt(e.target.value) }))}
                      className="input-field w-full mt-1" />
                  </div>
                  <div>
                    <label className="text-sm text-slate-400">Batch Size</label>
                    <input type="number" value={algoConfig.batch_size}
                      onChange={(e) => setAlgoConfig((p) => ({ ...p, batch_size: parseInt(e.target.value) }))}
                      className="input-field w-full mt-1" />
                  </div>
                  <div>
                    <label className="text-sm text-slate-400">目标网络更新频率</label>
                    <input type="number" value={algoConfig.target_update_freq}
                      onChange={(e) => setAlgoConfig((p) => ({ ...p, target_update_freq: parseInt(e.target.value) }))}
                      className="input-field w-full mt-1" />
                  </div>
                  <div>
                    <label className="text-sm text-slate-400">ε 衰减步数</label>
                    <input type="number" value={algoConfig.epsilon_decay_steps}
                      onChange={(e) => setAlgoConfig((p) => ({ ...p, epsilon_decay_steps: parseInt(e.target.value) }))}
                      className="input-field w-full mt-1" />
                  </div>

                  {algoConfig.algorithm === 'QMIX' && (
                    <div>
                      <label className="text-sm text-slate-400">混合网络隐藏层维度</label>
                      <input type="number" value={algoConfig.qmix_hidden_dim}
                        onChange={(e) => setAlgoConfig((p) => ({ ...p, qmix_hidden_dim: parseInt(e.target.value) }))}
                        className="input-field w-full mt-1" />
                    </div>
                  )}

                  {algoConfig.algorithm === 'MAPPO' && (
                    <>
                      <div>
                        <label className="text-sm text-slate-400">Clip 参数</label>
                        <input type="number" step="0.01" value={algoConfig.mappo_clip}
                          onChange={(e) => setAlgoConfig((p) => ({ ...p, mappo_clip: parseFloat(e.target.value) }))}
                          className="input-field w-full mt-1" />
                      </div>
                      <div>
                        <label className="text-sm text-slate-400">GAE λ</label>
                        <input type="number" step="0.01" value={algoConfig.mappo_gae_lambda}
                          onChange={(e) => setAlgoConfig((p) => ({ ...p, mappo_gae_lambda: parseFloat(e.target.value) }))}
                          className="input-field w-full mt-1" />
                      </div>
                    </>
                  )}

                  {(algoConfig.algorithm === 'QMIX' || algoConfig.algorithm === 'MAPPO') && (
                    <>
                      <div className="col-span-2 flex items-center gap-3">
                        <label className="text-sm text-slate-400">启用通信</label>
                        <input type="checkbox" checked={algoConfig.communication_enabled}
                          onChange={(e) => setAlgoConfig((p) => ({ ...p, communication_enabled: e.target.checked }))} />
                      </div>
                      {algoConfig.communication_enabled && (
                        <div>
                          <label className="text-sm text-slate-400">消息维度</label>
                          <input type="number" value={algoConfig.comm_dim}
                            onChange={(e) => setAlgoConfig((p) => ({ ...p, comm_dim: parseInt(e.target.value) }))}
                            className="input-field w-full mt-1" />
                        </div>
                      )}
                    </>
                  )}
                </div>
              </div>
            </div>

            <div className="flex gap-2 mt-4">
              <button onClick={handleCreate} className="btn-primary">创建实验</button>
              <button onClick={() => setIsCreating(false)} className="btn-secondary">取消</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
