'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { Experiment, Evaluation, StepData } from '@/types';
import { experimentApi, evaluationApi } from '@/lib/api';

export default function EvaluationPage() {
  const [experiments, setExperiments] = useState<Experiment[]>([]);
  const [evaluations, setEvaluations] = useState<Evaluation[]>([]);
  const [selectedExpId, setSelectedExpId] = useState<number | null>(null);
  const [numEpisodes, setNumEpisodes] = useState(10);
  const [isEvaluating, setIsEvaluating] = useState(false);

  const [replayData, setReplayData] = useState<StepData[] | null>(null);
  const [currentStep, setCurrentStep] = useState(0);
  const [playbackSpeed, setPlaybackSpeed] = useState(1);
  const [isPlaying, setIsPlaying] = useState(false);
  const [hoveredAgent, setHoveredAgent] = useState<number | null>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animRef = useRef<NodeJS.Timeout | null>(null);

  const fetchExps = useCallback(async () => {
    try {
      const res = await experimentApi.list();
      setExperiments(res.data);
    } catch (e) { console.error(e); }
  }, []);

  const fetchEvals = useCallback(async () => {
    try {
      const res = await evaluationApi.list();
      setEvaluations(res.data);
    } catch (e) { console.error(e); }
  }, []);

  useEffect(() => { fetchExps(); fetchEvals(); }, [fetchExps, fetchEvals]);

  const handleEvaluate = async () => {
    if (!selectedExpId) return;
    setIsEvaluating(true);
    try {
      await evaluationApi.create({ experiment_id: selectedExpId, num_episodes: numEpisodes });
      fetchEvals();
    } catch (e) {
      console.error(e);
      alert('评估失败，请确认实验已完成训练');
    }
    setIsEvaluating(false);
  };

  const handleReplay = async (evalId: number, episodeIdx: number) => {
    try {
      const res = await evaluationApi.getReplay(evalId, episodeIdx);
      setReplayData(res.data.steps || []);
      setCurrentStep(0);
      setIsPlaying(false);
    } catch (e) { console.error(e); }
  };

  const drawCanvas = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas || !replayData || replayData.length === 0) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const step = replayData[currentStep];
    if (!step) return;

    const gridW = 10, gridH = 10;
    const cellSize = Math.min((canvas.width - 40) / gridW, (canvas.height - 40) / gridH, 40);
    const offsetX = (canvas.width - cellSize * gridW) / 2;
    const offsetY = (canvas.height - cellSize * gridH) / 2;

    ctx.fillStyle = '#1e293b';
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    for (let y = 0; y < gridH; y++) {
      for (let x = 0; x < gridW; x++) {
        ctx.fillStyle = '#e5e7eb';
        ctx.fillRect(offsetX + x * cellSize, offsetY + y * cellSize, cellSize - 1, cellSize - 1);
      }
    }

    const agentColors = ['#3b82f6', '#ef4444', '#10b981', '#f59e0b', '#8b5cf6', '#ec4899', '#06b6d4', '#f97316'];
    step.agent_positions.forEach((pos, i) => {
      const px = offsetX + pos[1] * cellSize;
      const py = offsetY + pos[0] * cellSize;
      ctx.fillStyle = agentColors[i % agentColors.length];
      ctx.beginPath();
      ctx.arc(px + cellSize / 2, py + cellSize / 2, cellSize * 0.35, 0, Math.PI * 2);
      ctx.fill();
      ctx.fillStyle = '#fff';
      ctx.font = `bold ${Math.max(cellSize * 0.25, 7)}px sans-serif`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(`${i}`, px + cellSize / 2, py + cellSize / 2);
    });
  }, [replayData, currentStep]);

  useEffect(() => { drawCanvas(); }, [drawCanvas]);

  useEffect(() => {
    if (isPlaying && replayData) {
      const interval = Math.max(50, 500 / playbackSpeed);
      animRef.current = setInterval(() => {
        setCurrentStep((prev) => {
          if (prev >= replayData.length - 1) {
            setIsPlaying(false);
            return prev;
          }
          return prev + 1;
        });
      }, interval);
    }
    return () => { if (animRef.current) clearInterval(animRef.current); };
  }, [isPlaying, playbackSpeed, replayData]);

  const stepForward = () => {
    if (replayData && currentStep < replayData.length - 1) setCurrentStep((p) => p + 1);
  };
  const stepBackward = () => {
    if (currentStep > 0) setCurrentStep((p) => p - 1);
  };

  const currentStepData = replayData?.[currentStep];
  const actionNames = ['↑', '↓', '←', '→', '停留'];

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">评估回放</h1>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div>
          <div className="card mb-4">
            <h3 className="font-semibold mb-3">创建评估</h3>
            <div className="flex items-end gap-3">
              <div className="flex-1">
                <label className="text-sm text-slate-400">选择实验</label>
                <select value={selectedExpId || ''} onChange={(e) => setSelectedExpId(parseInt(e.target.value))} className="select-field w-full mt-1">
                  <option value="">请选择...</option>
                  {experiments.filter((e) => e.status === 'completed').map((exp) => (
                    <option key={exp.id} value={exp.id}>{exp.name} ({exp.algorithm})</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="text-sm text-slate-400">评估回合数</label>
                <input type="number" value={numEpisodes} onChange={(e) => setNumEpisodes(parseInt(e.target.value))} className="input-field w-20 mt-1" />
              </div>
              <button onClick={handleEvaluate} disabled={isEvaluating} className="btn-primary">
                {isEvaluating ? '评估中...' : '开始评估'}
              </button>
            </div>
          </div>

          <div className="card">
            <h3 className="font-semibold mb-3">评估结果</h3>
            <div className="space-y-2">
              {evaluations.map((ev) => (
                <div key={ev.id} className="bg-slate-700/50 rounded-lg p-3">
                  <div className="flex justify-between items-center mb-2">
                    <span className="text-sm">实验 #{ev.experiment_id} | {ev.num_episodes} 回合</span>
                    <span className="text-xs text-slate-400">{new Date(ev.created_at).toLocaleString()}</span>
                  </div>
                  <div className="grid grid-cols-4 gap-2 text-xs mb-2">
                    <div>平均奖励<br /><span className="text-blue-400 font-bold">{ev.avg_reward.toFixed(2)}</span></div>
                    <div>成功率<br /><span className="text-green-400 font-bold">{(ev.success_rate * 100).toFixed(1)}%</span></div>
                    <div>碰撞率<br /><span className="text-red-400 font-bold">{(ev.collision_rate * 100).toFixed(1)}%</span></div>
                    <div>平均步数<br /><span className="text-yellow-400 font-bold">{ev.avg_steps.toFixed(1)}</span></div>
                  </div>
                  <div className="flex gap-1">
                    {ev.episode_data.map((_, idx) => (
                      <button key={idx} onClick={() => handleReplay(ev.id, idx)}
                        className="px-2 py-1 bg-slate-600 hover:bg-slate-500 rounded text-xs">
                        EP{idx + 1}
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div>
          {replayData ? (
            <div className="card">
              <h3 className="font-semibold mb-3">回放控制</h3>
              <canvas ref={canvasRef} width={600} height={450} className="rounded-lg border border-slate-600 mb-3 w-full" />

              <div className="flex items-center gap-3 mb-3">
                <button onClick={stepBackward} className="btn-secondary text-sm">⏪</button>
                <button onClick={() => setIsPlaying(!isPlaying)} className="btn-primary text-sm">
                  {isPlaying ? '⏸' : '▶️'}
                </button>
                <button onClick={stepForward} className="btn-secondary text-sm">⏩</button>
                <span className="text-sm text-slate-400">
                  Step {currentStep + 1} / {replayData.length}
                </span>
                <select value={playbackSpeed} onChange={(e) => setPlaybackSpeed(parseFloat(e.target.value))} className="select-field text-sm">
                  <option value={0.5}>0.5x</option>
                  <option value={1}>1x</option>
                  <option value={2}>2x</option>
                  <option value={4}>4x</option>
                </select>
              </div>

              <input
                type="range" min={0} max={Math.max(replayData.length - 1, 0)}
                value={currentStep} onChange={(e) => setCurrentStep(parseInt(e.target.value))}
                className="w-full"
              />

              {currentStepData && (
                <div className="mt-3 space-y-2">
                  <h4 className="text-sm font-semibold">当前步信息</h4>
                  <div className="grid grid-cols-2 gap-2 text-xs">
                    {currentStepData.agent_positions.map((pos, i) => (
                      <div
                        key={i}
                        className="bg-slate-700/50 rounded p-2 cursor-pointer hover:bg-slate-700"
                        onMouseEnter={() => setHoveredAgent(i)}
                        onMouseLeave={() => setHoveredAgent(null)}
                      >
                        <span className="font-semibold text-blue-400">Agent {i}</span>
                        <span className="ml-2">位置: ({pos[0]},{pos[1]})</span>
                        <span className="ml-2">动作: {actionNames[currentStepData.actions[i]] || currentStepData.actions[i]}</span>
                        <span className="ml-2">奖励: {currentStepData.rewards[i]?.toFixed(2)}</span>
                      </div>
                    ))}
                  </div>

                  {hoveredAgent !== null && currentStepData.q_values?.[hoveredAgent] && (
                    <div className="bg-slate-700/50 rounded p-2">
                      <h5 className="text-xs font-semibold mb-1">Agent {hoveredAgent} Q值/策略概率</h5>
                      <div className="flex gap-1">
                        {currentStepData.q_values[hoveredAgent].map((q, a) => (
                          <div key={a} className="text-center">
                            <div className="text-[10px] text-slate-400">{actionNames[a]}</div>
                            <div className="text-xs font-mono">{q.toFixed(3)}</div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          ) : (
            <div className="card flex items-center justify-center h-96 text-slate-500">
              选择评估结果中的回合以查看回放
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
