"""Date-only recurrence rules, independent of Frappe and its database."""

from calendar import monthrange
from datetime import date, timedelta

MAX_OCCURRENCES = 1000
MAX_RANGE_DAYS = 3660
FREQUENCIES = ("Once", "Daily", "Weekdays", "Weekly", "Monthly", "Custom")


def production_dates(start, end, frequency, interval=1, unit="Days", weekdays=None, custom_dates=None):
	start, end = date.fromisoformat(str(start)), date.fromisoformat(str(end))
	if start > end or (end - start).days > MAX_RANGE_DAYS:
		raise ValueError("Choose an ordered date range of at most ten years.")
	if frequency not in FREQUENCIES:
		raise ValueError("Choose a supported frequency.")
	if frequency == "Once":
		return [start]
	if frequency == "Custom":
		if unit == "Dates":
			result = sorted({date.fromisoformat(str(value)) for value in (custom_dates or [])})
			if not result or any(value < start or value > end for value in result):
				raise ValueError("Select dates within the schedule range.")
			return _bounded(result)
		if unit not in ("Days", "Weeks", "Months"):
			raise ValueError("Choose days, weeks, months, or explicit dates.")
		if isinstance(interval, bool) or int(interval) != float(interval) or int(interval) < 1:
			raise ValueError("The recurrence interval must be a positive whole number.")
		interval = int(interval)
	else:
		interval = 1
		unit = {"Monthly": "Months", "Weekly": "Weeks"}.get(frequency, "Days")

	selected = set(weekdays or [start.weekday()])
	if any(value not in range(7) for value in selected):
		raise ValueError("Weekdays must be between Monday and Sunday.")
	result = []
	if unit == "Months":
		offset = 0
		while True:
			month_index = start.year * 12 + start.month - 1 + offset
			year, month = divmod(month_index, 12)
			value = date(year, month + 1, min(start.day, monthrange(year, month + 1)[1]))
			if value > end:
				break
			result.append(value)
			offset += interval
	else:
		value = start
		anchor_week = start - timedelta(days=start.weekday())
		while value <= end:
			if unit == "Weeks":
				include = ((value - anchor_week).days // 7) % interval == 0 and value.weekday() in selected
			else:
				include = (value - start).days % interval == 0
				if frequency == "Weekdays":
					include = include and value.weekday() < 5
			if include:
				result.append(value)
			value += timedelta(days=1)
	return _bounded(result)


def _bounded(result):
	if not result or len(result) > MAX_OCCURRENCES:
		raise ValueError(f"A schedule must generate between 1 and {MAX_OCCURRENCES} assignments.")
	return result
