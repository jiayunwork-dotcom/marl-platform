'use client';

import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  LineChart, Line, Legend,
} from 'recharts';
import {
  PolicyService, PolicyServiceDetail, InferenceLog, InferenceStats,
  Experiment, CheckpointItem, ABTestResponse, ABTestPolicyResult,
  PolicyResourceStats, PolicyServiceGroup,
} from '@/types';
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

type DetailTab = 'overview' | 'logs' | 'compare';

export default function DeploymentPage() {
  const [policies, setPolicies] = useState<PolicyService[]>([]);
  const [experiments, setExperiments] = useState<Experiment[]>([]);
  const [selectedPolicy, setSelectedPolicy] = useState<PolicyService | null>(null);
  const [policyDetail, setPolicyDetail] = useState<PolicyServiceDetail | null>(null);
  const [stats, setStats] = useState<InferenceStats | null>(null);
  const [resourceStats, setResourceStats] = useState<PolicyResourceStats | null>(null);
  const [logs, setLogs] = useState<InferenceLog[]>([]);
  const [isCreating, setIsCreating] = useState(false);
  const [checkpoints, setCheckpoints] = useState<CheckpointItem[]>([]);
  const [viewMode, setViewMode] = useState<'list' | 'grouped'>('list');
  const [detailTab, setDetailTab] = useState<DetailTab>('overview');
  const [groupedPolicies, setGroupedPolicies] = useState<PolicyServiceGroup[]>([]);
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set());

  const [formName, setFormName] = useState('');
  const [formExpId, setFormExpId] = useState<number | null>(null);
  const [formCkptId, setFormCkptId] = useState<number | null>(null);
  const [formMaxConcurrent, setFormMaxConcurrent] = useState(10);
  const [formTimeoutMs, setFormTimeoutMs] = useState(5000);

  const [comparePolicyA, setComparePolicyA] = useState<number | null>(null);
  const [comparePolicyB, setComparePolicyB] = useState<number | null>(null);
  const [compareObservations, setCompareObservations] = useState<string>('');
  const [abTestResult, setAbTestResult] = useState<ABTestResponse | null>(null);
  const [isComparing, setIsComparing] = useState(false);
  const [compareHistory, setCompareHistory] = useState<{ diff_rate: number; time: string }[]>([]);

  const [latencyBuckets, setLatencyBuckets] = useState<{ range: string; count: number }[]>([]);
  const [qpsTimeline, setQpsTimeline] = useState<{ time: string; qps: number }[]>([]);

  const fetchData = useCallback(async () => {
    try {
      const [polRes, expRes, groupedRes] = await Promise.all([
        policyApi.list(),
        experimentApi.list(),
        policyApi.listGrouped(),
      ]);
      setPolicies(polRes.data);
      setExperiments(expRes.data);
      setGroupedPolicies(groupedRes.data);
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
      const [detailRes, statsRes, logsRes, resourceRes] = await Promise.all([
        policyApi.get(policy.id),
        policyApi.getStats(policy.id),
        policyApi.getLogs(policy.id, 0, 50),
        policyApi.getResourceStats(policy.id),
      ]);
      setPolicyDetail(detailRes.data);
      setStats(statsRes.data);
      setLogs(logsRes.data.logs || []);
      setResourceStats(resourceRes.data);

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
      const interval = setInterval(() => fetchDetail(selectedPolicy), 3000);
      return () => clearInterval(interval);
    }
  }, [selectedPolicy?.id, fetchDetail]);

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

  const runningPolicies = useMemo(
    () => policies.filter((p) => p.status === 'running'),
    [policies]
  );

  const handleRunABTest = async () => {
    if (!comparePolicyA || !comparePolicyB || !compareObservations) return;
    setIsComparing(true);
    try {
      let observations: number[][];
      try {
        observations = JSON.parse(compareObservations);
      } catch {
        alert('观测数据格式错误，请输入有效的 JSON 数组');
        setIsComparing(false);
        return;
      }

      const res = await policyApi.abTest({
        policy_a: comparePolicyA,
        policy_b: comparePolicyB,
        observations,
      });
      setAbTestResult(res.data);
      setCompareHistory((prev) => [
        ...prev,
        {
          diff_rate: res.data.diff_rate,
          time: new Date().toLocaleTimeString(),
        },
      ].slice(-20));
    } catch (e) {
      console.error(e);
    } finally {
      setIsComparing(false);
    }
  };

  const toggleGroup = (name: string) => {
    setExpandedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  };

  const loadLogAsInput = (log: InferenceLog) => {
    const actions = log.output_actions.split(',').map(Number);
    const dims = log.obs_dimensions.split(',').map(Number);
    const placeholderObs = dims.map((d) => Array(d).fill(0));
    setCompareObservations(JSON.stringify(placeholderObs, null, 2));
  };

  const isHighConcurrency = resourceStats && resourceStats.max_concurrent > 0
    ? resourceStats.current_concurrent / resourceStats.max_concurrent >= 0.8
    : false;

  const concurrencyPercent = resourceStats && resourceStats.max_concurrent > 0
    ? (resourceStats.current_concurrent / resourceStats.max_concurrent) * 100
    : 0;

  return (
    <div className="flex gap-6 h-full">
      <div className="flex-1 flex flex-col">
        <div className="flex items-center justify-between mb-4">
          <h1 className="text-2xl font-bold">策略部署</h1>
          <div className="flex items-center gap-3">
            <div className="flex bg-slate-700 rounded-lg p-0.5">
              <button
                onClick={() => setViewMode('list')}
                className={`px-3 py-1 text-sm rounded ${viewMode === 'list' ? 'bg-slate-600 text-white' : 'text-slate-400'}`}
              >
                列表视图
              </button>
              <button
                onClick={() => setViewMode('grouped')}
                className={`px-3 py-1 text-sm rounded ${viewMode === 'grouped' ? 'bg-slate-600 text-white' : 'text-slate-400'}`}
              >
                分组视图
              </button>
            </div>
            <button onClick={() => setIsCreating(true)} className="btn-primary">+ 新建部署</button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto">
          {viewMode === 'list' ? (
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
                    <h3 className="font-semibold text-lg">
                      {p.name}
                      <span className="ml-2 text-sm text-slate-400">v{p.version}</span>
                    </h3>
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
          ) : (
            <div className="space-y-3">
              {groupedPolicies.map((group) => (
                <div key={group.name} className="card">
                  <div
                    className="flex items-center justify-between cursor-pointer"
                    onClick={() => toggleGroup(group.name)}
                  >
                    <div className="flex items-center gap-2">
                      <span className="text-slate-400">{expandedGroups.has(group.name) ? '▼' : '▶'}</span>
                      <h3 className="font-semibold">{group.name}</h3>
                      <span className="text-xs text-slate-500">{group.versions.length} 个版本</span>
                    </div>
                    <span className={`px-2 py-0.5 rounded text-xs text-white ${
                      group.versions.some(v => v.status === 'running') ? 'bg-green-600' : 'bg-slate-600'
                    }`}>
                      {group.versions.some(v => v.status === 'running') ? '运行中' : '未运行'}
                    </span>
                  </div>
                  {expandedGroups.has(group.name) && (
                    <div className="mt-3 space-y-2 border-t border-slate-700 pt-3">
                      {group.versions.map((p) => (
                        <div
                          key={p.id}
                          onClick={(e) => { e.stopPropagation(); setSelectedPolicy(p); }}
                          className={`flex items-center justify-between p-2 rounded cursor-pointer hover:bg-slate-700/50 ${
                            selectedPolicy?.id === p.id ? 'bg-slate-700' : ''
                          }`}
                        >
                          <div className="flex items-center gap-3">
                            <span className="text-sm font-mono bg-slate-700 px-2 py-0.5 rounded">v{p.version}</span>
                            <span className="text-sm text-slate-400">ID: {p.id}</span>
                          </div>
                          <span className={`px-2 py-0.5 rounded text-xs text-white ${statusColors[p.status]}`}>
                            {statusLabels[p.status]}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))}
              {groupedPolicies.length === 0 && (
                <p className="text-slate-500 text-center py-8">暂无策略服务</p>
              )}
            </div>
          )}
        </div>
      </div>

      {selectedPolicy && (
        <div className="w-[520px] min-w-[520px] bg-slate-800 rounded-lg border border-slate-700 flex flex-col max-h-[calc(100vh-3rem)]">
          <div className="flex items-center justify-between p-4 border-b border-slate-700">
            <div>
              <h2 className="text-lg font-bold">
                {selectedPolicy.name}
                <span className="ml-2 text-sm text-slate-400">v{selectedPolicy.version}</span>
              </h2>
              <span className={`text-xs px-2 py-0.5 rounded text-white ${statusColors[selectedPolicy.status]}`}>
                {statusLabels[selectedPolicy.status]}
              </span>
            </div>
            <button onClick={() => setSelectedPolicy(null)} className="text-slate-400 hover:text-white text-xl">&times;</button>
          </div>

          <div className="flex border-b border-slate-700">
            {(['overview', 'logs', 'compare'] as DetailTab[]).map((tab) => (
              <button
                key={tab}
                onClick={() => setDetailTab(tab)}
                className={`flex-1 py-2 text-sm ${
                  detailTab === tab
                    ? 'text-blue-400 border-b-2 border-blue-400'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                {tab === 'overview' ? '概览' : tab === 'logs' ? '推理日志' : 'A/B对比'}
              </button>
            ))}
          </div>

          <div className="flex-1 overflow-y-auto p-4">
            {detailTab === 'overview' && (
              <div className="space-y-4">
                <div className="grid grid-cols-2 gap-3">
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
                    <p className="text-slate-400 text-xs">缓存命中率</p>
                    <p className="text-xl font-bold">{stats ? `${(stats.cache_hit_rate * 100).toFixed(1)}%` : '-'}</p>
                  </div>
                </div>

                {resourceStats && (
                  <div className="card">
                    <div className="flex items-center justify-between mb-2">
                      <h3 className="text-sm font-semibold">资源使用</h3>
                      {isHighConcurrency && (
                        <span className="px-2 py-0.5 bg-yellow-600 text-white text-xs rounded">高负载警告</span>
                      )}
                    </div>
                    <div className="space-y-3">
                      <div>
                        <div className="flex justify-between text-xs mb-1">
                          <span className="text-slate-400">并发数</span>
                          <span className="text-slate-300">
                            {resourceStats.current_concurrent} / {resourceStats.max_concurrent}
                          </span>
                        </div>
                        <div className="w-full bg-slate-700 rounded-full h-2">
                          <div
                            className={`h-2 rounded-full transition-all ${
                              isHighConcurrency ? 'bg-yellow-500' : 'bg-green-500'
                            }`}
                            style={{ width: `${Math.min(concurrencyPercent, 100)}%` }}
                          />
                        </div>
                      </div>
                      <div className="grid grid-cols-2 gap-3 text-sm">
                        <div>
                          <p className="text-slate-400 text-xs">队列深度</p>
                          <p className="font-semibold">{resourceStats.queue_depth}</p>
                        </div>
                        <div>
                          <p className="text-slate-400 text-xs">1分钟平均延迟</p>
                          <p className="font-semibold">{resourceStats.avg_latency_1min.toFixed(1)}ms</p>
                        </div>
                      </div>
                    </div>
                  </div>
                )}

                {policyDetail?.history_versions && policyDetail.history_versions.length > 0 && (
                  <div className="card">
                    <h3 className="text-sm font-semibold mb-2">历史版本</h3>
                    <div className="space-y-1 max-h-32 overflow-y-auto">
                      {policyDetail.history_versions.map((v) => (
                        <div
                          key={v.id}
                          className="flex items-center justify-between py-1 px-2 rounded hover:bg-slate-700/50 cursor-pointer text-sm"
                          onClick={() => { setSelectedPolicy(v); setDetailTab('overview'); }}
                        >
                          <span className="font-mono">v{v.version}</span>
                          <span className={`text-xs px-2 py-0.5 rounded text-white ${statusColors[v.status]}`}>
                            {statusLabels[v.status]}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {latencyBuckets.length > 0 && (
                  <div>
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
                  <div>
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
              </div>
            )}

            {detailTab === 'logs' && (
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-slate-400 border-b border-slate-700">
                      <th className="text-left py-1 px-1">时间</th>
                      <th className="text-right py-1 px-1">延迟(ms)</th>
                      <th className="text-left py-1 px-1">动作</th>
                      <th className="text-center py-1 px-1">超时</th>
                      <th className="text-center py-1 px-1">操作</th>
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
                        <td className="py-1 px-1 text-slate-400 font-mono text-xs">{l.output_actions}</td>
                        <td className="py-1 px-1 text-center">
                          {l.is_timeout ? <span className="text-red-400">Yes</span> : <span className="text-green-400">No</span>}
                        </td>
                        <td className="py-1 px-1 text-center">
                          <button
                            onClick={() => loadLogAsInput(l)}
                            className="text-blue-400 hover:text-blue-300 text-xs"
                            title="用作对比输入"
                          >
                            选用
                          </button>
                        </td>
                      </tr>
                    ))}
                    {logs.length === 0 && (
                      <tr>
                        <td colSpan={5} className="text-center text-slate-500 py-4">暂无推理日志</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            )}

            {detailTab === 'compare' && (
              <div className="space-y-4">
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-sm text-slate-400">策略 A</label>
                    <select
                      value={comparePolicyA || ''}
                      onChange={(e) => setComparePolicyA(Number(e.target.value) || null)}
                      className="select-field w-full mt-1"
                    >
                      <option value="">请选择...</option>
                      {runningPolicies.map((p) => (
                        <option key={p.id} value={p.id}>{p.name} v{p.version}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="text-sm text-slate-400">策略 B</label>
                    <select
                      value={comparePolicyB || ''}
                      onChange={(e) => setComparePolicyB(Number(e.target.value) || null)}
                      className="select-field w-full mt-1"
                    >
                      <option value="">请选择...</option>
                      {runningPolicies.filter(p => p.id !== comparePolicyA).map((p) => (
                        <option key={p.id} value={p.id}>{p.name} v{p.version}</option>
                      ))}
                    </select>
                  </div>
                </div>

                <div>
                  <label className="text-sm text-slate-400">观测数据 (JSON 数组)</label>
                  <textarea
                    value={compareObservations}
                    onChange={(e) => setCompareObservations(e.target.value)}
                    className="input-field w-full mt-1 h-32 font-mono text-xs"
                    placeholder='[[0.1, 0.2, ...], [0.3, 0.4, ...]]'
                  />
                  <p className="text-xs text-slate-500 mt-1">提示：可以在"推理日志"标签中点击"选用"加载历史输入</p>
                </div>

                <button
                  onClick={handleRunABTest}
                  disabled={!comparePolicyA || !comparePolicyB || !compareObservations || isComparing}
                  className="btn-primary w-full"
                >
                  {isComparing ? '对比中...' : '发起对比'}
                </button>

                {abTestResult && (
                  <div className="space-y-3">
                    <div className="card bg-slate-700/30">
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-sm font-semibold">差异率</span>
                        <span className="text-lg font-bold text-yellow-400">
                          {(abTestResult.diff_rate * 100).toFixed(1)}%
                        </span>
                      </div>
                    </div>

                    <div className="grid grid-cols-2 gap-3">
                      {['policy_a', 'policy_b'].map((key) => {
                        const result = abTestResult[key as 'policy_a' | 'policy_b'];
                        const policyName = key === 'policy_a'
                          ? policies.find(p => p.id === comparePolicyA)?.name || `#${comparePolicyA}`
                          : policies.find(p => p.id === comparePolicyB)?.name || `#${comparePolicyB}`;
                        return (
                          <div key={key} className="card">
                            <p className="text-xs text-slate-400 mb-1">{key === 'policy_a' ? '策略 A' : '策略 B'}</p>
                            <p className="font-semibold text-sm mb-2">{policyName}</p>
                            {result.timeout ? (
                              <p className="text-red-400 text-sm">超时</p>
                            ) : result.error ? (
                              <p className="text-red-400 text-sm" title={result.error}>错误</p>
                            ) : (
                              <>
                                <p className="text-xs text-slate-400">延迟</p>
                                <p className="font-mono text-green-400 mb-2">{result.latency_ms.toFixed(1)}ms</p>
                              </>
                            )}
                          </div>
                        );
                      })}
                    </div>

                    {abTestResult.policy_a.actions && abTestResult.policy_b.actions && (
                      <div className="card">
                        <p className="text-sm font-semibold mb-2">动作对比</p>
                        <div className="overflow-x-auto max-h-48">
                          <table className="w-full text-xs">
                            <thead>
                              <tr className="text-slate-400 border-b border-slate-600">
                                <th className="text-left py-1">Agent</th>
                                <th className="text-center py-1">策略 A</th>
                                <th className="text-center py-1">策略 B</th>
                                <th className="text-center py-1">差异</th>
                              </tr>
                            </thead>
                            <tbody>
                              {abTestResult.policy_a.actions.map((a, i) => {
                                const b = abTestResult.policy_b!.actions![i];
                                const diff = a !== b;
                                return (
                                  <tr
                                    key={i}
                                    className={`border-b border-slate-700/50 ${diff ? 'bg-yellow-900/30' : ''}`}
                                  >
                                    <td className="py-1 text-slate-300">{i}</td>
                                    <td className="py-1 text-center font-mono">{a}</td>
                                    <td className="py-1 text-center font-mono">{b}</td>
                                    <td className="py-1 text-center">
                                      {diff ? <span className="text-yellow-400">✕</span> : <span className="text-green-400">✓</span>}
                                    </td>
                                  </tr>
                                );
                              })}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    )}

                    <div className="card">
                      <p className="text-sm font-semibold mb-2">延迟对比</p>
                      <ResponsiveContainer width="100%" height={120}>
                        <BarChart data={[
                          { name: '策略A', latency: abTestResult.policy_a.latency_ms },
                          { name: '策略B', latency: abTestResult.policy_b.latency_ms },
                        ]}>
                          <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                          <XAxis dataKey="name" tick={{ fontSize: 11, fill: '#94a3b8' }} />
                          <YAxis tick={{ fontSize: 10, fill: '#94a3b8' }} />
                          <Tooltip
                            contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #334155' }}
                            formatter={(value: number) => [`${value.toFixed(1)}ms`, '延迟']}
                          />
                          <Bar dataKey="latency" fill="#8b5cf6" radius={[4, 4, 0, 0]} />
                        </BarChart>
                      </ResponsiveContainer>
                    </div>

                    {compareHistory.length > 1 && (
                      <div className="card">
                        <p className="text-sm font-semibold mb-2">差异率趋势</p>
                        <ResponsiveContainer width="100%" height={120}>
                          <LineChart data={compareHistory}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                            <XAxis dataKey="time" tick={{ fontSize: 9, fill: '#94a3b8' }} />
                            <YAxis
                              tick={{ fontSize: 10, fill: '#94a3b8' }}
                              domain={[0, 1]}
                              tickFormatter={(v) => `${(v * 100).toFixed(0)}%`}
                            />
                            <Tooltip
                              contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #334155' }}
                              formatter={(value: number) => [`${(value * 100).toFixed(1)}%`, '差异率']}
                            />
                            <Line type="monotone" dataKey="diff_rate" stroke="#f59e0b" strokeWidth={2} dot />
                          </LineChart>
                        </ResponsiveContainer>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}
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
                <p className="text-xs text-slate-500 mt-1">同名部署会自动递增版本号</p>
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
