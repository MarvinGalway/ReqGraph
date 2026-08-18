# ReqGraph — Specifica Architetturale

**Sistema di semantic traceability per costruire e mantenere la relazione verificabile fra intenzione, specifica comportamentale, lavoro, implementazione e comportamento osservato di un software. Supporta sia progetti greenfield sia il bootstrap di progetti esistenti.**

Versione: **0.2 (draft)**  
Formato: Markdown + template JSON  
Knowledge Graph target: Neo4j  
Execution target: OpenCode, mantenuto sostituibile tramite `graph-cli`

---

## 1. Visione

ReqGraph non è soltanto un sistema di generazione di codice da requisiti. È un sistema che mantiene una catena navigabile e verificabile fra:

```text
Intento umano
  ↕
Requirement
  ↕
Contract
  ↕
Example
  ↕
Task
  ↕
Test / CodeUnit
  ↕
Comportamento osservato / Issue
```

Il progetto può entrare in ReqGraph in due modi:

1. **Greenfield Mode** — si parte da requisiti e si arriva all'implementazione.
2. **Existing Project Bootstrap Mode** — si parte da repository, test e altre evidenze tecniche, si ricostruisce ciò che il sistema fa e si propongono specifiche/requisiti candidati da validare umanamente.

Dopo il bootstrap, entrambi i percorsi convergono nello stesso Knowledge Graph e nello stesso lifecycle.

---

## 2. Principi

1. **Mai colmare i buchi in silenzio.** Ogni ambiguità produce una `Clarification` o una `Assumption` esplicita.
2. **Il Requirement resta la fonte dell'intento umano.** Una nuova intenzione produce una nuova versione del Requirement (`SUPERSEDES`), non una modifica silenziosa del Contract.
3. **Il Contract è derivato e revisionabile, non la fonte primaria dell'intento.** Se è formalizzato male viene rifiutato e rigenerato; se il requisito è ambiguo si torna al Requirement/Clarification.
4. **Example = test case comportamentale, non codice.** Descrive un caso concreto input → expected output che testimonia il Contract.
5. **Discovery is not authorization to modify.** Se un agente trova un possibile bug fuori dallo scope del Task corrente, apre una `Issue`; non lo corregge automaticamente.
6. **Observed behavior ≠ desired behavior.** Nel bootstrap legacy, ciò che il codice fa è evidenza; non diventa Requirement o Contract validato senza review umana.
7. **Invalidation e revalidation sono concetti distinti.** Cambio semantico certo → `stale`; modifica tecnica con impatto possibile → `needs_revalidation`.
8. **Il grafo seleziona deterministicamente cosa non può essere ignorato; LLM, test e reviewer valutano l'impatto.**
9. **Granularità tecnica simbolica.** Una modifica a un file non invalida automaticamente tutto ciò che condivide quel file: l'unità primaria è il simbolo/configuration unit realmente cambiato.
10. **Git conserva il contenuto storico; ReqGraph conserva la provenance semantica.**
11. **Generator e Reviewer devono essere modelli distinti.**

---

## 3. Modello concettuale

### 3.1 Categorie

| Categoria | Nodi | Domanda |
|---|---|---|
| **Intent & Semantics** | `Requirement`, `Clarification`, `Assumption` | Che cosa intendiamo? |
| **Behavioral Specification** | `Contract`, `Example` | Quale comportamento è richiesto e quali casi concreti lo testimoniano? |
| **Planning & Orchestration** | `Task` | Quale lavoro è stato autorizzato? |
| **Implementation & Verification** | `CodeUnit`, `ConfigUnit`, `Test` | Come è implementato e verificato? |
| **Quality & Investigation** | `Issue` | Quale possibile problema richiede triage/investigazione? |
| **Observed Evidence** | `ObservedBehavior` | Che cosa osserviamo realmente nel sistema/repository? |

`ObservedBehavior` è soprattutto un nodo di evidence/provenance. È fondamentale nel bootstrap legacy e può essere usato anche durante bug investigation o runtime analysis.

### 3.2 Ruolo centrale del Contract

Il `Contract` è il ponte tra intento e parte tecnica:

```text
Contract ──FORMALIZES──→ Requirement
Example  ──WITNESSES───→ Contract
Task     ──DERIVES_FROM→ Contract
CodeUnit ──IMPLEMENTS──→ Contract
ConfigUnit ──CONSTRAINS→ Contract
Test     ──TESTS────────→ Contract / CodeUnit / ConfigUnit
```

