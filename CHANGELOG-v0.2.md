# ReqGraph v0.2 — Changelog architetturale

## Principali cambiamenti rispetto alla v0.1

- Supporto esplicito a **Greenfield Mode** e **Existing Project Bootstrap Mode**.
- Nuovi nodi: `Issue`, `ObservedBehavior`, `ConfigUnit`.
- Provenance: `Test -> GENERATED_FROM -> Example` e `CodeUnit|ConfigUnit|Test -> GENERATED_BY -> Task`.
- Distinzione fra origine del lavoro (`Task -> DERIVES_FROM -> Contract`) e significato dell'implementazione (`CodeUnit -> IMPLEMENTS -> Contract`).
- Separazione di `knowledge_status` e `verification_status`; introdotto `needs_revalidation`.
- Issue workflow con regola **Discovery is not authorization to modify**.
- Reverse bootstrap: `Repository -> Code/Test/Config -> ObservedBehavior -> inferred Example/Contract/Requirement -> Human validation`.
- `ConfigUnit` per evitare invalidazioni grossolane di file globali come Django `settings.py`.
- Impact analysis: candidate discovery deterministica -> LLM impact analysis -> test/reviewer -> verified/failed.
- Versionamento/provenance dei `CodeUnit` con `SUPERSEDES`.
- Nuovi ruoli: `Planner`, `Reverse Analyst`, `Impact Analyst`, `Issue Triage`.
- Il minimo di 3 Example resta un gate minimo, non una garanzia di copertura completa.
