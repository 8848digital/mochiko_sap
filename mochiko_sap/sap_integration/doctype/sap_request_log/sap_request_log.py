# Copyright (c) 2024, 8848 Digital LLP and contributors
# For license information, please see license.txt

import frappe
from .production_assembly_sync import sync_production_assembly_with_sap
from .upper_receiving_sync import sync_upper_receiving_with_sap
from .sole_receiving_sync import sync_sole_receiving_with_sap
from .daily_sfg_entry_sync import sync_daily_sfg_with_sap
from .posc_sync import sync_posc_with_sap
from .transfer_warehouse_sync import sync_tw_with_sap
import requests
import json
from frappe.model.document import Document
from frappe.query_builder import DocType, Interval
from frappe.query_builder.functions import Now
from .error_email import send_sap_error_email


class SAPRequestLog(Document):
	@staticmethod
	def clear_old_logs(days=None):
		days = days or 30
		table = DocType("SAP Request Log")
		frappe.db.delete(table, filters=(table.modified < (Now() - Interval(days=days))))

	def before_save(self):
		if not self.max_retry:
			self.max_retry = frappe.get_single("SAP Integration").max_retry

	def on_update(self):
		if self.request_status in ["Error"]:
			# send email
			send_sap_error_email(self)

	@frappe.whitelist()
	def send(self):
		try:
			headers = self.get_headers()
			cookies = self.get_cookies() if self.is_primary else self.get_secondary_cookies()
			payload = self.get_payload()
			timeout = frappe.get_single("SAP Integration").get_timeout()

			# if retry, increase retry count
			if self.request_status in ["Failed", "Error"]:
				self.retry_count += 1

			if self.request_type == "GET":
				response = requests.get(
					self.url, params=payload, headers=headers, cookies=cookies, timeout=timeout
				)
			elif self.request_type == "POST":
				response = requests.post(
					self.url, json=payload, headers=headers, cookies=cookies, timeout=timeout
				)
			elif self.request_type == "PATCH":
				response = requests.patch(
					self.url, json=payload, headers=headers, cookies=cookies, timeout=timeout
				)
			self.handle_response(response)

		except Exception as e:
			frappe.log_error(
				message=repr(e),
				title="SAP API Error",
				reference_doctype=self.linked_doctype,
				reference_name=self.linked_docname,
			)
			if self.request_status == "Pending":
				self.retry_count += 1
			self.request_status = "Error"
			self.log_response("Error", frappe.get_traceback())
			self.save(ignore_permissions=True)
		finally:
			frappe.db.commit()  # Ensure transaction is saved // nosemgrep

	def get_headers(self):
		return (
			{"Content-Type": "application/json"}
			if not self.headers
			else json.loads(self.headers)
		)

	def get_cookies(self):
		session_id = frappe.cache.get_value("sap_session_id")
		if not session_id:
			session_id = frappe.get_single("SAP Integration").session_id
		return {"B1SESSION": session_id}

	def get_secondary_cookies(self):
		session_id = frappe.cache.get_value("sap_session_id_2")
		if not session_id:
			session_id = frappe.get_single("SAP Integration").session_id_2
		return {"B1SESSION": session_id}

	def get_payload(self):
		return json.loads(self.request_payload) if self.request_payload else {}

	def handle_response(self, response):
		response_text = (
			f"Status Code: {response.status_code}\n"
			f"Response Headers: {response.headers}\n"
			f"Response Body: {response.text}"
		)
		if response.status_code in [200, 201, 204]:
			self.request_status = "Success"
			self.log_response("Success", response_text)
			self.enqueue_callback_function(response)

			# Check if all logs for this Specs Sheet and primary_flag are marked Success
			if self.linked_doctype == "Specs Sheet":
				frappe.enqueue(
					"mochiko_sap.sap_integration.doctype.sap_request_log.specs_sheet_sync.check_specs_sheet_sync",
					specs_sheet_name=self.linked_docname,
					request_type=self.request_type,
					is_primary=self.is_primary,
					now=False,
					enqueue_after_commit=True,
				)
			elif self.linked_doctype == "MES Bin":
				frappe.enqueue(
					"mochiko_sap.sap_integration.API.create_mes_bin.create_mes_bin_from_sap",
					request=self,
					response=response,
				)
			elif self.linked_doctype == "Production Assembly":
				sync_production_assembly_with_sap(
					response, self.linked_docname, self.linked_doctype
				)
			elif self.linked_doctype == "Upper Receiving":
				sync_upper_receiving_with_sap(response, self.linked_docname, self.linked_doctype)
			elif self.linked_doctype == "Sole Receiving":
				sync_sole_receiving_with_sap(response, self.linked_docname, self.linked_doctype)
			elif self.linked_doctype == "Daily SFG Entry":
				sync_daily_sfg_with_sap(response, self.linked_docname, self.linked_doctype)
			elif self.linked_doctype == "Production Order for Sole and Compound":
				sync_posc_with_sap(response, self.linked_docname, self.linked_doctype)
			elif self.linked_doctype == "Transfer Warehouse":
				sync_tw_with_sap(response, self.linked_docname, self.linked_doctype)
			else:
				# Mainly Item doc
				self.update_doc_sync_status(1)
		else:

			self.request_status = "Failed"
			self.log_response("Failed", response_text)

			# Item already present in SAP -> treat as synced in MES
			if (
				self.linked_doctype == "Item" and "already exists" in (response.text or "").lower()
			):
				self.update_doc_sync_status(1)

			if self.linked_doctype == "Specs Sheet":
				frappe.enqueue(
					"mochiko_sap.sap_integration.doctype.sap_request_log.specs_sheet_sync.check_specs_sheet_sync",
					specs_sheet_name=self.linked_docname,
					request_type=self.request_type,
					is_primary=self.is_primary,
					now=False,
					enqueue_after_commit=True,
				)

			# Retry on 401
			if response.status_code == 401:
				auth_response = frappe.get_single("SAP Integration").generate_session(
					is_primary=self.is_primary
				)
				if auth_response.json().get("SessionId"):
					if not self.flags.after_session_id:
						self.flags.after_session_id = 1
						frappe.log_error(
							"SAP session refreshed. Retrying request...", "SAP API SessionID"
						)
						return self.send()
				else:
					self.log_response("Failed", auth_response.text)

		self.save(ignore_permissions=True)

	def log_response(self, status, response_txt):
		self.append(
			"response_logs",
			{
				"response_on": frappe.utils.now_datetime(),
				"response_status": status,
				"response_data": response_txt,
			},
		)

	def update_doc_sync_status(self, is_synced):
		try:
			if self.linked_doctype == "FG Item Name Change":  # FG Item Patch only
				field_to_update = "is_updated_sap" if self.is_primary else "is_updated_sap_2"

				frappe.db.set_value(
					self.linked_doctype,
					self.linked_docname,
					{
						field_to_update: is_synced,
					},
				)
			elif self.linked_doctype in ["Item", "Specs Sheet"]:
				field_to_update = (
					"custom_is_synced_to_sap" if self.is_primary else "custom_is_synced_to_sap_2"
				)

				frappe.db.set_value(
					self.linked_doctype,
					self.linked_docname,
					{
						field_to_update: is_synced,
						"custom_last_synced_to_sap": frappe.utils.now(),
					},
					# update_modified=False,
				)

			frappe.db.commit()  # Ensure transaction is saved // nosemgrep
		except Exception as e:
			frappe.log_error(
				message=repr(e),
				title="SAP API Error Update Item status",
				reference_doctype=self.doctype,
				reference_name=self.name,
			)

	def enqueue_callback_function(self, response):
		try:
			if self.callback_function:
				frappe.get_attr(self.callback_function)(request=self, response=response)
		except Exception as e:
			frappe.log_error(
				message=repr(e) + f"\n{frappe.get_traceback()}",
				title="SAP API Callback Error",
				reference_doctype=self.doctype,
				reference_name=self.name,
			)
