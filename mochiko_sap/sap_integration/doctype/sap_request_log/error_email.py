import frappe
import html
from frappe.utils import now_datetime, get_datetime
from datetime import timedelta


def send_sap_error_email(self):
	sap_email = frappe.get_single("SAP Error Email")

	# Check if feature enabled
	if not sap_email.enabled:
		return

	current_time = now_datetime()

	# Check 30 minute condition (convert string to datetime)
	if last_sent := sap_email.last_sent:
		time_diff = current_time - get_datetime(last_sent)
		if time_diff < timedelta(minutes=30):
			return  # Skip sending

	# Extract error safely
	error_text = (
		self.response_logs[-1].response_data if self.response_logs else "No logs available"
	)

	formatted_error = _extract_clean_exception(error_text)

	recipients = [row.email for row in sap_email.email if row.email]

	if not recipients:
		frappe.log_error(
			title="SAP Error Email: No Recipients",
			message=f"No recipients configured in SAP Error Email for document: {sap_email.name}"
		)
		return

	# Send email
	frappe.sendmail(
		recipients=recipients,
		subject="SAP API Request Failed",
		message=(f"SAP Request Log: {self.name}\n" f"Error Details: {formatted_error}\n"),
	)

	# Update last_sent
	sap_email.last_sent = current_time
	sap_email.save(ignore_permissions=True)


def _extract_clean_exception(error_text):
	if not error_text:
		return "No logs available"

	try:
		# Decode HTML entities
		error_text = html.unescape(error_text)

		# Convert escaped \n into real newlines
		error_text = error_text.encode().decode("unicode_escape")

		# Get last non-empty line
		lines = [l.strip() for l in error_text.split("\n") if l.strip()]

		if lines:
			return lines[-1]

		return error_text

	except Exception:
		# Fallback – never break email sending
		return str(error_text)
