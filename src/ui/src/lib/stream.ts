import { useEffect, useState } from 'react'

/** Envelope of every message on /api/stream (spec/SPEC.md §10). */
export type StreamMessage =
  | { type: 'tick'; scenario: number; day: number; payload: Record<string, unknown> }
  | { type: 'alert'; scenario: number; day: number; payload: Record<string, unknown> }
  | { type: 'action'; scenario: number; day: number; payload: Record<string, unknown> }
  | { type: 'investigation'; scenario: number; day: number; payload: Record<string, unknown> }

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
