import frappe


def publish_sap_success_notification(doc, method):
	# show alert when item get sync to sap
	if doc.request_status == "Success" and doc.linked_doctype == "Item":

		frappe.publish_realtime(
			event="sap_request_success",
			message={
				"title": "Item Sync to SAP",
				"message": f"Linked DocType: {doc.linked_doctype}, DocName: {doc.linked_docname}",
			},
			user=doc.owner,  # Sends the event to creator None if all
		)

	if doc.request_status == "Success" and doc.linked_doctype == "Specs Sheet":

		frappe.publish_realtime(
			event="sap_request_success",
			message={
				"title": "BOM Sync to SAP",
				"message": f"Linked DocType: {doc.linked_doctype}, DocName: {doc.linked_docname}",
			},
			user=doc.owner,  # Sends the event to creator None if all
		)

	if doc.linked_doctype == "SAP PO Patch":
		doc_link = (
			f'<a href="/app/sap-po-patch/{doc.linked_docname}">{doc.linked_docname}</a>'
		)
		detail = (
			f"{doc.request_description} | {doc_link}" if doc.request_description else doc_link
		)

		if doc.request_status == "Success":
			frappe.publish_realtime(
				event="sap_request_success",
				message={"title": "PO Patch Synced to SAP", "message": detail},
				user=doc.owner,
			)
		elif doc.request_status in ["Failed", "Error"]:
			frappe.publish_realtime(
				event="sap_request_failed",
				message={"title": "PO Patch Failed", "message": detail},
				user=doc.owner,
			)
