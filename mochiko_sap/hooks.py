app_name = "mochiko_sap"
app_title = "Mochiko SAP"
app_publisher = "8848 Digital LLP"
app_description = "SAP integration core engine, copied as-is from mochiko"
app_email = "deepakkumar@8848digital.com"
app_license = "mit"

# Hook on document methods and events

doc_events = {
	"SAP Request Log": {
		"on_update": "mochiko_sap.sap_integration.utils.utils.publish_sap_success_notification"
	},
}

# Scheduled Tasks

scheduler_events = {
	"all": [
		"mochiko_sap.sap_integration.doctype.sap_integration.sap_integration.execute",
	],
}

# log doctype cleanups to automatically add in log settings
default_log_clearing_doctypes = {
	"SAP Request Log": 10,
}
