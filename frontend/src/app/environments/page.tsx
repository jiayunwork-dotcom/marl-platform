'use client';

import { useState, useEffect, useCallback } from 'react';
import { Environment, MapConfig, CellConfig } from '@/types';
import { environmentApi } from '@/lib/api';
import GridEditor from '@/components/GridEditor';

const defaultMap: MapConfig = { width: 10, height: 10, cells: [] };

export default function EnvironmentsPage() {
  const [environments, setEnvironments] = useState<Environment[]>([]);
  const [selected, setSelected] = useState<Environment | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [mapConfig, setMapConfig] = useState<MapConfig>(defaultMap);
  const [mapWidth, setMapWidth] = useState(10);
  const [mapHeight, setMapHeight] = useState(10);
  const [maxSteps, setMaxSteps] = useState(100);
  const [obsRange, setObsRange] = useState(-1);
  const [actionSpace, setActionSpace] = useState(5);
  const [collisionRule, setCollisionRule] = useState('both_stay');
  const [resourceRefresh, setResourceRefresh] = useState('fixed_interval');
  const [refreshInterval, setRefreshInterval] = useState(10);
  const [agentCount, setAgentCount] = useState(2);
  const [rewards, setRewards] = useState({
    goal: 10, resource: 5, collision: -2, wall: -1, step: -0.1,
    catch_predator: 20, catch_prey: -20, timeout: -5,
  });
  const [activeTab, setActiveTab] = useState<'list' | 'editor' | 'params'>('list');

  const fetchEnvs = useCallback(async () => {
    try {
      const res = await environmentApi.list();
      setEnvironments(res.data);
    } catch (e) {
      console.error(e);
    }
  }, []);

  useEffect(() => { fetchEnvs(); }, [fetchEnvs]);

  const handleResize = () => {
    const w = Math.max(5, Math.min(30, mapWidth));
    const h = Math.max(5, Math.min(30, mapHeight));
    setMapWidth(w);
    setMapHeight(h);
    setMapConfig((prev) => ({
      ...prev,
      width: w,
      height: h,
      cells: prev.cells.filter((c) => c.x < w && c.y < h),
    }));
  };

  const handleCreate = async () => {
    try {
      await environmentApi.create({
        name, description, map_config: mapConfig,
        max_steps: maxSteps, obs_range: obsRange, action_space: actionSpace,
        collision_rule: collisionRule, resource_refresh: resourceRefresh,
        resource_refresh_interval: refreshInterval, agent_count: agentCount,
        ...rewards, scenario_type: 'custom', team_config: {},
      });
      setIsCreating(false);
      setName('');
      setDescription('');
      setMapConfig(defaultMap);
      fetchEnvs();
    } catch (e) {
      console.error(e);
    }
  };

  const handlePreset = async (type: string) => {
    try {
      await environmentApi.createPreset({
        scenario_type: type, map_size: mapWidth, agent_count: agentCount,
      });
      fetchEnvs();
    } catch (e) {
      console.error(e);
    }
  };

  const handleSelect = (env: Environment) => {
    setSelected(env);
    setMapConfig(env.map_config);
    setMapWidth(env.width);
    setMapHeight(env.height);
    setMaxSteps(env.max_steps);
    setObsRange(env.obs_range);
    setActionSpace(env.action_space);
    setCollisionRule(env.collision_rule);
    setResourceRefresh(env.resource_refresh);
    setRefreshInterval(env.resource_refresh_interval);
    setAgentCount(env.agent_count);
    setRewards({
      goal: env.reward_goal, resource: env.reward_resource, collision: env.reward_collision,
      wall: env.reward_wall, step: env.reward_step, catch_predator: env.reward_catch_predator,
      catch_prey: env.reward_catch_prey, timeout: env.reward_timeout,
    });
    setActiveTab('editor');
  };

  const handleDelete = async (id: number) => {
    try {
      await environmentApi.delete(id);
      if (selected?.id === id) setSelected(null);
      fetchEnvs();
    } catch (e) {
      console.error(e);
    }
  };

  const handleSaveMap = async () => {
    if (!selected) return;
    try {
      await environmentApi.saveMap(selected.id);
      alert('地图已保存');
    } catch (e) {
      console.error(e);
    }
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">环境编辑器</h1>
        <div className="flex gap-2">
          <button onClick={() => setIsCreating(true)} className="btn-primary">+ 新建环境</button>
        </div>
      </div>

      <div className="flex gap-2 mb-4">
        <button onClick={() => setActiveTab('list')} className={`px-4 py-2 rounded-lg text-sm ${activeTab === 'list' ? 'bg-blue-600 text-white' : 'bg-slate-700 text-slate-300'}`}>环境列表</button>
        <button onClick={() => setActiveTab('editor')} className={`px-4 py-2 rounded-lg text-sm ${activeTab === 'editor' ? 'bg-blue-600 text-white' : 'bg-slate-700 text-slate-300'}`}>地图编辑</button>
        <button onClick={() => setActiveTab('params')} className={`px-4 py-2 rounded-lg text-sm ${activeTab === 'params' ? 'bg-blue-600 text-white' : 'bg-slate-700 text-slate-300'}`}>参数配置</button>
      </div>

      {activeTab === 'list' && (
        <div>
          <div className="card mb-4">
            <h3 className="font-semibold mb-3">预设场景</h3>
            <div className="flex gap-2">
              <button onClick={() => handlePreset('cooperative_navigation')} className="btn-secondary text-sm">合作导航</button>
              <button onClick={() => handlePreset('resource_competition')} className="btn-secondary text-sm">资源争夺</button>
              <button onClick={() => handlePreset('predator_prey')} className="btn-secondary text-sm">捕食者-猎物</button>
            </div>
          </div>

          <div className="space-y-2">
            {environments.map((env) => (
              <div key={env.id} className="card flex items-center justify-between">
                <div>
                  <h3 className="font-semibold">{env.name}</h3>
                  <p className="text-xs text-slate-400">{env.width}×{env.height} | {env.scenario_type} | {env.agent_count}个智能体</p>
                </div>
                <div className="flex gap-2">
                  <button onClick={() => handleSelect(env)} className="btn-primary text-sm">编辑</button>
                  <button onClick={() => handleDelete(env.id)} className="btn-danger text-sm">删除</button>
                </div>
              </div>
            ))}
            {environments.length === 0 && <p className="text-slate-500 text-center py-8">暂无环境，请创建或加载预设场景</p>}
          </div>
        </div>
      )}

      {activeTab === 'editor' && (
        <div className="space-y-4">
          <div className="card">
            <div className="flex items-center gap-4 mb-3">
              <div>
                <label className="text-sm text-slate-400">宽度</label>
                <input type="number" min={5} max={30} value={mapWidth} onChange={(e) => setMapWidth(parseInt(e.target.value))} className="input-field w-20 ml-2" />
              </div>
              <div>
                <label className="text-sm text-slate-400">高度</label>
                <input type="number" min={5} max={30} value={mapHeight} onChange={(e) => setMapHeight(parseInt(e.target.value))} className="input-field w-20 ml-2" />
              </div>
              <button onClick={handleResize} className="btn-secondary text-sm">应用尺寸</button>
              {selected && <button onClick={handleSaveMap} className="btn-secondary text-sm">保存地图JSON</button>}
            </div>
            <GridEditor mapConfig={mapConfig} onChange={setMapConfig} />
          </div>
        </div>
      )}

      {activeTab === 'params' && (
        <div className="space-y-4">
          <div className="card">
            <h3 className="font-semibold mb-3">环境参数</h3>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
              <div>
                <label className="text-sm text-slate-400">最大步数</label>
                <input type="number" value={maxSteps} onChange={(e) => setMaxSteps(parseInt(e.target.value))} className="input-field w-full mt-1" />
              </div>
              <div>
                <label className="text-sm text-slate-400">观察范围</label>
                <select value={obsRange} onChange={(e) => setObsRange(parseInt(e.target.value))} className="select-field w-full mt-1">
                  <option value={-1}>全局观察</option>
                  {[1, 2, 3, 4, 5].map((r) => <option key={r} value={r}>半径 {r}</option>)}
                </select>
              </div>
              <div>
                <label className="text-sm text-slate-400">动作空间</label>
                <select value={actionSpace} onChange={(e) => setActionSpace(parseInt(e.target.value))} className="select-field w-full mt-1">
                  <option value={4}>四方向</option>
                  <option value={5}>五方向(含停留)</option>
                </select>
              </div>
              <div>
                <label className="text-sm text-slate-400">碰撞规则</label>
                <select value={collisionRule} onChange={(e) => setCollisionRule(e.target.value)} className="select-field w-full mt-1">
                  <option value="both_stay">双方都不动</option>
                  <option value="bounce_back">弹回原地</option>
                </select>
              </div>
              <div>
                <label className="text-sm text-slate-400">资源刷新</label>
                <select value={resourceRefresh} onChange={(e) => setResourceRefresh(e.target.value)} className="select-field w-full mt-1">
                  <option value="fixed_interval">固定间隔</option>
                  <option value="random_position">随机位置</option>
                </select>
              </div>
              <div>
                <label className="text-sm text-slate-400">刷新间隔</label>
                <input type="number" value={refreshInterval} onChange={(e) => setRefreshInterval(parseInt(e.target.value))} className="input-field w-full mt-1" />
              </div>
              <div>
                <label className="text-sm text-slate-400">智能体数量</label>
                <input type="number" min={2} max={8} value={agentCount} onChange={(e) => setAgentCount(parseInt(e.target.value))} className="input-field w-full mt-1" />
              </div>
            </div>
          </div>

          <div className="card">
            <h3 className="font-semibold mb-3">奖励函数</h3>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {Object.entries(rewards).map(([key, val]) => (
                <div key={key}>
                  <label className="text-sm text-slate-400">{key}</label>
                  <input
                    type="number" step="0.1" value={val}
                    onChange={(e) => setRewards((prev) => ({ ...prev, [key]: parseFloat(e.target.value) }))}
                    className="input-field w-full mt-1"
                  />
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {isCreating && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-slate-800 rounded-lg p-6 w-96">
            <h3 className="text-lg font-bold mb-4">新建环境</h3>
            <div className="space-y-3">
              <div>
                <label className="text-sm text-slate-400">名称</label>
                <input value={name} onChange={(e) => setName(e.target.value)} className="input-field w-full mt-1" />
              </div>
              <div>
                <label className="text-sm text-slate-400">描述</label>
                <textarea value={description} onChange={(e) => setDescription(e.target.value)} className="input-field w-full mt-1" rows={2} />
              </div>
            </div>
            <div className="flex gap-2 mt-4">
              <button onClick={handleCreate} className="btn-primary">创建</button>
              <button onClick={() => setIsCreating(false)} className="btn-secondary">取消</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
