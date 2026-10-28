# PDTA scompenso cardiaco — ATS della Val Padana

> Testo dimostrativo per il PoC CarePath AI. Tempi e codici sono valori di esempio, non validati clinicamente (delivery plan D28). Modello di percorso corrispondente: `spec/pathways/hf_lombardia_v1.json`.

## 1. Pazienti inclusi

Entrano nel percorso i pazienti con una diagnosi di scompenso cardiaco (ICD-9-CM 428.*) oppure in terapia con furosemide (ATC C03CA01).

## 2. Tappe del percorso dopo la dimissione

Il percorso parte da ogni dimissione ospedaliera per scompenso cardiaco (ICD-9-CM 428.*).

1. **Telemonitoraggio**: attivazione entro 7 giorni dalla dimissione.
2. **Visita cardiologica**: entro 30 giorni dalla dimissione.
3. **Ecocardiogramma** (codice 88.72): entro 90 giorni dalla dimissione.
4. **BNP** (LOINC 30934-4): ogni 90 giorni, per tutta la durata del percorso.

## 3. Regole di monitoraggio

- Se il peso rilevato dal telemonitoraggio aumenta di 2 kg o più in 3 giorni, la visita cardiologica va anticipata ed eseguita entro 7 giorni.
- Se il paziente non ritira il furosemide (ATC C03CA01) da 30 giorni, va segnalato un rischio di aderenza alla terapia.

## 4. Stato del paziente nel percorso

- **In linea**: tutto ciò che era previsto fino a oggi è stato fatto.
- **Scadenza vicina**: una tappa scade entro 7 giorni e non è ancora prenotata.
- **In ritardo**: una tappa ha superato la scadenza e non è stata eseguita.
- **Fuori percorso**: un ritardo supera i 30 giorni, oppure 2 o più tappe sono in ritardo nello stesso momento.

## 5. Azioni in caso di ritardo

1. Il giorno stesso del ritardo: promemoria automatico al paziente.
2. Dopo 3 giorni senza cambiamenti: il paziente entra nella lista chiamate del Centro Servizi.
3. Dopo 7 giorni: notifica al medico di medicina generale (MMG).
4. I pazienti ad alto rischio saltano il promemoria ed entrano subito nella lista chiamate.

## 6. Ricovero

Se il medico decide che serve un ricovero per scompenso cardiaco (ICD-9-CM 428.*), il reparto indicato è la cardiologia; se non ci sono posti, la medicina interna.

Le decisioni su diagnosi e terapia restano sempre al medico.
