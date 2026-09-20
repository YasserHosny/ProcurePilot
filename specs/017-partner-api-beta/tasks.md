# R3.4 Partner API Beta Tasks

- [x] Define the read-only partner API scope and constitution constraints.
- [x] Add typed partner module exports and read facade.
- [x] Register order list, order detail, and catalogue list routes.
- [x] Add service delegation unit coverage.
- [x] Add route-shape contract coverage proving the partner surface is read-only.
- [x] Add database-backed cross-tenant integration coverage to the full R3.4 integration gate.
- [x] Add outbound webhook subscriptions, audit-event outbox trigger, signed delivery worker, and bounded retries.
- [x] Add freshness scoring and refresh scheduling in the next R3.4 increment.
- [x] Add provider-neutral catalogue connector protocol, normalized page DTO, and stub factory.
- [x] Enqueue due refresh schedules through the existing tenant-scoped ingestion queue.
- [x] Link refresh schedules to the latest completed supplier CSV upload before enqueueing.
- [x] Create tenant-isolated normalized CSV previews for human review without committing prices.
- [x] Expose paginated review listing and owner/buyer approval or rejection endpoints.
- [x] Wire pending refresh previews into the matching queue with bilingual approve/reject actions.
- [x] Add hosted-stack smoke coverage for tenant-scoped review rendering.
