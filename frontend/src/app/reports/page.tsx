'use client';

import { useState, useEffect, useCallback } from 'react';
import { Experiment } from '@/types';
import { experimentApi, reportApi } from '@/lib/api';

export default function ReportsPage() {
  const [experiments, setExperiments] = useState<Experiment[]>([]);
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [report, setReport] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  const fetchExps = useCallback(async () => {
    try {
      const res = await experimentApi.list();
      setExperiments(res.data);
    } catch (e) { console.error(e); }
  }, []);

  useEffect(() => { fetchExps(); }, [fetchExps]);

  const toggleId = (id: number) => {
    setSelectedIds((prev) => {
      if (prev.includes(id)) return prev.filter((i) => i !== id);
      if (prev.length >= 4) return prev;
      return [...prev, id];
    });
  };

  const handleGenerate = async () => {
    if (selectedIds.length < 2) return;
    setLoading(true);
    try {
      const res = await reportApi.createComparison(selectedIds);
      setReport(res.data);
    } catch (e) {
      console.error(e);
    }
    setLoading(false);
  };

  const handleExportPdf = async () => {
    if (selectedIds.length < 2) return;
    try {
      const res = await reportApi.exportPdf(selectedIds);
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', 'marl_comparison_report.pdf');
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch (e) {
      console.error(e);
    }
  };

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">对比报告</h1>

      <div className="card mb-6">
        <h3 className="font-semibold mb-3">选择实验 (2-4个已完成实验)</h3>
        <div className="flex flex-wrap gap-2 mb-4">
          {experiments.filter((e) => e.status === 'completed').map((exp) => (
            <button
              key={exp.id}
              onClick={() => toggleId(exp.id)}
              className={`px-3 py-1.5 rounded-lg text-sm ${
                selectedIds.includes(exp.id) ? 'bg-blue-600 text-white' : 'bg-slate-700 text-slate-300'
              }`}
            >
              {exp.name} ({exp.algorithm})
            </button>
          ))}
          {experiments.filter((e) => e.status === 'completed').length === 0 && (
            <p className="text-slate-500 text-sm">暂无已完成的实验</p>
          )}
        </div>
        <div className="flex gap-2">
          <button onClick={handleGenerate} disabled={selectedIds.length < 2 || loading} className="btn-primary">
            {loading ? '生成中...' : '生成报告'}
          </button>
          <button onClick={handleExportPdf} disabled={selectedIds.length < 2} className="btn-secondary">
            导出PDF
          </button>
        </div>
      </div>

      {report && (
        <div className="space-y-4">
          <div className="card">
            <h3 className="font-semibold mb-3">配置差异表</h3>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-600">
                    <th className="text-left py-2 px-3 text-slate-400">参数</th>
                    {report.experiments?.map((exp: any) => (
                      <th key={exp.id} className="text-left py-2 px-3 text-slate-400">{exp.name}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(report.config_diff || {}).map(([key, values]: [string, any]) => (
                    <tr key={key} className="border-b border-slate-700">
                      <td className="py-2 px-3 font-mono text-yellow-400">{key}</td>
                      {Object.values(values).map((val: any, i: number) => (
                        <td key={i} className="py-2 px-3 text-red-400 font-semibold">{String(val)}</td>
                      ))}
                    </tr>
                  ))}
                  {Object.keys(report.config_diff || {}).length === 0 && (
                    <tr><td colSpan={5} className="py-3 text-center text-slate-500">配置完全一致，无差异</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          <div className="card">
            <h3 className="font-semibold mb-3">性能指标对比</h3>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-600">
                    <th className="text-left py-2 px-3 text-slate-400">实验</th>
                    <th className="text-left py-2 px-3 text-slate-400">平均奖励</th>
                    <th className="text-left py-2 px-3 text-slate-400">成功率</th>
                    <th className="text-left py-2 px-3 text-slate-400">收敛Episode</th>
                  </tr>
                </thead>
                <tbody>
                  {report.performance?.map((p: any) => (
                    <tr key={p.id} className="border-b border-slate-700">
                      <td className="py-2 px-3">{p.name}</td>
                      <td className="py-2 px-3 text-blue-400 font-semibold">{p.avg_reward?.toFixed(2)}</td>
                      <td className="py-2 px-3 text-green-400 font-semibold">{(p.success_rate * 100)?.toFixed(1)}%</td>
                      <td className="py-2 px-3 text-yellow-400 font-semibold">{p.convergence_ep}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="card">
            <h3 className="font-semibold mb-3">统计显著性检验</h3>
            <div className="space-y-2">
              {report.significance?.map((s: any, i: number) => (
                <div key={i} className="bg-slate-700/50 rounded p-3 flex items-center justify-between">
                  <span className="text-sm">
                    实验 #{s.exp_a} vs 实验 #{s.exp_b}
                  </span>
                  <div className="flex items-center gap-3">
                    {s.p_value !== null ? (
                      <>
                        <span className="text-xs text-slate-400">p-value: {s.p_value.toFixed(4)}</span>
                        <span className={`px-2 py-0.5 rounded text-xs ${s.significant ? 'bg-green-600 text-white' : 'bg-slate-600 text-slate-300'}`}>
                          {s.significant ? '显著' : '不显著'}
                        </span>
                      </>
                    ) : (
                      <span className="text-xs text-slate-500">{s.note}</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
