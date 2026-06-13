import Link from 'next/link';

export default function Home() {
  return (
    <div className="max-w-5xl mx-auto">
      <h1 className="text-3xl font-bold mb-2">多智能体强化学习实验平台</h1>
      <p className="text-slate-400 mb-8">
        支持自定义2D网格环境搭建、多种MARL算法训练、策略行为回放与可视化分析的完整实验管理流程
      </p>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mb-8">
        <Link href="/environments" className="card hover:border-blue-500 transition-colors">
          <div className="text-2xl mb-2">🗺️</div>
          <h3 className="font-semibold text-lg">环境编辑器</h3>
          <p className="text-sm text-slate-400 mt-1">可视化2D网格世界编辑，预设场景，自定义地图</p>
        </Link>
        <Link href="/experiments" className="card hover:border-green-500 transition-colors">
          <div className="text-2xl mb-2">🧪</div>
          <h3 className="font-semibold text-lg">实验管理</h3>
          <p className="text-sm text-slate-400 mt-1">创建训练实验，配置算法与超参数</p>
        </Link>
        <Link href="/training" className="card hover:border-yellow-500 transition-colors">
          <div className="text-2xl mb-2">📊</div>
          <h3 className="font-semibold text-lg">训练监控</h3>
          <p className="text-sm text-slate-400 mt-1">实时训练曲线，暂停/恢复/终止控制</p>
        </Link>
        <Link href="/evaluation" className="card hover:border-purple-500 transition-colors">
          <div className="text-2xl mb-2">▶️</div>
          <h3 className="font-semibold text-lg">评估回放</h3>
          <p className="text-sm text-slate-400 mt-1">策略评估，动画回放，Q值热力图</p>
        </Link>
        <Link href="/visualization" className="card hover:border-cyan-500 transition-colors">
          <div className="text-2xl mb-2">🔍</div>
          <h3 className="font-semibold text-lg">可视化分析</h3>
          <p className="text-sm text-slate-400 mt-1">轨迹热力图，Q值地图，学习曲线对比</p>
        </Link>
        <Link href="/reports" className="card hover:border-red-500 transition-colors">
          <div className="text-2xl mb-2">📄</div>
          <h3 className="font-semibold text-lg">对比报告</h3>
          <p className="text-sm text-slate-400 mt-1">多实验对比，统计检验，PDF导出</p>
        </Link>
      </div>

      <div className="card">
        <h2 className="font-semibold text-lg mb-3">支持的算法</h2>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
          {[
            { name: 'IQL', desc: '独立Q-Learning' },
            { name: 'DQN', desc: '独立DQN' },
            { name: 'VDN', desc: '值分解网络' },
            { name: 'QMIX', desc: '混合网络单调分解' },
            { name: 'MAPPO', desc: '多智能体PPO' },
            { name: 'MADDPG', desc: '多智能体DDPG' },
          ].map((algo) => (
            <div key={algo.name} className="bg-slate-700/50 rounded-lg p-3">
              <span className="text-blue-400 font-mono font-bold">{algo.name}</span>
              <p className="text-xs text-slate-400 mt-1">{algo.desc}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
