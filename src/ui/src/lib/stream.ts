import { useEffect, useState } from 'react'
import type { Action, Kpi } from './api'
import type { Bilingual } from './i18n'

/** Envelope of every message on /api/stream and its payloads (spec/SPEC.md §10). */
type Envelope<T extends string, P> = { type: T; scenario: number; day: number; payload: P }

export type TickPayload = { speed?: number; kpi?: Kpi }
export type AlertPayload = {
  alert_id: string
  level: 'patient' | 'regional'
  text: Bilingual
  facility_id: string | null
  /** MMG group or first comune of the area, for a group alarm (C26) */
  group_key: string | null
  investigation_id: string | null
}
export type InvestigationPayload = {
  investigation_id: string
  step: number
  tool: string
  args: Record<string, unknown>
  result_summary: Bilingual
  verified: boolean | null
  final: boolean
}

export type StreamMessage =
  | Envelope<'tick', TickPayload>
  | Envelope<'alert', AlertPayload>
  | Envelope<'action', Action>
  | Envelope<'investigation', InvestigationPayload>

export type ConnectionState = 'connecting' | 'open' | 'closed'

const RECONNECT_MS = 1000

/** Subscribes to /api/stream and reconnects on its own; state lives on the server. */
export function useStream(onMessage: (msg: StreamMessage) => void): ConnectionState {
  const [state, setState] = useState<ConnectionState>('connecting')

  useEffect(() => {
    let ws: WebSocket | undefined
    let retry: number | undefined
    let stopped = false

    const connect = () => {
      const proto = location.protocol === 'https:' ? 'wss' : 'ws'
      ws = new WebSocket(`${proto}://${location.host}/api/stream`)
      ws.onopen = () => setState('open')
      ws.onmessage = (event) => onMessage(JSON.parse(event.data) as StreamMessage)
      ws.onclose = () => {
        setState('closed')
        if (!stopped) retry = window.setTimeout(connect, RECONNECT_MS)
      }
    }
    connect()

    return () => {
      stopped = true
      window.clearTimeout(retry)
      ws?.close()
    }
  }, [onMessage])

  return state
}
