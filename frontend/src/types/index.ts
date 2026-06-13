export interface CellConfig {
  x: number;
  y: number;
  type: 'empty' | 'obstacle' | 'resource' | 'spawn' | 'target';
  team?: number;
}

export interface MapConfig {
  width: number;
  height: number;
  cells: CellConfig[];
}

export interface Environment {
  id: number;
  name: string;
  description: string;
  map_config: MapConfig;
  width: number;
  height: number;
  max_steps: number;
  obs_range: number;
  action_space: number;
  collision_rule: string;
  resource_refresh: string;
  resource_refresh_interval: number;
  reward_goal: number;
  reward_resource: number;
  reward_collision: number;
  reward_wall: number;
  reward_step: number;
  reward_catch_predator: number;
  reward_catch_prey: number;
  reward_timeout: number;
  scenario_type: string;
  agent_count: number;
  team_config: Record<string, number>;
  created_at: string;
}

export interface AlgorithmInfo {
  id: string;
  name: string;
  type: string;
  off_policy: boolean;
  supports_comm?: boolean;
}

export interface AlgorithmConfig {
  algorithm: string;
  learning_rate: number;
  gamma: number;
  epsilon_start: number;
  epsilon_end: number;
  epsilon_decay_steps: number;
  replay_buffer_size: number;
  batch_size: number;
  target_update_freq: number;
  qmix_hidden_dim: number;
  mappo_clip: number;
  mappo_gae_lambda: number;
  communication_enabled: boolean;
  comm_dim: number;
}

export interface Experiment {
  id: number;
  name: string;
  environment_id: number;
  algorithm: string;
  hyperparams: AlgorithmConfig;
  communication_enabled: boolean;
  status: string;
  current_episode: number;
  total_episodes: number;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface TrainingLog {
  id: number;
  experiment_id: number;
  episode: number;
  total_reward: number;
  agent_rewards: Record<string, number>;
  steps: number;
  goal_reached: boolean;
  win_rate: number;
  timestamp: string;
}

export interface Evaluation {
  id: number;
  experiment_id: number;
  num_episodes: number;
  avg_reward: number;
  success_rate: number;
  collision_rate: number;
  avg_steps: number;
  episode_data: EpisodeData[];
  created_at: string;
}

export interface EpisodeData {
  steps: StepData[];
  total_reward: number;
  steps_count: number;
  collisions: number;
  success: boolean;
}

export interface StepData {
  step: number;
  agent_positions: number[][];
  actions: number[];
  rewards: number[];
  q_values: number[][];
}

export interface TrainingProgress {
  status: string;
  current_episode: number;
  total_episodes: number;
  recent_data: any[];
}
