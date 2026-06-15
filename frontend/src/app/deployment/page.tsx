'use client';

import { useState, useEffect, useCallback } from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, LineChart, Line } from 'recharts';
import { PolicyService, InferenceLog, InferenceStats, Experiment, CheckpointItem } from '@/types';
import { policyApi, experimentApi } from '@/lib/api';

const statusColors: Record<string, string> = {
  created: 'bg-slate-600',
  deploying: 'bg-yellow-600',
  running: 'bg-green-600',
  stopped: 'bg-gray-600',
  error: 'bg-red-600',
};

const statusLabels: Record<string, string> = {
  created: '已创建',
  deploying: '部署中',
  running: '运行中',
  stopped: '已停止',
  error: '异常',
};

export default function DeploymentPage() {
  const [policies, setPolicies] = useState<PolicyService[]>([]);
  const [experiments, setExperiments] = useState<Experiment[]>([]);
  const [selectedPolicy, setSelectedPolicy] = useState<PolicyService | null>(null);
  const [stats, setStats] = useState<InferenceStats | null>(null);
  const [logs, setLogs] = useState<InferenceLog[]>([]);
  const [isCreating, setIsCreating] = useState(false);
  const [checkpoints, setCheckpoints] = useState<CheckpointItem[]>([]);

  const [formName, setFormName] = useState('');
  const [formExpId, setFormExpId] = useState<number | null>(null);
  const [formCkptId, setFormCkptId] = useState<number | null>(null);
  const [formMaxConcurrent, setFormMaxConcurrent] = useState(10);
  const [formTimeoutMs, setFormTimeoutMs] = useState(5000);

  const [latencyBuckets, setLatencyBuckets] = useState<{ range: string; count: number }[]>([]);
  const [qpsTimeline, setQpsTimeline] = useState<{ time: string; qps: number }[]>([]);

  const fetchData = useCallback(async () => {
    try {
      const [polRes, expRes] = await Promise.all([
        policyApi.list(),
        experimentApi.list(),
      ]);
      setPolicies(polRes.data);
      setExperiments(expRes.data);
    } catch (e) {
      console.error(e);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 5000);
    return () => clearInterval(interval);
  }, [fetchData]);

  const fetchDetail = useCallback(async (policy: PolicyService) => {
    try {
      const [statsRes, logsRes] = await Promise.all([
        policyApi.getStats(policy.id),
        policyApi.getLogs(policy.id, 0, 50),
      ]);
      setStats(statsRes.data);
      setLogs(logsRes.data.logs || []);

      if (logsRes.data.logs && logsRes.data.logs.length > 0) {
        const latencies = logsRes.data.logs
          .filter((l: InferenceLog) => !l.is_timeout)
          .map((l: InferenceLog) => l.latency_ms);

        if (latencies.length > 0) {
          const min = Math.floor(Math.min(...latencies));
          const max = Math.ceil(Math.max(...latencies));
          const bucketSize = Math.max(Math.ceil((max - min) / 10), 1);
          const buckets: { range: string; count: number }[] = [];
          for (let i = min; i < max; i += bucketSize) {
            const lo = i;
            const hi = i + bucketSize;
            const count = latencies.filter((v: number) => v >= lo && v < hi).length;
            buckets.push({ range: `${lo}-${hi}`, count });
          }
          setLatencyBuckets(buckets);
        }

        const sortedLogs = [...logsRes.data.logs].sort(
          (a: InferenceLog, b: InferenceLog) =>
            new Date(a.request_time).getTime() - new Date(b.request_time).getTime()
        );
        const byMinute: Record<string, number> = {};
        sortedLogs.forEach((l: InferenceLog) => {
          const d = new Date(l.request_time);
          const key = `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`;
          byMinute[key] = (byMinute[key] || 0) + 1;
        });
        const timeline = Object.entries(byMinute).map(([time, count]) => ({
          time,
          qps: Number((count / 60).toFixed(3)),
        }));
        setQpsTimeline(timeline);
      }
    } catch (e) {
      console.error(e);
    }
  }, []);

  useEffect(() => {
    if (selectedPolicy) {
      fetchDetail(selectedPolicy);
      const interval = setInterval(() => fetchDetail(selectedPolicy), 10000);
      return () => clearInterval(interval);
    }
  }, [selectedPolicy?.id]);

  const handleLoadCheckpoints = async (expId: number) => {
    setFormExpId(expId);
    setFormCkptId(null);
    try {
      const res = await experimentApi.getCheckpoints(expId);
      setCheckpoints(res.data);
    } catch (e) {
      console.error(e);
      setCheckpoints([]);
    }
  };

  const handleCreate = async () => {
    if (!formExpId || !formCkptId || !formName) return;
    try {
      await policyApi.create({
        name: formName,
        experiment_id: formExpId,
        checkpoint_id: formCkptId,
        max_concurrent: formMaxConcurrent,
        timeout_ms: formTimeoutMs,
      });
      setIsCreating(false);
      setFormName('');
      setFormExpId(null);
      setFormCkptId(null);
      setFormMaxConcurrent(10);
      setFormTimeoutMs(5000);
      setCheckpoints([]);
      fetchData();
    } catch (e) {
      console.error(e);
    }
  };

  const handleStart = async (id: number) => {
    try { await policyApi.start(id); fetchData(); } catch (e) { console.error(e); }
  };

  const handleStop = async (id: number) => {
    try { await policyApi.stop(id); fetchData(); } catch (e) { console.error(e); }
  };

  const handleDelete = async (id: number) => {
    if (!confirm('确定删除此策略服务？')) return;
    try {
      await policyApi.delete(id);
      if (selectedPolicy?.id === id) setSelectedPolicy(null);
      fetchData();
    } catch (e) { console.error(e); }
  };

  const getExpName = (expId: number) => {
    const exp = experiments.find((e) => e.id === expId);
    return exp ? exp.name : `实验#${expId}`;
  };

  return (
    <div className="flex gap-6 h-full">
      <div className="flex-1">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-2xl font-bold">策略部署</h1>
          <button onClick={() => setIsCreating(true)} className="btn-primary">+ 新建部署</button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {policies.map((p) => (
            <div
              key={p.id}
              onClick={() => setSelectedPolicy(p)}
              className={`card cursor-pointer transition-all hover:ring-2 hover:ring-blue-500 ${
                p.status === 'error' ? 'border-red-500 bg-red-900/20' : ''
              } ${selectedPolicy?.id === p.id ? 'ring-2 ring-blue-400' : ''}`}
            >
              <div className="flex items-center justify-between mb-2">
                <h3 className="font-semibold text-lg">{p.name}</h3>
                <span className={`px-2 py-0.5 rounded text-xs text-white ${statusColors[p.status] || 'bg-slate-600'}`}>
                  {statusLabels[p.status] || p.status}
                </span>
              </div>
              <p className="text-sm text-slate-400 mb-1">关联实验: {getExpName(p.experiment_id)}</p>
              <p className="text-xs text-slate-500 mb-3">
                创建: {new Date(p.created_at).toLocaleString()}
              </p>
              {p.status === 'error' && p.error_reason && (
                <p className="text-xs text-red-400 mb-2 truncate" title={p.error_reason}>
                  错误: {p.error_reason}
                </p>
              )}
              <div className="flex gap-2">
                {(p.status === 'created' || p.status === 'stopped' || p.status === 'error') && (
                  <button onClick={(e) => { e.stopPropagation(); handleStart(p.id); }} className="btn-success text-xs px-3 py-1">启动</button>
                )}
                {p.status === 'running' && (
                  <button onClick={(e) => { e.stopPropagation(); handleStop(p.id); }} className="btn-danger text-xs px-3 py-1">停止</button>
                )}
                <button onClick={(e) => { e.stopPropagation(); handleDelete(p.id); }} className="btn-secondary text-xs px-3 py-1">删除</button>
              </div>
            </div>
          ))}
          {policies.length === 0 && (
            <p className="text-slate-500 text-center py-8 col-span-3">暂无策略服务，点击右上角创建新部署</p>
          )}
        </div>
      </div>

      {selectedPolicy && (
        <div className="w-[480px] min-w-[480px] bg-slate-800 rounded-lg border border-slate-700 p-4 overflow-y-auto max-h-[calc(100vh-3rem)]">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-bold">{selectedPolicy.name} - 详情</h2>
            <button onClick={() => setSelectedPolicy(null)} className="text-slate-400 hover:text-white text-xl">&times;</button>
          </div>

          <div className="grid grid-cols-2 gap-3 mb-4 text-sm">
            <div className="card">
              <p className="text-slate-400 text-xs">总推理次数</p>
              <p className="text-xl font-bold">{stats?.total_count ?? '-'}</p>
            </div>
            <div className="card">
              <p className="text-slate-400 text-xs">平均延迟</p>
              <p className="text-xl font-bold">{stats?.avg_latency_ms ? `${stats.avg_latency_ms.toFixed(1)}ms` : '-'}</p>
            </div>
            <div className="card">
              <p className="text-slate-400 text-xs">P95 延迟</p>
              <p className="text-xl font-bold">{stats?.p95_latency_ms ? `${stats.p95_latency_ms.toFixed(1)}ms` : '-'}</p>
            </div>
            <div className="card">
              <p className="text-slate-400 text-xs">超时率</p>
              <p className="text-xl font-bold">{stats ? `${(stats.timeout_rate * 100).toFixed(1)}%` : '-'}</p>
            </div>
            <div className="card col-span-2">
              <p className="text-slate-400 text-xs">最近1小时 QPS</p>
              <p className="text-xl font-bold">{stats?.qps_last_hour ?? '-'}</p>
            </div>
          </div>

          {latencyBuckets.length > 0 && (
            <div className="mb-4">
              <h3 className="text-sm font-semibold mb-2">延迟分布</h3>
              <ResponsiveContainer width="100%" height={160}>
                <BarChart data={latencyBuckets}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                  <XAxis dataKey="range" tick={{ fontSize: 10, fill: '#94a3b8' }} />
                  <YAxis tick={{ fontSize: 10, fill: '#94a3b8' }} />
                  <Tooltip contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #334155' }} />
                  <Bar dataKey="count" fill="#3b82f6" radius={[2, 2, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}

          {qpsTimeline.length > 0 && (
            <div className="mb-4">
              <h3 className="text-sm font-semibold mb-2">QPS 时间线</h3>
              <ResponsiveContainer width="100%" height={140}>
                <LineChart data={qpsTimeline}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                  <XAxis dataKey="time" tick={{ fontSize: 10, fill: '#94a3b8' }} />
                  <YAxis tick={{ fontSize: 10, fill: '#94a3b8' }} />
                  <Tooltip contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #334155' }} />
                  <Line type="monotone" dataKey="qps" stroke="#10b981" strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}

          <h3 className="text-sm font-semibold mb-2">最近推理日志</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-slate-400 border-b border-slate-700">
                  <th className="text-left py-1 px-1">时间</th>
                  <th className="text-right py-1 px-1">延迟(ms)</th>
                  <th className="text-left py-1 px-1">动作</th>
                  <th className="text-center py-1 px-1">超时</th>
                </tr>
              </thead>
              <tbody>
                {logs.slice(0, 50).map((l) => (
                  <tr key={l.id} className="border-b border-slate-700/50 hover:bg-slate-700/30">
                    <td className="py-1 px-1 text-slate-300">
                      {new Date(l.request_time).toLocaleTimeString()}
                    </td>
                    <td className={`py-1 px-1 text-right ${l.is_timeout ? 'text-red-400' : 'text-slate-300'}`}>
                      {l.latency_ms.toFixed(1)}
                    </td>
                    <td className="py-1 px-1 text-slate-400">{l.output_actions}</td>
                    <td className="py-1 px-1 text-center">
                      {l.is_timeout ? <span className="text-red-400">Yes</span> : <span className="text-green-400">No</span>}
                    </td>
                  </tr>
                ))}
                {logs.length === 0 && (
                  <tr>
                    <td colSpan={4} className="text-center text-slate-500 py-4">暂无推理日志</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {isCreating && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-slate-800 rounded-lg p-6 w-[500px] max-h-[80vh] overflow-y-auto">
            <h3 className="text-lg font-bold mb-4">新建策略部署</h3>
            <div className="space-y-4">
              <div>
                <label className="text-sm text-slate-400">部署名称</label>
                <input value={formName} onChange={(e) => setFormName(e.target.value)} className="input-field w-full mt-1" placeholder="输入策略服务名称" />
              </div>

              <div>
                <label className="text-sm text-slate-400">选择实验</label>
                <select
                  value={formExpId || ''}
                  onChange={(e) => handleLoadCheckpoints(parseInt(e.target.value))}
                  className="select-field w-full mt-1"
                >
                  <option value="">请选择实验...</option>
                  {experiments.map((exp) => (
                    <option key={exp.id} value={exp.id}>{exp.name} ({exp.algorithm})</option>
                  ))}
                </select>
              </div>

              <div>
                <label className="text-sm text-slate-400">选择 Checkpoint</label>
                <select
                  value={formCkptId || ''}
                  onChange={(e) => setFormCkptId(parseInt(e.target.value))}
                  className="select-field w-full mt-1"
                  disabled={!formExpId}
                >
                  <option value="">{formExpId ? '请选择...' : '请先选择实验'}</option>
                  {checkpoints.map((c) => (
                    <option key={c.id} value={c.id}>Episode {c.episode}</option>
                  ))}
                </select>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-sm text-slate-400">最大并发推理数</label>
                  <input
                    type="number"
                    value={formMaxConcurrent}
                    onChange={(e) => setFormMaxConcurrent(parseInt(e.target.value))}
                    min={1}
                    max={100}
                    className="input-field w-full mt-1"
                  />
                </div>
                <div>
                  <label className="text-sm text-slate-400">推理超时 (ms)</label>
                  <input
                    type="number"
                    value={formTimeoutMs}
                    onChange={(e) => setFormTimeoutMs(parseInt(e.target.value))}
                    min={100}
                    max={60000}
                    className="input-field w-full mt-1"
                  />
                </div>
              </div>
            </div>

            <div className="flex gap-2 mt-4">
              <button onClick={handleCreate} className="btn-primary" disabled={!formName || !formExpId || !formCkptId}>创建部署</button>
              <button onClick={() => { setIsCreating(false); setCheckpoints([]); }} className="btn-secondary">取消</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
