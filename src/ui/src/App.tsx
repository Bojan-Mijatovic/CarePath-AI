import { useCallback, useState } from 'react'
import './App.css'
import { type StreamMessage, useStream } from './lib/stream'

// Menu order and Italian labels follow the prototype; screens arrive in Phase 2.
const SCREENS = [
  'Panoramica',
  'Mappa',
  'Chiedi',
  'Confronto',
  'What-if',
  'Percorsi',
  'Chiamate',
  'Posti letto',
  'Pazienti',
] as const

const CONNECTION_LABEL = { connecting: 'connessione…', open: 'connesso', closed: 'riconnessione…' }

export default function App() {
  const [day, setDay] = useState<number | null>(null)
  const [screen, setScreen] = useState<(typeof SCREENS)[number]>('Panoramica')

  const onMessage = useCallback((msg: StreamMessage) => {
    if (msg.type === 'tick') setDay(msg.day)
  }, [])
  const connection = useStream(onMessage)

  return (
    <div className="shell">
      <nav className="nav" aria-label="Navigazione principale">
        <div className="brand">
          <strong>CarePath AI</strong>
          <span>ATS della Val Padana</span>
        </div>
        {SCREENS.map((name) => (
          <button
            key={name}
            type="button"
            className={name === screen ? 'nav-item active' : 'nav-item'}
            onClick={() => setScreen(name)}
          >
            {name}
          </button>
        ))}
        <div className="nav-footer">Modelli locali · nessun dato reale</div>
      </nav>

      <main className="main">
        <header className="topbar">
          <h1>{screen}</h1>
          <span className="spacer" />
          <span className="day">{day === null ? '–' : `Giorno ${day}`}</span>
          <span className="pill">Dati sintetici</span>
          <span className={`connection ${connection}`}>{CONNECTION_LABEL[connection]}</span>
        </header>
        <section className="content">
          <p className="placeholder">Schermata “{screen}”: in arrivo nella Fase 2.</p>
        </section>
      </main>

      <aside className="feed" aria-label="Attività agenti">
        <h2>Attività agenti · live</h2>
        <p className="placeholder">Le azioni degli agenti appariranno qui.</p>
      </aside>
    </div>
  )
}
