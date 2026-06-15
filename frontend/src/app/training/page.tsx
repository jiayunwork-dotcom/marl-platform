'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { Experiment, TrainingLog, TrainingSummary, LearningCurveData, CompareCurveItem } from '@/types';
import { experimentApi, visualizationApi } from '@/lib/api';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';

const COLORS = ['#3b82f6', '#ef4444', '#10b981', '#f59e0b', '#8b5cf6', '#ec4899', '#06b6d4', '#f97316'];
const POLL_INTERVAL = 3000;
const DEFAULT_LOAD_COUNT = 200;

function formatDuration(seconds: number | null): string {
  if (seconds === null || seconds === undefined) return '-';
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (h > 0) return `${h}h ${m}m ${s}s`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

function SummaryCard({ summary }: { summary: TrainingSummary | null }) {
  if (!summary) return null;
  return (
    <div className="card mb-4">
      <h3 className="font-semibold mb-3 text-sm">训练统计摘要</h3>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div>
          <span className="text-xs text-slate-400">最终平均奖励</span>
          <p className="text-lg font-bold text-blue-400">{summary.final_avg_reward?.toFixed(2) ?? '-'}</p>
          <span className="text-[10px] text-slate-500">最后50 episode均值</span>
        </div>
        <div>
          <span className="text-xs text-slate-400">最高单次奖励</span>
          <p className="text-lg font-bold text-green-400">{summary.max_episode_reward?.toFixed(2) ?? '-'}</p>
        </div>
        <div>
          <span className="text-xs text-slate-400">收敛 Episode</span>
          <p className="text-lg font-bold text-yellow-400">{summary.convergence_episode ?? '未收敛'}</p>
          <span className="text-[10px] text-slate-500">连续20 ep超均值80%</span>
        </div>
        <div>
          <span className="text-xs text-slate-400">总训练时长</span>
          <p className="text-lg font-bold text-purple-400">{formatDuration(summary.total_duration_seconds)}</p>
        </div>
      </div>
    </div>
  );
}

export default function TrainingPage() {
  const [experiments, setExperiments] = useState<Experiment[]>([]);
  const [selectedExpId, setSelectedExpId] = useState<number | null>(null);
  const [curveData, setCurveData] = useState<any[]>([]);
  const [agentCurveData, setAgentCurveData] = useState<Record<string, any[]>>({});
  const [progress, setProgress] = useState<any>(null);
  const [totalCount, setTotalCount] = useState<number>(0);
  const [showAllData, setShowAllData] = useState<boolean>(false);
  const [experimentDetail, setExperimentDetail] = useState<Experiment | null>(null);
  const intervalRef = useRef<NodeJS.Timeout | null>(null);

  const [compareExpIds, setCompareExpIds] = useState<number[]>([]);
  const [compareData, setCompareData] = useState<Record<number, CompareCurveItem> | null>(null);
  const [compareLoading, setCompareLoading] = useState(false);

  const fetchExps = useCallback(async () => {
    try {
      const res = await experimentApi.list();
      setExperiments(res.data);
    } catch (e) { console.error(e); }
  }, []);

  useEffect(() => { fetchExps(); }, [fetchExps]);

  const fetchProgress = useCallback(async () => {
    if (!selectedExpId) return;
    try {
      const progRes = await experimentApi.getProgress(selectedExpId);
      setProgress(progRes.data);

      const exp = experiments.find((e) => e.id === selectedExpId);
      const isRunning = exp?.status === 'running' || progRes.data.status === 'running';

      let curveRes;
      if (isRunning) {
        curveRes = await visualizationApi.getLearningCurves(selectedExpId);
      } else if (showAllData) {
        curveRes = await visualizationApi.getLearningCurves(selectedExpId);
      } else {
        curveRes = await visualizationApi.getLearningCurves(selectedExpId, 0, DEFAULT_LOAD_COUNT);
      }

      const curves: LearningCurveData = curveRes.data;
      setTotalCount(curves.total_count || 0);

      const totalRewards = curves.episodes.map((ep: number, i: number) => ({
        episode: ep,
        total_reward: curves.total_rewards[i],
        steps: curves.steps[i],
        win_rate: curves.win_rates[i],
      }));
      setCurveData(totalRewards);

      if (curves.agent_rewards && curves.agent_rewards.length > 0) {
        const agentKeys = Object.keys(curves.agent_rewards[0]);
        const agentCurves: Record<string, any[]> = {};
        agentKeys.forEach((key) => {
          agentCurves[key] = curves.episodes.map((ep: number, i: number) => ({
            episode: ep,
            reward: curves.agent_rewards[i][key],
          }));
        });
        setAgentCurveData(agentCurves);
      }
    } catch (e) { console.error(e); }
  }, [selectedExpId, experiments, showAllData]);

  useEffect(() => {
    if (!selectedExpId) return;

    fetchProgress();

    const exp = experiments.find((e) => e.id === selectedExpId);
    if (exp?.status === 'running' || exp?.status === 'queued') {
      intervalRef.current = setInterval(fetchProgress, POLL_INTERVAL);
    }

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [selectedExpId, fetchProgress, experiments]);

  useEffect(() => {
    if (!selectedExpId) {
      setExperimentDetail(null);
      return;
    }
    experimentApi.get(selectedExpId).then((res) => {
      setExperimentDetail(res.data);
    }).catch(console.error);
  }, [selectedExpId, experiments]);

  useEffect(() => {
    if (!selectedExpId) return;
    const exp = experiments.find((e) => e.id === selectedExpId);
    if (exp?.status === 'completed' || exp?.status === 'stopped' || exp?.status === 'error') {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    }
  }, [experiments, selectedExpId]);

  const handlePause = async () => {
    if (!selectedExpId) return;
    try { await experimentApi.pause(selectedExpId); fetchExps(); } catch (e) { console.error(e); }
  };

  const handleResume = async () => {
    if (!selectedExpId) return;
    try { await experimentApi.resume(selectedExpId); fetchExps(); } catch (e) { console.error(e); }
  };

  const handleStop = async () => {
    if (!selectedExpId) return;
    try { await experimentApi.stop(selectedExpId); fetchExps(); } catch (e) { console.error(e); }
  };

  const handleLoadAll = () => {
    setShowAllData(true);
  };

  const handleCompare = async () => {
    if (compareExpIds.length < 2 || compareExpIds.length > 4) return;
    setCompareLoading(true);
    try {
      const res = await visualizationApi.compareCurves(compareExpIds);
      setCompareData(res.data);
    } catch (e) {
      console.error(e);
    } finally {
      setCompareLoading(false);
    }
  };

  const toggleCompareExp = (id: number) => {
    setCompareExpIds((prev) => {
      if (prev.includes(id)) return prev.filter((x) => x !== id);
      if (prev.length >= 4) return prev;
      return [...prev, id];
    });
    setCompareData(null);
  };

  const selectedExp = experiments.find((e) => e.id === selectedExpId);

  const completedExperiments = experiments.filter(
    (e) => e.status === 'completed' || e.status === 'stopped'
  );

  const mergedAgentData = curveData.length > 0 && Object.keys(agentCurveData).length > 0
    ? Object.values(agentCurveData)[0]?.map((_, i) => {
        const point: any = { episode: curveData[i]?.episode, total_reward: curveData[i]?.total_reward };
        Object.entries(agentCurveData).forEach(([key, data]) => {
          point[`agent_${key}`] = data[i]?.reward;
        });
        return point;
      }) || []
    : [];

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">训练监控</h1>

      <div className="flex gap-4 mb-6">
        <div className="w-64">
          <label className="text-sm text-slate-400">选择实验</label>
          <select
            value={selectedExpId || ''}
            onChange={(e) => {
              setSelectedExpId(parseInt(e.target.value));
              setShowAllData(false);
              setCurveData([]);
              setAgentCurveData({});
              setProgress(null);
              setExperimentDetail(null);
            }}
            className="select-field w-full mt-1"
          >
            <option value="">请选择...</option>
            {experiments.map((exp) => (
              <option key={exp.id} value={exp.id}>
                {exp.name} ({exp.algorithm}) [{exp.status}]
              </option>
            ))}
          </select>
        </div>

        {selectedExp && (
          <div className="flex items-end gap-2">
            {selectedExp.status === 'running' && (
              <button onClick={handlePause} className="btn-secondary">暂停</button>
            )}
            {selectedExp.status === 'paused' && (
              <button onClick={handleResume} className="btn-success">恢复</button>
            )}
            {(selectedExp.status === 'running' || selectedExp.status === 'paused') && (
              <button onClick={handleStop} className="btn-danger">终止</button>
            )}
            {selectedExp.status === 'running' && (
              <span className="text-xs text-green-400 animate-pulse self-center">● 实时刷新中</span>
            )}
          </div>
        )}
      </div>

      {progress && (
        <div className="card mb-4">
          <div className="flex items-center gap-6">
            <div>
              <span className="text-sm text-slate-400">状态</span>
              <p className={`font-semibold ${progress.status === 'running' ? 'text-green-400' : progress.status === 'paused' ? 'text-yellow-400' : progress.status === 'completed' ? 'text-blue-400' : 'text-slate-300'}`}>
                {progress.status}
              </p>
            </div>
            <div>
              <span className="text-sm text-slate-400">进度</span>
              <p className="font-semibold">{progress.current_episode} / {progress.total_episodes}</p>
            </div>
            <div className="flex-1">
              <div className="w-full bg-slate-700 rounded-full h-3">
                <div
                  className="bg-blue-500 rounded-full h-3 transition-all"
                  style={{ width: `${(progress.current_episode / progress.total_episodes) * 100}%` }}
                />
              </div>
            </div>
            {!showAllData && totalCount > DEFAULT_LOAD_COUNT && selectedExp?.status !== 'running' && (
              <button onClick={handleLoadAll} className="btn-secondary text-sm whitespace-nowrap">
                加载全部 ({totalCount})
              </button>
            )}
            {showAllData && <span className="text-xs text-slate-400">已加载全部 {totalCount} 条</span>}
            {!showAllData && totalCount <= DEFAULT_LOAD_COUNT && totalCount > 0 && (
              <span className="text-xs text-slate-400">共 {totalCount} 条</span>
            )}
          </div>
        </div>
      )}

      {experimentDetail?.summary && <SummaryCard summary={experimentDetail.summary} />}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="card">
          <h3 className="font-semibold mb-2">团队总奖励 + 智能体奖励</h3>
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={mergedAgentData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis dataKey="episode" stroke="#94a3b8" fontSize={10} />
              <YAxis stroke="#94a3b8" fontSize={10} />
              <Tooltip contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #475569' }} />
              <Legend />
              <Line type="monotone" dataKey="total_reward" stroke="#3b82f6" strokeWidth={2} dot={false} name="团队总奖励" />
              {Object.keys(agentCurveData).map((key, idx) => (
                <Line
                  key={key}
                  type="monotone"
                  dataKey={`agent_${key}`}
                  stroke={COLORS[(idx + 1) % COLORS.length]}
                  strokeWidth={1.5}
                  dot={false}
                  name={`Agent ${key}`}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>

        <div className="card">
          <h3 className="font-semibold mb-2">胜率趋势</h3>
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={curveData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis dataKey="episode" stroke="#94a3b8" fontSize={10} />
              <YAxis stroke="#94a3b8" fontSize={10} domain={[0, 1]} />
              <Tooltip contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #475569' }} />
              <Line type="monotone" dataKey="win_rate" stroke="#10b981" strokeWidth={2} dot={false} name="胜率" />
            </LineChart>
          </ResponsiveContainer>
        </div>

        <div className="card">
          <h3 className="font-semibold mb-2">Episode 长度趋势</h3>
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={curveData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis dataKey="episode" stroke="#94a3b8" fontSize={10} />
              <YAxis stroke="#94a3b8" fontSize={10} />
              <Tooltip contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #475569' }} />
              <Line type="monotone" dataKey="steps" stroke="#f59e0b" strokeWidth={2} dot={false} name="步数" />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="mt-8">
        <h2 className="text-xl font-bold mb-4">多实验曲线对比</h2>
        <div className="card">
          <p className="text-sm text-slate-400 mb-3">选择 2-4 个已完成的实验进行曲线叠加对比</p>

          {completedExperiments.length === 0 ? (
            <p className="text-sm text-slate-500">暂无已完成的实验可供对比</p>
          ) : (
            <>
              <div className="flex flex-wrap gap-3 mb-4">
                {completedExperiments.map((exp) => (
                  <label
                    key={exp.id}
                    className={`flex items-center gap-2 px-3 py-1.5 rounded border cursor-pointer transition-colors text-sm ${
                      compareExpIds.includes(exp.id)
                        ? 'border-blue-500 bg-blue-500/10 text-blue-400'
                        : 'border-slate-600 bg-slate-800 text-slate-300 hover:border-slate-500'
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={compareExpIds.includes(exp.id)}
                      onChange={() => toggleCompareExp(exp.id)}
                      className="hidden"
                    />
                    <span>{exp.name}</span>
                    <span className="text-xs text-slate-400">({exp.algorithm})</span>
                  </label>
                ))}
              </div>

              <button
                onClick={handleCompare}
                disabled={compareExpIds.length < 2 || compareExpIds.length > 4 || compareLoading}
                className="btn-primary text-sm disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {compareLoading ? '加载中...' : '生成对比曲线'}
              </button>

              {compareExpIds.length > 0 && compareExpIds.length < 2 && (
                <span className="ml-3 text-xs text-yellow-400">至少选择 2 个实验</span>
              )}
              {compareExpIds.length > 4 && (
                <span className="ml-3 text-xs text-yellow-400">最多选择 4 个实验</span>
              )}

              {compareData && (
                <div className="mt-6">
                  <h3 className="font-semibold mb-2 text-sm">Episode 奖励曲线对比</h3>
                  <ResponsiveContainer width="100%" height={400}>
                    <LineChart>
                      <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                      <XAxis dataKey="episode" stroke="#94a3b8" fontSize={10} type="number" domain={['dataMin', 'dataMax']} />
                      <YAxis stroke="#94a3b8" fontSize={10} />
                      <Tooltip contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #475569' }} />
                      <Legend />
                      {Object.entries(compareData).map(([eid, data], idx) => {
                        const chartData = data.episodes.map((ep: number, i: number) => ({
                          episode: ep,
                          reward: data.total_rewards[i],
                        }));
                        return (
                          <Line
                            key={eid}
                            data={chartData}
                            dataKey="reward"
                            stroke={COLORS[idx % COLORS.length]}
                            strokeWidth={2}
                            dot={false}
                            name={`${data.name} (${data.algorithm})`}
                          />
                        );
                      })}
                    </LineChart>
                  </ResponsiveContainer>

                  <div className="mt-4 grid grid-cols-2 md:grid-cols-4 gap-3">
                    {Object.entries(compareData).map(([eid, data], idx) => (
                      <div key={eid} className="text-xs bg-slate-800 rounded p-2">
                        <div className="flex items-center gap-2">
                          <div className="w-3 h-3 rounded-full" style={{ backgroundColor: COLORS[idx % COLORS.length] }} />
                          <span className="font-semibold">{data.name}</span>
                        </div>
                        <span className="text-slate-400 ml-5">{data.algorithm}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
