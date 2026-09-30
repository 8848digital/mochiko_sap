import frappe
import json

def sync_production_assembly_with_sap(response, docname, reference_doctype):
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

    doc_entry = data.get("DocEntry")
    doc_num = data.get("DocNum")

    if not doc_entry or not doc_num:
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
                "is_synced_to_sap": 1,
                "sap_docentry": doc_entry,
                "sap_docnum": doc_num
            }
        )
        frappe.db.commit()
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