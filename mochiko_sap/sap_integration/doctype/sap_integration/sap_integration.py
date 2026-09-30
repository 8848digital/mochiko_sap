# Copyright (c) 2024, 8848 Digital LLP and contributors
# For license information, please see license.txt

import frappe
import requests
from frappe import _
from frappe.model.document import Document
from frappe.utils.background_jobs import is_job_enqueued
from datetime import datetime, timedelta
from random import randint
from frappe.utils import get_datetime, now_datetime
from croniter import CroniterBadCronError, croniter


class SAPIntegration(Document):
	def validate(self):
		if self.event_frequency == "Cron":
			if not self.cron_format:
				frappe.throw(_("Cron format is required for job types with Cron frequency."))
			try:
				croniter(self.cron_format)
			except CroniterBadCronError:
				frappe.throw(
					_("{0} is not a valid Cron expression.").format(
						f"<code>{self.cron_format}</code>"
					),
					title=_("Bad Cron Expression"),
				)

	def enqueue(self, force=False):
		if (
			self.is_event_due() or force
		):  # set hour in sap inegration or more, to trigger manual job execute
			if not self.is_job_in_queue():
				frappe.enqueue(
					self.trigger_requests,
					queue=self.get_queue_name(),
					job_id=self.rq_job_id + "-trigger_requests",
					deduplicate=True,
				)
				self.db_set("last_execution", now_datetime(), update_modified=False)
				return True
			else:
				frappe.log_error(
					f"Skipped queueing SAP Integration because it was found in queue for {frappe.local.site}"
				)

		return False

	def get_queue_name(self):
		return "long" if ("Long" in self.event_frequency) else "default"

	@property
	def rq_job_id(self):
		"""Unique ID created to deduplicate jobs with single RQ call."""
		return "scheduled_job::sap_integration.execute"

	def is_event_due(self, current_time=None):
		"""Return true if event is due based on time lapsed since last execution"""
		# if the next scheduled event is before NOW, then its due!
		return self.get_next_execution() <= (current_time or now_datetime())

	def is_job_in_queue(self) -> bool:
		return is_job_enqueued(self.rq_job_id)

	@property
	def next_execution(self):
		return self.get_next_execution()

	def get_next_execution(self):
		CRON_MAP = {
			"Yearly": "0 0 1 1 *",
			"Annual": "0 0 1 1 *",
			"Monthly": "0 0 1 * *",
			"Monthly Long": "0 0 1 * *",
			"Weekly": "0 0 * * 0",
			"Weekly Long": "0 0 * * 0",
			"Daily": "0 0 * * *",
			"Daily Long": "0 0 * * *",
			"Hourly": "0 * * * *",
			"Hourly Long": "0 * * * *",
			"All": f"*/{(frappe.get_conf().scheduler_interval or 240) // 60} * * * *",
		}

		if not self.cron_format:
			self.cron_format = CRON_MAP.get(self.event_frequency)

		last_execution = get_datetime(self.last_execution or self.creation)
		next_execution = croniter(self.cron_format, last_execution).get_next(datetime)

		jitter = 0
		if "Long" in self.event_frequency:
			jitter = randint(1, 600)
		return next_execution + timedelta(seconds=jitter)

	def trigger_requests(self):
		if not self.enabled:
			return

		filters = self.get_filters()
		pending_requests = frappe.get_all(
			"SAP Request Log",
			filters=filters,
			pluck="name",
			limit=self.batch_size,
			order_by="creation asc",
		)
		# TODO frappe enqueue
		# Process all requests in parallel 19th feb updated as per enqueue
		for request_name in pending_requests:
			frappe.enqueue(
				"mochiko_sap.sap_integration.doctype.sap_integration.sap_integration.process_sap_request",
				request_name=request_name,
				queue="long",
				job_id=f"sap_request_{request_name}",  # Unique job ID
				deduplicate=True,  # Ensures the same job is not queued twice
			)

	def get_headers(self):
		return {"Content-Type": "application/json"}

	def get_payload(self):
		payload = {}
		for row in self.header_parameters:
			if row.enabled:
				payload[row.key] = row.value
		return payload

	def get_timeout(self):
		return (self.connect_timeout or 60, self.read_timeout or 120)

	def get_secondary_payload(self):
		payload = {}
		for row in self.db2_header_parameters:
			if row.enabled:
				payload[row.key] = row.value
		return payload

	def get_filters(self):
		filters = {}
		pickup_status = ["Pending"]
		if self.allow_retry:
			pickup_status.append("Error")
			filters.update({"retry_count": ["<", self.max_retry]})
		if self.applicable_doctypes:
			filters.update(
				{"linked_doctype": ["in", [row.document_type for row in self.applicable_doctypes]]}
			)
		filters.update(
			{
				"request_status": ["in", pickup_status],
				"creation": [
					">=",
					now_datetime() - timedelta(minutes=self.max_time_in_minutes or 1440),
				],
			}
		)
		return filters

	def generate_session(self, is_primary=True):
		try:
			if not self.enabled:
				return
			url = self.base_url if is_primary else self.sports_base_url
			headers = self.get_headers()
			payload = self.get_payload() if is_primary else self.get_secondary_payload()
			# Send the POST request
			response = requests.post(
				url + "Login", json=payload, headers=headers, timeout=self.get_timeout()
			)

			# If successful, return the session ID and URL
			return self.handle_response(response=response, is_primary=is_primary)
		except Exception as e:
			# Log the exception message
			frappe.log_error(message=repr(e), title="Error in SAP API Auth")
			return

	def handle_response(self, response, is_primary=True):
		if response.status_code == 200:
			session_id = response.json().get("SessionId")
			if is_primary:
				# self.session_id = session_id
				frappe.db.set_value(self.doctype, self.name, "session_id", session_id)
				frappe.cache.set_value("sap_session_id", session_id)
			else:
				# self.session_id_2 = session_id
				frappe.db.set_value(self.doctype, self.name, "session_id_2", session_id)
				frappe.cache.set_value("sap_session_id_2", session_id)
			frappe.db.commit()  # Commit to ensure session ID is saved // nosemgrep
			# self.save()
			return response
		frappe.log_error(message=response.text, title="Error in SAP API Auth")
		return


# cron job
def execute():
	frappe.get_single("SAP Integration").enqueue(force=True)


def process_sap_request(request_name):

	sap_settings = frappe.get_single("SAP Integration")
	if not sap_settings.enabled:
		return

	request = frappe.get_doc("SAP Request Log", request_name)

	status_filter = ["Pending"]

	if sap_settings.allow_retry:
		status_filter.extend(["Failed", "Error"])

	if request.request_status not in status_filter:
		return

	request.send()
