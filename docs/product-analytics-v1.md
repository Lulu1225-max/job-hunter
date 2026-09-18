# Product Analytics v1

Events are written after committed business operations in a separate transaction. A failed analytics write is logged and does not change the business response. Metadata is allowlisted in `app/services/analytics.py`; no resume, job description, question, answer, prompt, or token body is retained. `is_demo` compares the current user's stored email with the configured demo email. User deletion cascades to events; Job, Resume, and Experience deletion sets the corresponding event ID to NULL.

One `job_imported` event is stored per confirmed import that creates or updates at least one Job. `imported_count` counts newly created Jobs. `duplicate_count` counts existing Jobs updated or skipped as unchanged during that import; blank rows are excluded. This keeps batch imports from producing excessive events. Deep Match starts when the explicit match POST is accepted after authentication; a cached result still has a started and completed event, with `cache_hit=true`. Latency uses server `perf_counter` from request/service entry through successful completion or handled failure.

```sql
SELECT event_name, COUNT(*) FROM analytics_events GROUP BY event_name ORDER BY COUNT(*) DESC;

SELECT COUNT(*) FILTER (WHERE event_name = 'resume_match_completed')::numeric
       / NULLIF(COUNT(*) FILTER (WHERE event_name = 'resume_match_started'), 0) AS completion_rate
FROM analytics_events;

SELECT COUNT(*) FILTER (WHERE event_name = 'resume_match_failed')::numeric
       / NULLIF(COUNT(*) FILTER (WHERE event_name = 'resume_match_started'), 0) AS failure_rate
FROM analytics_events;

SELECT error_type, COUNT(*) FROM analytics_events
WHERE event_name = 'resume_match_failed'
GROUP BY error_type ORDER BY COUNT(*) DESC;

SELECT event_name, ROUND(AVG(latency_ms), 1) AS avg_latency_ms
FROM analytics_events WHERE latency_ms IS NOT NULL
GROUP BY event_name ORDER BY event_name;

SELECT stage, event_count FROM (
  SELECT 1 AS step, 'Job Created / Imported' AS stage, COUNT(*) AS event_count
    FROM analytics_events WHERE event_name IN ('job_created', 'job_imported')
  UNION ALL SELECT 2, 'Resume Match Started', COUNT(*) FROM analytics_events WHERE event_name = 'resume_match_started'
  UNION ALL SELECT 3, 'Resume Match Completed', COUNT(*) FROM analytics_events WHERE event_name = 'resume_match_completed'
  UNION ALL SELECT 4, 'Experience Selected', COUNT(*) FROM analytics_events WHERE event_name = 'experience_selected'
  UNION ALL SELECT 5, 'Interview Answer Generated', COUNT(*) FROM analytics_events WHERE event_name = 'interview_answer_generated'
) stages ORDER BY step;
```

The stage query counts events, not unique users or a joined cohort. A batch import is one event; use `SUM((metadata->>'imported_count')::int)` for imported Job volume. Filter with `metadata->>'is_demo' = 'false'` to exclude Demo activity.
