# ProcurePilot — Operations Runbook

> Step-by-step procedures for running ProcurePilot in production.

---

## 1. On-Call Basics

- Primary dashboards: Bunny Magic Containers, Supabase Dashboard, Sentry, PostHog.
- Severity levels:
  - **SEV-1** — platform down or data incorrect affecting payments/audit; page founder.
  - **SEV-2** — degraded experience; investigate within 1 hour.
  - **SEV-3** — non-urgent issue; ticket for next business day.

## 2. Health Checks

```bash
# Backend
curl https://<project>-api.<domain>/api/health

# Frontend
curl -I https://<project>.<domain>/index.html
```

## 3. Common Failures

### 3.1 Backend container unhealthy
1. Check Bunny container logs for crash or OOM.
2. If image issue, roll back to previous `ghcr` tag in Bunny dashboard.
3. Verify `BACKEND_HOST` is not set incorrectly on frontend.
4. If DB connection fails, check Supabase connection pooler / PgBouncer.

### 3.2 Extraction latency spikes
1. Check Bedrock/Azure status pages.
2. Review Sentry/PostHog for queue depth.
3. Scale extraction-worker container if queue > threshold.
4. Confirm document hash cache hit rate.

### 3.3 Matching precision drops
1. Run AI eval harness on latest benchmark.
2. Check for new supplier description patterns not in training data.
3. Lower auto-accept threshold temporarily if human review capacity exists.
4. Add new aliases from recent corrections.

### 3.4 Review queue backlog
1. Dashboard: review-band size and items per 100 lines.
2. Prioritise by financial impact.
3. If persistent, widen candidate generation or improve alias learning.

### 3.5 Mobile push failures
1. Check Expo push service status.
2. Verify push tokens are current in tenant profile.
3. Test deep link routing.

## 4. Scaling Actions

- **Database CPU > 70% sustained:** enable Supabase read replicas or review query plans.
- **Storage > 80%:** configure lifecycle rules for old source documents.
- **Backend CPU > 80%:** increase Bunny container CPU/ram or add second container.
- **Extraction queue > 1000 documents:** scale extraction-worker horizontally.

## 5. Backup & Restore

- Supabase provides daily automated backups.
- Test restore monthly in a separate project.
- Document RPO: 24 hours; RTO: 4 hours.

## 6. Security Incidents

1. Revoke affected user sessions via Supabase Auth.
2. Audit `AuditEvent` for suspicious actions.
3. Rotate leaked secrets.
4. Notify affected tenants per DPA.
5. Post-incident review within 5 business days.

## 7. Deployment Day Checklist

- [ ] Backend `.env` has all required credentials.
- [ ] `/api/health` responds.
- [ ] Frontend builds with `ng build --configuration=production`.
- [ ] `docker compose up --build` succeeds locally.
- [ ] GHCR images pushed with `latest` tag.
- [ ] Bunny containers updated and healthy.
- [ ] RLS enabled on all tables.
- [ ] Smoke test: onboard → upload → extract → compare → record saving.

## 8. Contact Escalation

- Engineering lead — technical issues.
- Founder / Product Lead — commercial, prioritisation, customer comms.
- AI lead — model/prompt regressions.