Nessun `Task` deriva direttamente dalla prosa.

---

## 4. Stati

ReqGraph separa la qualità della conoscenza dalla verifica tecnica.

### 4.1 `knowledge_status`

- `observed` — evidenza direttamente osservata;
- `inferred` — ricostruzione proposta a partire da evidenze;
- `generated` — artefatto generato nella normale pipeline, ancora da validare;
- `validated` — approvato dal gate previsto;
- `disputed` — contestato/in conflitto;
- `stale` — invalidato da una modifica semantica a monte.

### 4.2 `verification_status`

Usato soprattutto per artefatti tecnici:

- `not_applicable`
- `unknown`
- `needs_revalidation`
- `verified`
- `failed`

Esempio:

```text
Contract C7:
  knowledge_status = validated

CodeUnit CU12:
  knowledge_status = validated
  verification_status = needs_revalidation
```

Una modifica al codice non rende automaticamente sbagliato il Contract.

### 4.3 Versionamento

I nodi storici restano nel grafo.

```text
R2 ──SUPERSEDES──→ R1
C2 ──SUPERSEDES/REFINES──→ C1
CU2 ──SUPERSEDES──→ CU1
```

Per `CodeUnit`, Git conserva il contenuto storico; il grafo conserva almeno `path`, `symbol`, `hash`, eventuale `git_commit` e le relazioni semantiche.

---

## 5. Relazioni principali

### Semantica e specifica

- `CLARIFIES`: `Clarification|Assumption → Requirement`
- `FORMALIZES`: `Contract → Requirement`
- `WITNESSES`: `Example → Contract`
- `CONTRADICTS`: `Requirement|Contract → Requirement|Contract`
- `REFINES`: `Contract → Contract`
- `SUPERSEDES`: versioni di `Requirement`, `Contract`, `CodeUnit`, `ConfigUnit`

### Pianificazione e provenance

- `DERIVES_FROM`: `Task → Contract`
- `ADDRESSES`: `Task → Issue`
- `GENERATED_BY`: `CodeUnit|ConfigUnit|Test → Task`
- `GENERATED_FROM`: `Test → Example`

`GENERATED_BY` risponde a “durante quale Task è nato/modificato questo artefatto?”.  
`IMPLEMENTS` risponde invece a “quale Contract soddisfa questo artefatto?”.

### Implementazione e verifica

- `IMPLEMENTS`: `CodeUnit → Contract`
- `CONSTRAINS`: `ConfigUnit → Contract` quando una configurazione è parte del comportamento richiesto
- `TESTS`: `Test → Contract|CodeUnit|ConfigUnit`
- `DEPENDS_ON`: dipendenze tecniche esplicite fra `CodeUnit|ConfigUnit`

### Evidenza legacy

- `EVIDENCES`: `Test|CodeUnit|ConfigUnit → ObservedBehavior`
- `SUPPORTS`: `ObservedBehavior → Contract` candidato/validato
- `INFERRED_FROM`: `Example|Contract|Requirement → Test|CodeUnit|ConfigUnit|ObservedBehavior`

`INFERRED_FROM` non implica che l'artefatto sorgente sia stato originariamente generato dal nodo inferito.

### Issue

- `FOUND_DURING`: `Issue → Task`
- `AFFECTS`: `Issue → CodeUnit|ConfigUnit`
- `VIOLATES`: `Issue → Contract`
- `EXPLAINED_BY`: `Issue → Contract`
- `BLOCKS`: `Issue → Task`
- `ADDRESSES`: `Task → Issue`

---

## 6. Greenfield Mode

### Fase G0 — Ingest e critica dei Requirement

**Input:** prosa esterna. **Attori:** Human + Critic.

1. La prosa viene acquisita come `Requirement`.
2. Il Critic cerca ambiguità, lacune, contraddizioni e boundary cases.
3. Le domande diventano `Clarification`; eventuali decisioni temporanee diventano `Assumption`.
4. Gate: nessun Requirement prosegue con domande bloccanti non risolte.

Il PM/Product modifica il Requirement, non normalmente il Contract.

### Fase G1 — Formalizzazione

**Attore:** Formalizer → human review.

1. Generazione di `Contract` con preconditions, postconditions, invariants e acceptance criteria.
2. Generazione di `Example` comportamentali.
3. Gli Example devono coprire classi comportamentali significative, boundary/error path e non soltanto rispettare un numero fisso.
4. Soglia minima di default: 3 Example, almeno 1 edge case; è un gate minimo, non una garanzia di copertura completa.
5. L'umano valida prima gli Example e poi il Contract.

