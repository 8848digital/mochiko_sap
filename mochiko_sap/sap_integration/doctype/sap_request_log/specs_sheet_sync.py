import frappe


def expected_log_count(specs_sheet, request_type, is_primary):
	expected_descriptions = []

	if specs_sheet.upper_items:
		expected_descriptions.append("Upper Item BOM")
	if specs_sheet.stockfitting_items:
		expected_descriptions.append("Stockfitting Item BOM")
	if specs_sheet.assembly_items:
		expected_descriptions.append("Final BOM")

	return expected_descriptions


def check_specs_sheet_sync(specs_sheet_name, request_type, is_primary):
	specs_sheet = frappe.get_doc("Specs Sheet", specs_sheet_name)
	expected_descriptions = expected_log_count(
		specs_sheet, request_type, is_primary
	)  # returns a list like ["Final BOM", "Stockfitting Item BOM", "Upper Item BOM"]

	success_count = 0

	for description in expected_descriptions:
		success_exists = frappe.db.exists(
			"SAP Request Log",
			{
				"linked_doctype": "Specs Sheet",
				"linked_docname": specs_sheet_name,
				"request_type": request_type,
				"is_primary": is_primary,
				"request_status": "Success",
				"request_description": description,
			},
		)
		if success_exists:
			success_count += 1

	if success_count == len(expected_descriptions):
		field = "custom_is_synced_to_sap" if is_primary else "custom_is_synced_to_sap_2"
		frappe.db.set_value(
			"Specs Sheet",
			specs_sheet_name,
			{
				field: 1,
				"custom_last_synced_to_sap": frappe.utils.now(),
			},
		)
		action = "Created" if request_type == "POST" else "Updated"
		doc = frappe.get_doc("Specs Sheet", specs_sheet_name)
		doc.add_comment("Info", f"BOM {action} in SAP successfully by {frappe.session.user}")
	else:
		failed_count = frappe.db.count(
			"SAP Request Log",
			{
				"linked_doctype": "Specs Sheet",
				"linked_docname": specs_sheet_name,
				"request_type": request_type,
				"is_primary": is_primary,
				"request_status": "Failed",
				"request_description": ["in", expected_descriptions],
			},
		)
		if success_count + failed_count == len(expected_descriptions):
			action = "Created" if request_type == "POST" else "Updated"
			doc = frappe.get_doc("Specs Sheet", specs_sheet_name)
			doc.add_comment("Info", f"BOM {action} in SAP failed by {frappe.session.user}")
