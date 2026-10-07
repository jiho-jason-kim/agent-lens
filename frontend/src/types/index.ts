export type Position = [number, number];

export interface Observation {
  position: Position;
  inventory: number;
  cells: { position: Position; resource: boolean; home: boolean; agents?: string[]; obstacle?: boolean; target?: boolean }[];
  visible_agents?: { agent_id: string; position: Position }[];
  goal_complete?: boolean;
}

export type Action = { type: 'move'; direction: 'north' | 'south' | 'east' | 'west' }
  | { type: 'collect' | 'wait' }
  | { type: 'send_message'; recipient: string; message: string };

export interface AgentContext {
  agent_id?: string;
  recent_messages?: Message[];
  retrieved_memories?: Memory[];
  scenario_instructions?: string[];
  goal: string;
  observation: Observation;
  inventory: number;
  previous_plan: string | null;
  recent_history: { turn: number; action: Action; success: boolean; message: string }[];
}

export interface EnvironmentDelta {
  success: boolean;
  message: string;
  position: { before: Position; after: Position };
  inventory: { before: number; after: number };
  removed_resources: Position[];
  goal_complete: { before: boolean; after: boolean };
  changed_cells: Position[];
}

interface EventBase {
  event_id: string;
  run_id: string;
  turn: number;
  agent_id: string;
  timestamp: string;
  input_refs: string[];
  effect_refs: string[];
}

export type RecordedEvent = EventBase & (
  | { type: 'observation'; payload: { context: AgentContext } }
  | { type: 'plan'; payload: { plan: string } }
  | { type: 'action'; payload: { action: Action } }
  | { type: 'environment_delta'; payload: EnvironmentDelta }
  | { type: 'model_call' | 'goal_complete' | 'error' | 'scenario_complete' | 'scenario_instruction' | 'target_occupied' | 'local_observation' | 'memory_write' | 'memory_retrieve'; payload: Record<string, unknown> }
  | { type: 'message_send' | 'message_receive'; payload: { message: Message } }
);

export interface WorldState {
  turn: number;
  position: Position;
  inventory: number;
  resources: Position[];
  home: Position;
  goal_complete: boolean;
}

export interface RunMetadata {
  agent_mode?: 'mock' | 'llm' | 'langchain' | null;
  schema_version: number;
  run_id: string;
  created_at: string;
  agent: string;
  goal: string;
  scenario_id?: string;
  scenario_name?: string;
  agents?: { agent_id: string; goal: string; target: number; target_position?: Position | null }[];
  status: 'goal_complete' | 'turn_limit' | 'error' | 'resources_exhausted';
  turns: number;
  max_turns: number;
}

export interface AgentState {
  agent_id: string;
  position: Position;
  inventory: number;
  home: Position;
  goal_complete: boolean;
}
export interface MultiWorldState {
  turn: number;
  agents: AgentState[];
  resources: Position[];
  obstacles: Position[];
  targets: Position[];
}
export type Snapshot = WorldState | MultiWorldState;
export interface Message {
  message_id: string;
  sender_id: string;
  recipient_id: string;
  content: string;
  sent_turn: number;
  delivered_turn: number | null;
}
export interface Memory {
  source_type?: string;
  resource_position?: Position | null;
  memory_id: string;
  content: string;
  source_event_id: string;
  created_turn: number;
}
export interface Scenario {
  id: string;
  name: string;
  description: string;
  concepts: string[];
  agent_count: number;
}