Se il Contract non è corretto:
- requisito ambiguo/incompleto → `Clarification` o nuova versione del `Requirement`;
- requisito corretto, formalizzazione errata → Contract `disputed`, feedback e rigenerazione.

### Fase G2 — Planning

1. Ogni `Task` deriva da almeno un Contract validato.
2. Il Task contiene Contract, Requirement di riferimento, Example assegnati, dipendenze e Definition of Done.
3. Un Task rappresenta lavoro autorizzato, non semplicemente una funzione da generare.

### Fase G3 — TDD e implementazione

Per ogni Task:

1. genera Test a partire dagli Example assegnati;
2. crea `Test ──GENERATED_FROM──→ Example`;
3. verifica RED quando applicabile;
4. genera/modifica CodeUnit/ConfigUnit;
5. crea `CodeUnit|ConfigUnit|Test ──GENERATED_BY──→ Task`;
6. crea/aggiorna `IMPLEMENTS`, `CONSTRAINS`, `TESTS`;
7. porta i test target a GREEN;
8. esegui regression suite rilevante;
9. Reviewer differente dal Codegen verifica Code/Config ↔ Contract e Contract ↔ Requirement;
10. aggiorna grafo e project state.

### Fase G4 — Chiusura

- consistency checks;
- open assumptions;
- contradictions;
- open/blocked issues;
- stale nodes;
- nodes needing revalidation;
- coverage Requirement → Contract → Example → Task → Test/Implementation.

---

## 7. Existing Project Bootstrap Mode

### B0 — Repository scan

La prima fase è principalmente deterministica.

Estrarre:

- `CodeUnit` a livello di simbolo (`path + symbol + hash`);
- `ConfigUnit` a livello di chiave/sezione/configuration concept;
- `Test`;
- import/call/dependency graph;
- route/API;
- model/schema/constraint;
- test assertions;
- documentazione, commenti, OpenAPI, migration;
- opzionalmente Git/PR/Jira come provenance storica.

Non creare ancora Requirement validati.

### B1 — Observed Behavior Extraction

Da test, codice, config e altre evidenze creare `ObservedBehavior`.

```text
Given order.status = shipped
When cancel_order
Observed CannotCancelOrder
```

con collegamenti `EVIDENCES`.

### B2 — Candidate Behavioral Specification

L'LLM raggruppa evidenze coerenti e propone `Example` e `Contract` con `knowledge_status=inferred`. La provenance viene registrata con `INFERRED_FROM`.

### B3 — Candidate Intent

Da Contract/evidenze si possono proporre `Requirement` candidati:

```text
knowledge_status = inferred
source = reverse-engineered
```

Regola: **il codice non viene mai assunto come intent originale.**

### B4 — Human Reverse-Specification Review

Per ogni area funzionale l'utente può scegliere:

- corretto → valida Requirement/Contract;
- comportamento corretto ma wording da cambiare;
- possibile bug → crea `Issue`;
- requisito ambiguo → crea `Clarification`;
- comportamento obsoleto;
- non abbastanza evidenza.

### B5 — Convergenza

Dopo la validazione, il ramo entra nel normale lifecycle ReqGraph. Non si inventano Task storici se Git/Jira/PR non forniscono evidenza sufficiente.

---

## 8. Issue lifecycle

### 8.1 Principio

Una `Issue` è una **segnalazione da investigare**, non una dichiarazione che esiste sicuramente un bug.

Può essere creata:

- manualmente da PM, developer, tester o utente autorizzato;
- automaticamente da Critic/Codegen/Reviewer durante un Task;
- durante bootstrap legacy;
- da failure di test/regressione.

### 8.2 Discovery fuori scope

Se durante `T12` l'agente trova un possibile bug non necessario per completare T12:

```text
create Issue
record evidence
continue T12
```

Non modifica il codice relativo all'Issue.

Se impedisce il Task corrente:

```text
Issue ──BLOCKS──→ Task
Task.status = blocked
```

e serve una decisione umana.

### 8.3 Stati Issue

Workflow:

- `open`
- `triaging`
- `ready`
- `in_progress`
- `resolved`
- `closed`
- `rejected`

Classification:

