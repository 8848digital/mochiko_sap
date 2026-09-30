// Copyright (c) 2024, 8848 Digital LLP and contributors
// For license information, please see license.txt

frappe.ui.form.on("SAP Request Log", {
	refresh(frm) {
		if (!frm.is_new() && !frm.is_dirty() && frm.doc.request_status != "Success") {
			frm.add_custom_button(__("Send"), function () {
				frm.trigger("send_request");
			});
		}
	},
	send_request(frm) {
		frm.call({
			doc: frm.doc,
			method: "send",
		});
		frappe.show_alert(__("SAP Request has been sent"));
	},
});
