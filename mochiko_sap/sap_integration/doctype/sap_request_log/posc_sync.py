import frappe
import json

def sync_posc_with_sap(response, docname, reference_doctype):
    try:
        data = response.json()
    except Exception:
        frappe.log_error(
            title="SAP Sync Error - Invalid JSON",
            message=(
                f"Reference Doctype: {reference_doctype}\n"
                f"Doc: {docname}\n"
                f"Response Text:\n{response.text}"
            )
        )
        return

    doc_entry = data.get("DocumentNumber")
    doc_num = data.get("DocumentNumber")
    absolute_entry = data.get("AbsoluteEntry")

    if not doc_entry:
        frappe.log_error(
            title="SAP Sync Error - Missing Fields",
            message=(
                f"Reference Doctype: {reference_doctype}\n"
                f"Doc: {docname}\n"
                f"Response:\n{data}"
            )
        )
        return

    try:
        frappe.db.set_value(
            reference_doctype,
            docname,
            {
                "posc_sync": 1,
                "sap_docentry": absolute_entry,
                "sap_docnum": doc_num
            }
        )
        frappe.db.commit()
        doc = frappe.get_doc(reference_doctype, docname)
        doc.add_comment(
            comment_type="Info",
            text=(
                f"Successfully synced with SAP.<br>"
                f"<b>SAP DocEntry:</b> {absolute_entry}<br>"
                f"<b>SAP Document Number:</b> {doc_num}"
            )
        )
    except Exception:
        frappe.log_error(
            title="SAP Sync DB Update Failed",
            message=(
                f"Reference Doctype: {reference_doctype}\n"
                f"Doc: {docname}\n"
                f"DocEntry: {doc_entry}\n"
                f"DocNum: {doc_num}"
            )
        )