- `unknown`
- `suspected_bug`
- `confirmed_bug`
- `expected_behavior`
- `specification_gap`
- `requirement_ambiguity`
- `regression`
- `tech_debt`
- `duplicate`

### 8.4 Issue → Task

Solo quando l'umano autorizza la risoluzione viene creato un Task:

```text
Task ──ADDRESSES──→ Issue
```

La correzione segue la normale pipeline Contract/Example/Test/Code/Review.

---

## 9. Change propagation e impact analysis

### 9.1 Cambio semantico

Quando:

```text
R2 ──SUPERSEDES──→ R1
```

il vecchio ramo derivato viene marcato `stale`:

```text
R1
  → Contract
    → Example
    → Task
      → CodeUnit / ConfigUnit / Test
```

I nodi restano nel grafo.

### 9.2 Cambio tecnico

Una modifica tecnica non rende automaticamente stale i Requirement/Contract collegati.

Pipeline:

1. rileva diff Git/filesystem;
2. identifica precisamente `CodeUnit`/`ConfigUnit` realmente cambiati;
3. aggiorna hash/versione;
4. traversal deterministico per trovare Contract, Test e dipendenze direttamente rilevanti;
5. marca gli artefatti tecnici coinvolti `verification_status=needs_revalidation`;
6. LLM Impact Analyst valuta semanticamente il diff rispetto ai Contract candidati;
7. esegui test/reviewer necessari;
8. `verified` se conforme, `failed` se esiste evidenza di regressione/violazione;
9. se necessario crea `Issue` e, dopo autorizzazione, un nuovo Task.

### 9.3 Non invalidare per semplice co-location nel file

Un file è un contenitore fisico, non un'unità semantica.

```text
service.py
  cancel_order()    → CU1
  refund_order()    → CU2
  calculate_total() → CU3
```

Se cambia solo `CU1`, CU2/CU3 non vengono automaticamente rivalidati.

### 9.4 Configurazione globale: evitare il “settings.py invalida tutto”

Configurazioni come `settings.py` richiedono granularità semantica.

```text
settings.py

DATABASES.default.engine → CFG1
TIME_ZONE                → CFG2
AUTHENTICATION_BACKENDS  → CFG3
FEATURE_X_ENABLED        → CFG4
```

Il diff:

```text
FEATURE_X_ENABLED = False → True
```

modifica `CFG4`, non l'intero file.

Solo dipendenze materializzate o candidate semanticamente vengono considerate. Per configurazioni altamente pervasive:

- traversal deterministico su riferimenti/import/dependency espliciti;
- ricerca semantica come candidate discovery;
- LLM Impact Analyst per classificare l'effettivo rischio;
- **mai “tutti i file che importano settings → invalidati” come regola automatica.**

Il grafo deve essere conservativo nella selezione dei candidati, ma la revalidation deve essere proporzionata all'evidenza.

---

## 10. Retrieval

Strategia primaria:

```text
vector entry point
  +
typed traversal
  +
status/provenance filtering
  +
balanced context
```

### 10.1 Task context

Sempre includere:

```text
Task
 → Contract
 → Requirement
 → Example validati
 → Issue addressed/blocked
 → Test target
 → CodeUnit/ConfigUnit target
 → dipendenze rilevanti
```

### 10.2 Bootstrap context

Per reverse specification includere evidence packs separando chiaramente:

```text
[OBSERVED]
[INFERRED]
[VALIDATED]
[STALE]
[NEEDS_REVALIDATION]
```

### 10.3 Impact context

L'Impact Analyst riceve:

- diff;
- CodeUnit/ConfigUnit cambiati;
- Contract direttamente collegati;
- test relativi;
- dipendenze candidate;
- Issue aperte correlate.

La similarità semantica può proporre candidati, ma non crea da sola invalidazioni.

---

## 11. Project state

```text
/.project-state/
  project.json
  todo-global.json
  issues/
    issue-<id>.json
  bootstrap/
    bootstrap-state.json
  phases/
    phase-NN/
      todo-phase.json
      tasks/
        task-NN-NN.json
  decisions-log.md
```

La project state è memoria operativa per gli agenti; Neo4j resta la fonte delle relazioni e della traceability.

---

## 12. Ruoli LLM

