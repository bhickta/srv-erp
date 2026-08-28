import json
import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path


@dataclass(frozen=True)
class BridgeConfig:
	frappe_url: str
	api_key: str
	api_secret: str
	erpnext_company: str
	target_id: str
	tally_company: str
	tally_url: str = "http://127.0.0.1:9000"
	poll_interval_seconds: int = 60
	batch_size: int = 20
	listen_host: str = "127.0.0.1"
	listen_port: int = 8765
	request_timeout_seconds: int = 30
	from_date: str | None = None
	voucher_date_override: str | None = None

	@classmethod
	def load(cls, path):
		path = Path(path)
		with path.open(encoding="utf-8") as handle:
			values = json.load(handle)

		env_values = {
			"api_key": os.getenv("SRV_TALLY_API_KEY"),
			"api_secret": os.getenv("SRV_TALLY_API_SECRET"),
		}
		values.update({key: value for key, value in env_values.items() if value})
		config = cls(**values)
		config.validate()
		return config

	def validate(self):
		missing = [
			name
			for name in ("frappe_url", "api_key", "api_secret", "erpnext_company", "target_id", "tally_company")
			if not getattr(self, name)
		]
		if missing:
			raise ValueError(f"Missing bridge configuration: {', '.join(missing)}")
		if not self.frappe_url.lower().startswith(("http://", "https://")):
			raise ValueError("frappe_url must be an HTTP or HTTPS URL")
		if not self.tally_url.lower().startswith("http://"):
			raise ValueError("tally_url must be an HTTP URL")
		if not 1 <= int(self.batch_size) <= 100:
			raise ValueError("batch_size must be between 1 and 100")
		if self.voucher_date_override:
			try:
				date.fromisoformat(self.voucher_date_override)
			except ValueError as exc:
				raise ValueError("voucher_date_override must use YYYY-MM-DD format") from exc
