# SRV-001: Overdue Sales Order bell reminders

Priority: 1
Status: Implemented; default recipients: owner and assigned users.

Notify portal notification bell at 5, 10, 15 and subsequent five-day overdue milestones. Use the earliest delivery date of an undelivered order item (header delivery date as fallback). Ignore drafts, cancelled, closed/on-hold and fully delivered orders. Respect recipient permissions and notification preferences. Retries must not duplicate the same milestone; delayed scheduler runs send the latest outstanding milestone once. Notification links to the order. No WhatsApp, Telegram or email.

Deliverable: Separate production and dev PRs. Merge dev only after validation; leave production open.

Implementation: Daily scheduler creates unread Alert-type Notification Logs linked to the order. Deterministic order/due-date/milestone/recipient keys deduplicate retries. Current default audience is owner plus open ToDo assignees, filtered to enabled System Users with order read access and notifications enabled. After deployment run the normal site migration to register the daily scheduler event; enable scheduler/workers. No email is sent by Alert-type bell logs.

Validation: 6 tests pass, including persisted Notification Logs at 5/10/15 days, retries, delayed runs, completed/inactive orders, item dates and recipient restrictions.
