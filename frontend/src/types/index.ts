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

export interface TrainingSummary {
  final_avg_reward: number;
  max_episode_reward: number;
  convergence_episode: number | null;
  total_duration_seconds: number | null;
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
  batch_run_id: number | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  summary: TrainingSummary | null;
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

export interface LearningCurveData {
  total_count: number;
  episodes: number[];
  total_rewards: number[];
  steps: number[];
  win_rates: number[];
  agent_rewards: Record<string, number>[];
}

export interface LogsResponse {
  total_count: number;
  offset: number;
  limit: number;
  logs: TrainingLog[];
}

export interface CompareCurveItem {
  name: string;
  algorithm: string;
  episodes: number[];
  total_rewards: number[];
  win_rates: number[];
}

export interface PolicyService {
  id: number;
  name: string;
  version: number;
  experiment_id: number;
  checkpoint_id: number;
  max_concurrent: number;
  timeout_ms: number;
  status: 'created' | 'deploying' | 'running' | 'stopped' | 'error';
  error_reason: string | null;
  created_at: string;
  started_at: string | null;
  stopped_at: string | null;
}

export interface PolicyServiceDetail extends PolicyService {
  history_versions: PolicyService[];
}

export interface PolicyServiceGroup {
  name: string;
  versions: PolicyService[];
}

export interface InferenceLog {
  id: number;
  policy_service_id: number;
  request_time: string;
  latency_ms: number;
  obs_dimensions: string;
  output_actions: string;
  is_timeout: boolean;
}

export interface InferenceLogsResponse {
  total_count: number;
  offset: number;
  limit: number;
  logs: InferenceLog[];
}

export interface InferenceStats {
  total_count: number;
  avg_latency_ms: number;
  p95_latency_ms: number;
  timeout_rate: number;
  qps_last_hour: number;
  cache_hit_rate: number;
}

export interface CheckpointItem {
  id: number;
  episode: number;
  filepath: string;
  created_at: string;
}

export interface ABTestPolicyResult {
  policy_id: number;
  actions?: number[];
  q_values?: number[][];
  latency_ms: number;
  timeout: boolean;
  error?: string | null;
  cached?: boolean;
}

export interface ABTestResponse {
  policy_a: ABTestPolicyResult;
  policy_b: ABTestPolicyResult;
  diff_rate: number;
}

export interface PolicyResourceStats {
  policy_id: number;
  current_concurrent: number;
  max_concurrent: number;
  queue_depth: number;
  avg_latency_1min: number;
}

export interface ExperimentTemplate {
  id: number;
  name: string;
  description: string;
  algorithm: string;
  hyperparams: Record<string, any>;
  communication_enabled: boolean;
  environment_id: number;
  agent_count: number;
  total_episodes: number;
  param_variables: Record<string, any[]>;
  created_at: string;
}

export interface BatchRun {
  id: number;
  name: string;
  template_id: number;
  status: 'pending' | 'running' | 'completed' | 'failed';
  experiment_ids: number[];
  current_index: number;
  param_combinations: Record<string, any>[];
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  error_message: string | null;
  is_cancelled: boolean;
}

export interface BatchRunStats {
  batch_run_id: number;
  status: string;
  total_experiments: number;
  completed_count: number;
  running_count: number;
  failed_count: number;
  pending_count: number;
  experiments: BatchRunExperiment[];
  group_stats: GroupStat[];
  best_combination: BestCombination | null;
  total_duration_seconds: number | null;
}

export interface BatchRunExperiment {
  id: number;
  name: string;
  status: string;
  params: Record<string, any>;
  final_reward: number | null;
  max_reward: number | null;
  current_episode: number;
  total_episodes: number;
}

export interface GroupStat {
  variable: string;
  groups: VariableGroup[];
}

export interface VariableGroup {
  variable: string;
  value: any;
  avg_reward: number;
  count: number;
}

export interface BestCombination {
  experiment_id: number;
  params: Record<string, any>;
  final_reward: number;
}

export interface BatchRunPreview {
  total_combinations: number;
  param_combinations: Record<string, any>[];
}

