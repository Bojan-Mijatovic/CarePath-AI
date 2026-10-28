# PDTA diabete mellito tipo 2 — ATS della Val Padana (bozza)

> **Bozza** per l'opzione B del PoC CarePath AI (delivery plan, fase 3). Testo dimostrativo: tempi e codici sono valori di esempio, non validati clinicamente (delivery plan D28). Il modello di percorso viene prodotto da questo testo dal Pathway Builder.

## 1. Pazienti inclusi

Entrano nel percorso i pazienti con una diagnosi di diabete mellito (ICD-9-CM 250.*) oppure in terapia con metformina (ATC A10BA02).

## 2. Tappe del percorso

Il percorso parte dall'inclusione del paziente.

1. **Emoglobina glicata HbA1c** (LOINC 4548-4): ogni 180 giorni.
2. **Funzione renale, eGFR** (LOINC 33914-3): ogni 365 giorni.
3. **Visita diabetologica**: ogni 365 giorni.
4. **Esame del fondo oculare** (codice 95.02): ogni 365 giorni.

## 3. Regole di monitoraggio

- Se il paziente non ritira la metformina (ATC A10BA02) da 60 giorni, va segnalato un rischio di aderenza alla terapia.
- Se l'HbA1c è in ritardo da oltre 30 giorni, va segnalata una mancata misurazione dell'HbA1c.

## 4. Stato del paziente nel percorso

- **In linea**: tutto ciò che era previsto fino a oggi è stato fatto.
- **Scadenza vicina**: una tappa scade entro 14 giorni e non è ancora prenotata.
- **In ritardo**: una tappa ha superato la scadenza e non è stata eseguita.
- **Fuori percorso**: un ritardo supera i 90 giorni, oppure 2 o più tappe sono in ritardo nello stesso momento.

## 5. Azioni in caso di ritardo

1. Il giorno stesso del ritardo: promemoria automatico al paziente.
2. Dopo 7 giorni senza cambiamenti: il paziente entra nella lista chiamate del Centro Servizi.
3. Dopo 14 giorni: notifica al medico di medicina generale (MMG).
4. I pazienti ad alto rischio saltano il promemoria ed entrano subito nella lista chiamate.

## 6. Ricovero

Se il medico decide che serve un ricovero per diabete con complicanze (ICD-9-CM 250.*), il reparto indicato è la medicina interna; in alternativa l'endocrinologia.

Le decisioni su diagnosi e terapia restano sempre al medico.
