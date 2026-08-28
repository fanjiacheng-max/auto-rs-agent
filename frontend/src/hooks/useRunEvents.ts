import { useEffect, useRef } from 'react'
import type { RunEvent, RunEventType } from '../types'

const TERMINAL: RunEventType[] = ['run_completed', 'run_failed', 'run_interrupted']

export function useRunEvents(
  runId: string | null,
  onEvent: (event: RunEvent) => void,
  cursor: number = 0,
) {
  const onEventRef = useRef(onEvent)
  onEventRef.current = onEvent

  useEffect(() => {
    if (!runId) return

    const url = `/api/runs/${runId}/events?cursor=${cursor}`
    const es = new EventSource(url)

    es.onmessage = (e) => {
      const event: RunEvent = JSON.parse(e.data)
      onEventRef.current(event)
      if (TERMINAL.includes(event.type)) {
        es.close()
      }
    }

    es.onerror = () => {
      es.close()
    }

    return () => {
      es.close()
    }
  }, [runId]) // cursor intentionally omitted — reconnect only on new run
}
