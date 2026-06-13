'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { Experiment } from '@/types';
import { experimentApi, visualizationApi } from '@/lib/api';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';

export default function VisualizationPage() {
  const [experiments, setExperiments] = useState<Experiment[]>([]);
  const [selectedExpId, setSelectedExpId] = useState<number | null>(null);
  const [activeViz, setActiveViz] = useState<'heatmap' | 'qmap' | 'compare'>('heatmap');
  const [heatmapData, setHeatmapData] = useState<any>(null);
  const [qMapData, setQMapData] = useState<any>(null);
  const [compareIds, setCompareIds] = useState<number[]>([]);
  const [compareData, setCompareData] = useState<any>(null);
  const [selectedAgent, setSelectedAgent] = useState(0);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  const fetchExps = useCallback(async () => {
    try {
      const res = await experimentApi.list();
      setExperiments(res.data);
    } catch (e) { console.error(e); }
  }, []);

  useEffect(() => { fetchExps(); }, [fetchExps]);

  const fetchHeatmap = useCallback(async () => {
    if (!selectedExpId) return;
    try {
      const res = await visualizationApi.getTrajectoryHeatmap(selectedExpId);
      setHeatmapData(res.data);
    } catch (e) { console.error(e); }
  }, [selectedExpId]);

  const fetchQMap = useCallback(async () => {
    if (!selectedExpId) return;
    try {
      const res = await visualizationApi.getQValueMap(selectedExpId, selectedAgent);
      setQMapData(res.data);
    } catch (e) { console.error(e); }
  }, [selectedExpId, selectedAgent]);

  const fetchCompare = useCallback(async () => {
    if (compareIds.length < 2) return;
    try {
      const res = await visualizationApi.compareCurves(compareIds);
      setCompareData(res.data);
    } catch (e) { console.error(e); }
  }, [compareIds]);

  useEffect(() => {
    if (activeViz === 'heatmap') fetchHeatmap();
    else if (activeViz === 'qmap') fetchQMap();
    else if (activeViz === 'compare' && compareIds.length >= 2) fetchCompare();
  }, [activeViz, fetchHeatmap, fetchQMap, fetchCompare]);

  const drawHeatmap = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas || !heatmapData) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const { width, height, heatmaps, n_agents } = heatmapData;
    const currentHeatmap = heatmaps[selectedAgent] || heatmaps[0] || [];
    const cellSize = Math.min((canvas.width - 40) / width, (canvas.height - 40) / height, 40);
    const offsetX = (canvas.width - cellSize * width) / 2;
    const offsetY = (canvas.height - cellSize * height) / 2;

    ctx.fillStyle = '#1e293b';
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    for (let y = 0; y < height; y++) {
      for (let x = 0; x < width; x++) {
        const val = currentHeatmap[y]?.[x] || 0;
        const px = offsetX + x * cellSize;
        const py = offsetY + y * cellSize;
        const r = Math.floor(val * 239);
        const g = Math.floor(val * 68);
        const b = Math.floor(val * 68);
        ctx.fillStyle = `rgb(${r}, ${g}, ${b})`;
        ctx.fillRect(px, py, cellSize - 1, cellSize - 1);
      }
    }
  }, [heatmapData, selectedAgent]);

  const drawQMap = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas || !qMapData) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const { width, height, q_map } = qMapData;
    const cellSize = Math.min((canvas.width - 40) / width, (canvas.height - 40) / height, 40);
    const offsetX = (canvas.width - cellSize * width) / 2;
    const offsetY = (canvas.height - cellSize * height) / 2;

    ctx.fillStyle = '#1e293b';
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    for (let y = 0; y < height; y++) {
      for (let x = 0; x < width; x++) {
        const val = q_map[y]?.[x] || 0;
        const px = offsetX + x * cellSize;
        const py = offsetY + y * cellSize;
        const r = Math.floor(val * 255);
        const b = Math.floor((1 - val) * 255);
        ctx.fillStyle = `rgb(${r}, 50, ${b})`;
        ctx.fillRect(px, py, cellSize - 1, cellSize - 1);
      }
    }
  }, [qMapData]);

  useEffect(() => {
    if (activeViz === 'heatmap') drawHeatmap();
    else if (activeViz === 'qmap') drawQMap();
  }, [activeViz, drawHeatmap, drawQMap]);

  const toggleCompareId = (id: number) => {
    setCompareIds((prev) => {
      if (prev.includes(id)) return prev.filter((i) => i !== id);
      if (prev.length >= 4) return prev;
      return [...prev, id];
    });
  };

  const compareChartData = compareData ? Object.entries(compareData).flatMap(([, data]: [string, any]) =>
    data.episodes.map((ep: number, i: number) => ({
      episode: ep,
      [`${data.name}`]: data.total_rewards[i],
    }))
  ) : [];

  const mergedData = compareChartData.reduce((acc: any, item: any) => {
    const existing = acc.find((a: any) => a.episode === item.episode);
    if (existing) Object.assign(existing, item);
    else acc.push(item);
    return acc;
  }, [] as any[]);

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">可视化分析</h1>

      <div className="flex gap-2 mb-4">
        <button onClick={() => setActiveViz('heatmap')} className={`px-4 py-2 rounded-lg text-sm ${activeViz === 'heatmap' ? 'bg-blue-600 text-white' : 'bg-slate-700 text-slate-300'}`}>
          轨迹热力图
        </button>
        <button onClick={() => setActiveViz('qmap')} className={`px-4 py-2 rounded-lg text-sm ${activeViz === 'qmap' ? 'bg-blue-600 text-white' : 'bg-slate-700 text-slate-300'}`}>
          Q值空间地图
        </button>
        <button onClick={() => setActiveViz('compare')} className={`px-4 py-2 rounded-lg text-sm ${activeViz === 'compare' ? 'bg-blue-600 text-white' : 'bg-slate-700 text-slate-300'}`}>
          学习曲线对比
        </button>
      </div>

      <div className="flex items-center gap-3 mb-4">
        <label className="text-sm text-slate-400">选择实验</label>
        <select value={selectedExpId || ''} onChange={(e) => setSelectedExpId(parseInt(e.target.value))} className="select-field">
          <option value="">请选择...</option>
          {experiments.map((exp) => (
            <option key={exp.id} value={exp.id}>{exp.name}</option>
          ))}
        </select>
      </div>

      {(activeViz === 'heatmap' || activeViz === 'qmap') && heatmapData && (
        <div className="flex items-center gap-3 mb-3">
          <label className="text-sm text-slate-400">选择智能体</label>
          <select value={selectedAgent} onChange={(e) => setSelectedAgent(parseInt(e.target.value))} className="select-field">
            {Array.from({ length: heatmapData.n_agents }, (_, i) => (
              <option key={i} value={i}>Agent {i}</option>
            ))}
          </select>
        </div>
      )}

      {(activeViz === 'heatmap' || activeViz === 'qmap') && (
        <div className="card">
          <canvas ref={canvasRef} width={700} height={500} className="rounded-lg border border-slate-600 w-full" />
          <div className="mt-2 flex items-center gap-2 text-xs text-slate-400">
            <span>低</span>
            <div className="w-32 h-3 bg-gradient-to-r from-slate-900 to-red-500 rounded" />
            <span>高</span>
          </div>
        </div>
      )}

      {activeViz === 'compare' && (
        <div>
          <div className="card mb-4">
            <h3 className="font-semibold mb-3">选择对比实验 (2-4个)</h3>
            <div className="flex flex-wrap gap-2">
              {experiments.map((exp) => (
                <button
                  key={exp.id}
                  onClick={() => toggleCompareId(exp.id)}
                  className={`px-3 py-1.5 rounded-lg text-sm ${
                    compareIds.includes(exp.id) ? 'bg-blue-600 text-white' : 'bg-slate-700 text-slate-300'
                  }`}
                >
                  {exp.name} ({exp.algorithm})
                </button>
              ))}
            </div>
          </div>

          {compareData && mergedData.length > 0 && (
            <div className="card">
              <h3 className="font-semibold mb-2">学习曲线对比</h3>
              <ResponsiveContainer width="100%" height={400}>
                <LineChart data={mergedData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                  <XAxis dataKey="episode" stroke="#94a3b8" fontSize={10} />
                  <YAxis stroke="#94a3b8" fontSize={10} />
                  <Tooltip contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #475569' }} />
                  <Legend />
                  {Object.entries(compareData).map(([, data]: [string, any], idx) => {
                    const colors = ['#3b82f6', '#ef4444', '#10b981', '#f59e0b'];
                    return <Line key={idx} type="monotone" dataKey={data.name} stroke={colors[idx % colors.length]} strokeWidth={2} dot={false} />;
                  })}
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
