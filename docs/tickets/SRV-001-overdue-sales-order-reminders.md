# SRV-001: Overdue Sales Order bell reminders

Priority: 1
Status: Implemented; blanket reminders for all enabled Desk users.

Notify portal notification bell at 5, 10, 15 and subsequent five-day overdue milestones. Use the earliest delivery date of an undelivered order item (header delivery date as fallback). Ignore drafts, cancelled, closed/on-hold and fully delivered orders. Send the same reminder to every enabled System User; no owner, assignment, role or document-access targeting. Order access permissions remain unchanged. Retries must not duplicate the same milestone; delayed scheduler runs send the latest outstanding milestone once. Notification links to the order. No WhatsApp, Telegram or email.

Deliverable: Separate production and dev PRs. Merge dev and production after validation, per the updated user instruction.

Implementation: Daily scheduler creates unread Alert-type Notification Logs linked to the order. Deterministic order/due-date/milestone/recipient keys deduplicate retries. The audience is all enabled System Users. Reminder delivery does not depend on owner, Assign To, sales roles, document read permission or notification preferences. After deployment run the normal site migration to register the daily scheduler event; enable scheduler/workers. No email is sent by Alert-type bell logs.

Validation: 6 tests pass, including persisted Notification Logs at 5/10/15 days, retries, delayed runs, completed/inactive orders, item dates and blanket delivery to an unassigned user without order access, plus disabled/Website User exclusions.
