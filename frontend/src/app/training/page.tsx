'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { Experiment, TrainingLog } from '@/types';
import { experimentApi, visualizationApi } from '@/lib/api';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';

export default function TrainingPage() {
  const [experiments, setExperiments] = useState<Experiment[]>([]);
  const [selectedExpId, setSelectedExpId] = useState<number | null>(null);
  const [curveData, setCurveData] = useState<any[]>([]);
  const [progress, setProgress] = useState<any>(null);
  const [agentCurveData, setAgentCurveData] = useState<Record<string, any[]>>({});
  const intervalRef = useRef<NodeJS.Timeout | null>(null);

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
      const [progRes, curveRes] = await Promise.all([
        experimentApi.getProgress(selectedExpId),
        visualizationApi.getLearningCurves(selectedExpId),
      ]);
      setProgress(progRes.data);

      const curves = curveRes.data;
      const totalRewards = curves.episodes.map((ep: number, i: number) => ({
        episode: ep, total_reward: curves.total_rewards[i],
        steps: curves.steps[i], win_rate: curves.win_rates[i],
      }));
      setCurveData(totalRewards);

      if (curves.agent_rewards && curves.agent_rewards.length > 0) {
        const agentKeys = Object.keys(curves.agent_rewards[0]);
        const agentCurves: Record<string, any[]> = {};
        agentKeys.forEach((key) => {
          agentCurves[key] = curves.episodes.map((ep: number, i: number) => ({
            episode: ep, reward: curves.agent_rewards[i][key],
          }));
        });
        setAgentCurveData(agentCurves);
      }
    } catch (e) { console.error(e); }
  }, [selectedExpId]);

  useEffect(() => {
    fetchProgress();
    if (selectedExpId) {
      const exp = experiments.find((e) => e.id === selectedExpId);
      if (exp?.status === 'running') {
        intervalRef.current = setInterval(fetchProgress, 3000);
      }
    }
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [selectedExpId, fetchProgress, experiments]);

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

  const selectedExp = experiments.find((e) => e.id === selectedExpId);

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">训练监控</h1>

      <div className="flex gap-4 mb-6">
        <div className="w-64">
          <label className="text-sm text-slate-400">选择实验</label>
          <select
            value={selectedExpId || ''}
            onChange={(e) => setSelectedExpId(parseInt(e.target.value))}
            className="select-field w-full mt-1"
          >
            <option value="">请选择...</option>
            {experiments.map((exp) => (
              <option key={exp.id} value={exp.id}>{exp.name} ({exp.algorithm})</option>
            ))}
          </select>
        </div>

        {selectedExp && (
          <div className="flex items-end gap-2">
            {selectedExp.status === 'running' && <button onClick={handlePause} className="btn-secondary">暂停</button>}
            {selectedExp.status === 'paused' && <button onClick={handleResume} className="btn-success">恢复</button>}
            {(selectedExp.status === 'running' || selectedExp.status === 'paused') && (
              <button onClick={handleStop} className="btn-danger">终止</button>
            )}
          </div>
        )}
      </div>

      {progress && (
        <div className="card mb-4">
          <div className="flex items-center gap-6">
            <div>
              <span className="text-sm text-slate-400">状态</span>
              <p className={`font-semibold ${progress.status === 'running' ? 'text-green-400' : progress.status === 'paused' ? 'text-yellow-400' : 'text-slate-300'}`}>
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
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="card">
          <h3 className="font-semibold mb-2">团队总奖励曲线</h3>
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={curveData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis dataKey="episode" stroke="#94a3b8" fontSize={10} />
              <YAxis stroke="#94a3b8" fontSize={10} />
              <Tooltip contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #475569' }} />
              <Line type="monotone" dataKey="total_reward" stroke="#3b82f6" strokeWidth={2} dot={false} name="总奖励" />
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
          <h3 className="font-semibold mb-2">各智能体奖励曲线</h3>
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={curveData.length > 0 ? Object.entries(agentCurveData).length > 0 ?
              Object.values(agentCurveData)[0]?.map((_, i) => {
                const point: any = { episode: curveData[i]?.episode };
                Object.entries(agentCurveData).forEach(([key, data]) => { point[`agent_${key}`] = data[i]?.reward; });
                return point;
              }) || [] : [] : []}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis dataKey="episode" stroke="#94a3b8" fontSize={10} />
              <YAxis stroke="#94a3b8" fontSize={10} />
              <Tooltip contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #475569' }} />
              <Legend />
              {Object.keys(agentCurveData).map((key, idx) => {
                const colors = ['#3b82f6', '#ef4444', '#10b981', '#f59e0b', '#8b5cf6', '#ec4899', '#06b6d4', '#f97316'];
                return <Line key={key} type="monotone" dataKey={`agent_${key}`} stroke={colors[idx % colors.length]} strokeWidth={1.5} dot={false} name={`Agent ${key}`} />;
              })}
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
    </div>
  );
}
