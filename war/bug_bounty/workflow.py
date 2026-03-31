"""
Report lifecycle state machine.

Valid transitions:
  new          -> triaging, rejected
  triaging     -> accepted, rejected, duplicate
  accepted     -> in_progress, rejected
  in_progress  -> fixed, accepted          (back if needs more info)
  fixed        -> bounty_paid, closed
  bounty_paid  -> closed
  duplicate    -> closed
  rejected     -> closed
  closed       -> (terminal)
"""

from datetime import datetime
from typing import Optional
from .models import Status, Report, AuditLog, Database, Researcher


# Allowed status transitions
TRANSITIONS: dict[str, list[str]] = {
    Status.NEW.value:          [Status.TRIAGING.value, Status.REJECTED.value],
    Status.TRIAGING.value:     [Status.ACCEPTED.value, Status.REJECTED.value, Status.DUPLICATE.value],
    Status.ACCEPTED.value:     [Status.IN_PROGRESS.value, Status.REJECTED.value],
    Status.IN_PROGRESS.value:  [Status.FIXED.value, Status.ACCEPTED.value],
    Status.FIXED.value:        [Status.BOUNTY_PAID.value, Status.CLOSED.value],
    Status.BOUNTY_PAID.value:  [Status.CLOSED.value],
    Status.DUPLICATE.value:    [Status.CLOSED.value],
    Status.REJECTED.value:     [Status.CLOSED.value],
    Status.CLOSED.value:       [],
}

TERMINAL_STATUSES = {Status.CLOSED.value}
RESOLUTION_STATUSES = {Status.FIXED.value, Status.BOUNTY_PAID.value, Status.CLOSED.value,
                       Status.REJECTED.value, Status.DUPLICATE.value}


class WorkflowError(Exception):
    pass


class ReportWorkflow:
    def __init__(self, db: Database, actor: str = "system"):
        self.db = db
        self.actor = actor

    def transition(self, report_id: str, new_status: str,
                   notes: Optional[str] = None,
                   bounty_amount: Optional[float] = None,
                   duplicate_of: Optional[str] = None,
                   assigned_to: Optional[str] = None) -> Report:
        """
        Transition a report to a new status.
        Raises WorkflowError if the transition is not allowed.
        """
        report = self.db.get_report(report_id)
        if not report:
            raise WorkflowError(f"Report {report_id} not found.")

        allowed = TRANSITIONS.get(report.status, [])
        if new_status not in allowed:
            raise WorkflowError(
                f"Cannot transition '{report.status}' -> '{new_status}'. "
                f"Allowed: {allowed or ['(none — terminal state)']}"
            )

        old_status = report.status
        report.status = new_status

        if notes:
            separator = "\n---\n" if report.notes else ""
            report.notes = f"{report.notes}{separator}[{datetime.utcnow().isoformat()}] {notes}"

        if bounty_amount is not None:
            report.bounty_amount = bounty_amount

        if duplicate_of is not None:
            report.duplicate_of = duplicate_of

        if assigned_to is not None:
            report.assigned_to = assigned_to

        if new_status in RESOLUTION_STATUSES and not report.resolved_at:
            report.resolved_at = datetime.utcnow().isoformat()

        self.db.update_report(report)

        # Audit log
        self.db.log_action(AuditLog(
            report_id=report_id,
            action=f"status_change",
            actor=self.actor,
            old_value=old_status,
            new_value=new_status,
        ))

        # Update researcher stats on accept/pay
        if new_status == Status.ACCEPTED.value and old_status not in (Status.ACCEPTED.value,):
            self._increment_researcher(report.researcher_id, accepted=True)

        if new_status == Status.BOUNTY_PAID.value and report.bounty_amount > 0:
            self._pay_researcher(report.researcher_id, report.bounty_amount)

        return report

    def start_triage(self, report_id: str) -> Report:
        return self.transition(report_id, Status.TRIAGING.value)

    def accept(self, report_id: str, notes: Optional[str] = None,
               assigned_to: Optional[str] = None) -> Report:
        return self.transition(report_id, Status.ACCEPTED.value,
                               notes=notes, assigned_to=assigned_to)

    def reject(self, report_id: str, reason: str) -> Report:
        return self.transition(report_id, Status.REJECTED.value, notes=f"Rejected: {reason}")

    def mark_duplicate(self, report_id: str, original_id: str) -> Report:
        return self.transition(report_id, Status.DUPLICATE.value,
                               notes=f"Duplicate of {original_id}",
                               duplicate_of=original_id)

    def mark_in_progress(self, report_id: str, assigned_to: Optional[str] = None) -> Report:
        return self.transition(report_id, Status.IN_PROGRESS.value, assigned_to=assigned_to)

    def mark_fixed(self, report_id: str, notes: Optional[str] = None) -> Report:
        return self.transition(report_id, Status.FIXED.value, notes=notes)

    def pay_bounty(self, report_id: str, amount: float) -> Report:
        return self.transition(report_id, Status.BOUNTY_PAID.value,
                               notes=f"Bounty paid: ${amount:.2f}",
                               bounty_amount=amount)

    def close(self, report_id: str, notes: Optional[str] = None) -> Report:
        return self.transition(report_id, Status.CLOSED.value, notes=notes)

    def _increment_researcher(self, researcher_id: str, accepted: bool = False):
        r = self.db.get_researcher(researcher_id)
        if r:
            r.report_count += 1
            if accepted:
                r.accepted_count += 1
            self.db.update_researcher(r)

    def _pay_researcher(self, researcher_id: str, amount: float):
        r = self.db.get_researcher(researcher_id)
        if r:
            r.total_earned += amount
            self.db.update_researcher(r)
