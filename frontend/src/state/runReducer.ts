import { RunState, LogEvent, CompleteEvent, StageName } from '../lib/types';
import { parsePhase } from '../lib/parsePhase';

const STAGE_ORDER: StageName[] = [
  'Plan',
  'LitReview',
  'Summarizer',
  'GapDetect',
  'Merge',
  'Negotiate',
  'Synthesize',
  'Critic',
];

export const initialState: RunState = {
  status: 'idle',
  phases: {
    Plan: { status: 'pending', message: '' },
    LitReview: { status: 'pending', message: '' },
    Summarizer: { status: 'pending', message: '' },
    GapDetect: { status: 'pending', message: '' },
    Merge: { status: 'pending', message: '' },
    Negotiate: { status: 'pending', message: '' },
    Synthesize: { status: 'pending', message: '' },
    Critic: { status: 'pending', message: '' },
  },
  log: [],
  result: null,
  error: null,
};

export type RunAction =
  | { type: 'RUN_STARTED' }
  | { type: 'LOG_RECEIVED'; payload: LogEvent }
  | { type: 'COMPLETE_RECEIVED'; payload: CompleteEvent }
  | { type: 'ERROR_RECEIVED'; payload: string }
  | { type: 'RUN_RESET' }
  | { type: 'RUN_CANCELED' };

export function runReducer(state: RunState, action: RunAction): RunState {
  switch (action.type) {
    case 'RUN_STARTED':
      return {
        ...initialState,
        status: 'running',
      };

    case 'LOG_RECEIVED': {
      const { stage, message } = parsePhase(action.payload.entry);
      const newLog = [...state.log, action.payload];
      const newPhases = { ...state.phases };

      if (stage) {
        // Mark current stage as active
        newPhases[stage] = { status: 'active', message };

        // Mark all previous stages as done
        const currentIndex = STAGE_ORDER.indexOf(stage);
        for (let i = 0; i < currentIndex; i++) {
          const prevStage = STAGE_ORDER[i];
          if (newPhases[prevStage].status !== 'done') {
            newPhases[prevStage] = {
              ...newPhases[prevStage],
              status: 'done',
            };
          }
        }
      }

      return {
        ...state,
        log: newLog,
        phases: newPhases,
      };
    }

    case 'COMPLETE_RECEIVED': {
      const allDone = { ...state.phases };
      // Mark all stages as done
      STAGE_ORDER.forEach((stage) => {
        if (allDone[stage].status === 'active' || allDone[stage].status === 'pending') {
          allDone[stage] = { ...allDone[stage], status: 'done' };
        }
      });

      return {
        ...state,
        status: 'done',
        result: action.payload,
        phases: allDone,
      };
    }

    case 'ERROR_RECEIVED': {
      const errorPhases = { ...state.phases };
      // Mark the currently active stage as error
      const activeStage = STAGE_ORDER.find(
        (stage) => errorPhases[stage].status === 'active'
      );
      if (activeStage) {
        errorPhases[activeStage] = {
          ...errorPhases[activeStage],
          status: 'error',
        };
      }

      return {
        ...state,
        status: 'error',
        error: action.payload,
        phases: errorPhases,
      };
    }

    case 'RUN_RESET':
      return initialState;

    case 'RUN_CANCELED':
      return {
        ...state,
        status: 'idle',
      };

    default:
      return state;
  }
}
