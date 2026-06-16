'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';

const navItems = [
  { href: '/environments', label: '环境编辑器', icon: '🗺️' },
  { href: '/experiments', label: '实验管理', icon: '🧪' },
  { href: '/templates', label: '实验模板', icon: '📋' },
  { href: '/training', label: '训练监控', icon: '📊' },
  { href: '/evaluation', label: '评估回放', icon: '▶️' },
  { href: '/visualization', label: '可视化分析', icon: '🔍' },
  { href: '/reports', label: '对比报告', icon: '📄' },
  { href: '/deployment', label: '策略部署', icon: '🚀' },
];

export default function NavSidebar() {
  const pathname = usePathname();

  return (
    <aside className="w-56 min-h-screen bg-slate-900 border-r border-slate-700 flex flex-col">
      <div className="p-4 border-b border-slate-700">
        <h1 className="text-lg font-bold text-blue-400">MARL Platform</h1>
        <p className="text-xs text-slate-400 mt-1">多智能体强化学习实验平台</p>
      </div>
      <nav className="flex-1 py-2">
        {navItems.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className={`flex items-center gap-3 px-4 py-3 text-sm transition-colors ${
              pathname === item.href
                ? 'bg-blue-600/20 text-blue-400 border-r-2 border-blue-400'
                : 'text-slate-300 hover:bg-slate-800 hover:text-white'
            }`}
          >
            <span>{item.icon}</span>
            <span>{item.label}</span>
          </Link>
        ))}
      </nav>
      <div className="p-4 border-t border-slate-700">
        <p className="text-xs text-slate-500">v1.0.0</p>
      </div>
    </aside>
  );
}