| Ruolo | Responsabilità |
|---|---|
| Critic | ambiguità, gap, contraddizioni |
| Formalizer | Contract, Example, candidate specification |
| Planner | derivazione Task e Definition of Done |
| Codegen | Test + implementazione autorizzata |
| Reviewer | fedeltà Code/Config ↔ Contract ↔ Requirement |
| Librarian | extraction, graph update, embeddings |
| Reverse Analyst | bootstrap legacy: ObservedBehavior e candidate specification |
| Impact Analyst | analisi semantica di diff e revalidation |
| Issue Triage | classificazione assistita delle Issue, senza autorizzare modifiche |

I ruoli possono condividere lo stesso modello fisico, ma `Reviewer` deve essere diverso dal `Codegen`.

Il binding modello è per-ruolo e multi-provider: ogni ruolo dichiara indipendentemente `provider` + `model` (vedi `models-config-v0.2.json`, sezione `providers`). I provider supportati out-of-the-box sono `anthropic` e `openai`; l'elenco è estendibile senza cambi di schema, aggiungendo l'id provider all'allowlist e il relativo adapter nel layer `graph-cli`/OpenCode. Il vincolo `Reviewer ≠ Codegen` si valuta sulla coppia fisica `(provider, model)`, non sulla sola stringa id — quindi è ammesso, ad esempio, avere `codegen` su `openai` e `reviewer` su `anthropic` (o viceversa), oltre a due modelli diversi sullo stesso provider.

---

## 13. `graph-cli` previsto

Greenfield:

```text
init
ingest-requirements
run-critic
formalize
derive-tasks
context <task-id>
run-task <task-id>
complete <task-id>
```

Legacy:

```text
bootstrap-scan
bootstrap-observe
bootstrap-infer
bootstrap-review
```

Maintenance:

```text
detect-changes
impact <codeunit|configunit>
revalidate <node-id>
open-issue
triage-issue <issue-id>
authorize-issue <issue-id>
invalidate <node-id>
consistency-check
status
```

OpenCode non scrive direttamente su Neo4j: passa attraverso `graph-cli`/application layer.

---

## 14. Consistency checks

Minimi:

- Requirement validato senza Contract validato;
- Contract validato senza Example coverage minima;
- Example validato senza Contract;
- Test generato senza `GENERATED_FROM` quando nasce da Example;
- CodeUnit/Test/ConfigUnit generati nel lifecycle senza `GENERATED_BY` Task;
- CodeUnit validato senza Contract implementato, salvo artefatti legacy ancora non ricostruiti;
- Issue `confirmed_bug` chiusa senza Task/decisione di risoluzione o motivazione;
- Task che modifica artefatti fuori scope senza Issue/decisione;
- `needs_revalidation` non risolti a fine phase;
- contradiction open;
- stale branch presente nel context senza label;
- candidate Requirement/Contract legacy marcato `validated` senza human validation provenance.

---

## 15. MVP / vertical slices

### Slice A — Greenfield

```text
Requirement
→ Clarification
→ Contract
→ Example
→ human validation
→ Task
→ Test RED
→ Code GREEN
→ Reviewer
→ Requirement change
→ stale cascade
→ reimplementation
```

### Slice B — Existing Project

Repository minimale:

```text
orders.py
test_orders.py
```

Dimostrare:

```text
scan
→ CodeUnit/Test
→ ObservedBehavior
→ inferred Example/Contract/Requirement
→ human validation
→ normal lifecycle
```

### Slice C — Issue + out-of-scope discovery

Durante un Task:
- agente rileva un possibile bug non correlato;
- crea Issue;
- non modifica il codice;
- human autorizza;
- nuovo Task;
- fix via normale pipeline.

### Slice D — Technical revalidation

Modifica a CodeUnit/ConfigUnit condiviso:
- candidate selection deterministica;
- `needs_revalidation`;
- impact analysis;
- rerun test;
- nessuna invalidazione indiscriminata del progetto.

---

## 16. Regole non negoziabili

1. Nessuna modifica fuori Task autorizzato, salvo operazioni meccaniche necessarie e dichiarate dal Task.
2. Nessun comportamento legacy diventa intent validato senza human review.
3. Nessun Contract rigenerato sostituisce silenziosamente il Requirement.
4. Nessuna modifica di file invalida automaticamente tutte le CodeUnit del file.
5. Nessuna modifica di configurazione globale invalida automaticamente tutto il progetto.
6. Ogni artefatto generato conserva provenance verso Task/evidenza.
7. Ogni ramo storico resta interrogabile.
8. I cambiamenti semantici producono `stale`; i cambiamenti tecnici producono prima `needs_revalidation`.
