import frappe
import json


def create_log(
	url,
	doctype,
	docname,
	request_type,
	request_payload,
	is_primary,
	request_description=None,
	callback_function=None,
):
	data = {
		"url": url,
		"request_type": request_type,
		"request_payload": json.dumps(request_payload, indent=4),
		"linked_doctype": doctype,
		"linked_docname": docname,
		"request_description": request_description,
		"callback_function": callback_function,
		"is_primary": is_primary,
	}
	log = frappe.new_doc("SAP Request Log")
	log.update(data)
	log.save(ignore_permissions=True)
	# frappe.db.commit needed cz somtimes enqueue does not find record
	# Commit to ensure the log is saved before enqueue
	frappe.db.commit()  # Commit to ensure log is saved before sending // nosemgrep

	# enqueue immediately
	frappe.enqueue(
		"mochiko_sap.sap_integration.API.create_request_log.send_request",
		request_log_name=log.name,
		job_id=f"sap_request_{log.name}",  # Unique job ID
		deduplicate=True,  # Ensures the same job is not queued twice
	)
	# return log name
	# return log.name


def send_request(request_log_name):
	"""Fetch SAP Request Log and send request"""
	request_log = frappe.get_doc("SAP Request Log", request_log_name)
	request_log.send()
