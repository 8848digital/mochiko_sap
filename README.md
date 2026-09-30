## Mochiko SAP

The core SAP integration engine from mochiko (`mochiko/sap_integration`), copied as-is into its own app.
Business syncs (Item, SO, PO, BOM, DN, Production Order, MRP, MES Bin, Jobwork…) are **not** included.

Install:

    bench get-app <repo-url>
    bench --site <site> install-app mochiko_sap

Do not install on a site that has mochiko: the doctypes are the same.

### Workflow

1. Code calls `create_log(url, doctype, docname, request_type, payload, is_primary, description, callback_function)`
   from `mochiko_sap.sap_integration.API.create_request_log`.
2. A **SAP Request Log** is saved with status **Pending** and committed, then a background job (`send_request`) is queued right away.
3. `send()` calls SAP (GET / POST / PATCH) with the `B1SESSION` cookie of the primary DB (`is_primary=1`) or the secondary DB.
4. Result:
   - **2xx → Success**: the response is added to the Response Log table, `callback_function` runs, the linked doc's
     sync flag is set, and a realtime "synced" alert is shown (`publish_sap_success_notification`).
   - **401 → session expired**: log in again to SAP (`generate_session`) and resend once.
   - **Other HTTP status → Failed**: the response is saved.
   - **Exception (timeout, connection…) → Error**: the traceback is saved, `retry_count` goes up, and an error email is sent
     to the SAP Error Email recipients (at most one email per 30 minutes).
5. **Scheduler** (`all`, every tick): `SAP Integration.execute` picks up logs that are
   **Pending**, plus **Error** logs if *Allow Retry* is on and `retry_count < Max Retry`.
   It only takes logs created within *Max Time in Minutes* and for the *Applicable DocTypes*, at most *Batch Size* per run,
   and sends each one again in the background.
   Failed (non-2xx) logs are not retried automatically. Use the **Send** button on the log.
6. Logs older than 10 days are deleted (Log Settings).

### Doctypes

| Doctype | Purpose |
|---|---|
| SAP Integration | Settings: base URLs + API URLs, login for 2 company DBs, timeouts, retry rules, batch size |
| Key Value Pair | Login parameters (CompanyDB, UserName, Password) per DB |
| SAP Integration DocType | Which doctypes the retry job handles |
| SAP Request Log | One record per SAP call: request, status, retry count, linked document |
| SAP Response Log | Every attempt's response, inside the request log |
| SAP Error Email / SAP Error Email User | Error email on/off and recipients |

### Known leftovers from mochiko (kept as-is)

- `sap_request_log.py` still has branches for mochiko doctypes (Specs Sheet, MES Bin, Production Assembly, Upper/Sole Receiving,
  Daily SFG Entry, POSC, Transfer Warehouse) and the related `*_sync.py` files. They only run when a log is linked to those doctypes.
- The MES Bin branch enqueues `mochiko_sap.sap_integration.API.create_mes_bin.create_mes_bin_from_sap`, which is not in this app.
- The Specs Sheet FG update (`trigger_specs_sheet_update_if_both_synced`) was removed, because it belongs to mochiko's MES Operations.
- SAP Integration still has the 46 mochiko API URL fields.
