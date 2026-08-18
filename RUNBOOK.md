# QMS SAP PR Integration — Final Setup & Runbook

**Server:** 192.168.66.34 (app) / 192.168.66.33 (SQL Server)
**Repo:** https://github.com/aviverma007/QMS_SAP_PR
**Last updated:** 2026-08-18

---

## 1. What This System Does

Two SAP reports are continuously pulled from `smartworlddevelopersonline.com`,
written into SQL Server as timestamped history, and exposed via HTTP
endpoints so SAP (via SM59/RFC destinations) can query PR status directly.

| Report | Source | SQL Table | PR field format |
|---|---|---|---|
| PR Report | `SapPrReport.php` | `PRReportHistory` | `8110xxxxxxx` (`PR_No`) |
| PR/NFA TAT Report | `SapPrNFATatReport.php` | `PRNFATatReportHistory` | `0000xxxxxx` (`EPR_No`) |

**These two reports track different scopes of data.** Not every PR in
the first report will have a matching entry in the second — only PRs
that went through NFA approval appear there. This is expected, not a bug.

---

## 2. Current Live Endpoints (port 5002)

```
http://192.168.66.34:5002/check_pr?pr=<PR_NUMBER>
http://192.168.66.34:5002/odata/PRReportHistory?$top=100&$skip=0

http://192.168.66.34:5002/nfatat/check_pr?pr=<EPR_NUMBER>
http://192.168.66.34:5002/nfatat/search?pr=<EPR_NUMBER>&startdate=<YYYY-MM-DD>&enddate=<YYYY-MM-DD>
http://192.168.66.34:5002/nfatat/odata/PRNFATatReportHistory?$top=100&$skip=0
```

`/nfatat/search` parameters are all optional and independent — PR only,
dates only, or both together all work in the same URL.

**Direct SQL access (read-only):**
- Server: `192.168.66.33`, Port `1433`, DB `QMS_PR_Report`
- Login: `qms_pr_reader` (password set separately, not stored in repo)

---

## 3. Server 34 Setup (what's actually running)

- **App runs as a Windows service** named `QMSPRApp` (via NSSM), not a manual
  terminal process. Auto-restarts on crash, survives reboot/logoff.
  - Install location: `D:\smartdesk_live\QMS_SAP_PR\app`
  - Python: `D:\smartdesk_live\python312\python.exe` (embeddable distro)
  - NSSM: `D:\smartdesk_live\nssm\nssm-2.24\win64\nssm.exe`
  - Logs (once configured): `service_stdout.log`, `service_stderr.log` in the app folder
- **Firewall rule:** `QMS PR Report App`, inbound TCP 5002, all profiles.
  *(Note: duplicate copies of this rule exist from testing other ports —
  harmless but worth cleaning up with `Get-NetFirewallRule -DisplayName
  "QMS PR Report App"` and removing extras.)*
- **Routing:** persistent default route added (`route -p add 0.0.0.0 mask
  0.0.0.0 192.168.66.1 metric 1`) to resolve a dual-gateway conflict that
  was causing intermittent outbound traffic to go out the wrong interface.
- **Port 8000 is NOT usable on this server** — permanently occupied by
  `MediaServer.exe` (eSSL BioCVSecurity, likely tied to biometric
  attendance hardware). Do not attempt to reclaim this port without
  looping in whoever manages the attendance system.

---

## 4. SQL Server Setup (192.168.66.33)

Run once, in order, via SSMS:
1. `sql/create_database.sql` — creates `QMS_PR_Report` DB + `PRReportHistory` table
2. `sql/create_readonly_login.sql` — creates `qms_pr_reader` login (change password first)
3. `sql/widen_nfatat_columns.sql` — one-time fix for a truncation bug (already applied)

Tables auto-create/auto-widen their own columns as new fields appear in
the source JSON — no manual schema maintenance needed going forward.

---

## 5. SAP-Side Status (as of last check)

| Environment | Host | Status |
|---|---|---|
| Development | `vhsmwds4ci.sap.smartworlddevelopers.com` | Working, but **intermittent** — has flipped between success and `NIECONN_REFUSED` multiple times with nothing changed on server 34. Root cause not fully identified — likely a network-path issue outside our control (see Section 7). |
| Quality | `vhsmwqs4ci.sap.smartworlddevelopers.com` | Blocked by Squid proxy (`vhsmwsingwc.sin.sap.smartworlddevelopers.com`), 403 Forbidden / `ERR_ACCESS_DENIED`. Escalation email sent, awaiting infra fix (whitelist or proxy bypass for `192.168.66.0/24`). |
| Production | `vhsmwps4ci.sap.smartworlddevelopers.com` | Never actually tested in this process — status unknown. |

SM59 destination used for testing: `ZPR_CHECK_TEST`
- Host: `192.168.66.34` (no `http://` prefix, no trailing slash — this
  broke the test once when someone accidentally added it)
- Port: `5002`
- Path Prefix: `/check_pr?pr=<test_value>` for connection tests. **For
  real production use, the PR number must be supplied dynamically by
  the ABAP program at runtime, not hardcoded in the destination.**

---

## 6. Troubleshooting Runbook

If SAP reports `NIECONN_REFUSED` or similar, check server 34 in this order:

```powershell
# 1. Is the service running and clean (no duplicate/conflicting process)?
Get-Service QMSPRApp
netstat -ano | findstr :5002

# 2. Is the firewall rule present?
Get-NetFirewallRule -DisplayName "QMS PR Report App" | Select DisplayName, Enabled, Direction, Action, Profile

# 3. Does it work locally?
curl "http://localhost:5002/check_pr?pr=8110000192" -UseBasicParsing

# 4. Is routing correct (single default gateway, not two)?
route print -4
```

**If all four come back clean** (as they have every single time we've
checked in this project so far), the problem is NOT on server 34 — it's
on the network path or the SAP/proxy side. Do not keep re-troubleshooting
server 34 in that case; escalate to infra/Basis with the specific SAP
environment and error shown.

**If the firewall rule is missing:**
```powershell
netsh advfirewall firewall add rule name="QMS PR Report App" dir=in action=allow protocol=TCP localport=5002
```

**If the route shows two default gateways:**
```powershell
route change 0.0.0.0 mask 0.0.0.0 192.168.66.1 metric 1
route -p add 0.0.0.0 mask 0.0.0.0 192.168.66.1 metric 1
```

**To update the code after a change is pushed to GitHub:**
```powershell
Stop-Service QMSPRApp
cd D:\smartdesk_live\QMS_SAP_PR
git pull
Start-Service QMSPRApp
```

---

## 7. Open / Unresolved Items

1. **Quality's Squid proxy block** — escalation sent, awaiting infra action.
2. **Development's intermittent failures** — worked, failed, worked again,
   with nothing changed on server 34 each time. Suspected causes (unconfirmed):
   - Dev's SAP hostname may resolve to multiple physical servers (cluster/load
     balancer), with the firewall path only open on some of them
   - A stateful firewall/security appliance somewhere in between with
     inconsistent behavior
   - Ask infra directly: *"Is vhsmwds4ci a single server or a cluster? If
     multiple servers, is the firewall rule applied to all of them?"*
3. **Production** — never tested. Should be verified before considering
   this fully rolled out.
4. **Duplicate firewall rules** on server 34 (harmless, but worth cleaning
   up for clarity):
   ```powershell
   Get-NetFirewallRule -DisplayName "QMS PR Report App"
   ```
   Remove extras via `Remove-NetFirewallRule` if multiple show up.
5. **Service crash logging not yet fully confirmed active** — the
   `AppStdout`/`AppStderr` NSSM settings were added partway through this
   session. Confirm they're capturing output by checking:
   ```powershell
   Get-Content "D:\smartdesk_live\QMS_SAP_PR\app\service_stderr.log" -Tail 20
   ```

---

## 8. What NOT To Do

- **Don't change the port again.** 5002 is confirmed stable and working
  on server 34's side. Port 8000 is permanently blocked by attendance
  software. Port-hopping doesn't fix the Quality/Dev issues, which are
  network/proxy problems, not port problems.
- **Don't edit the SM59 Host field to include `http://` or a trailing
  slash.** Just the bare IP: `192.168.66.34`.
- **Don't hardcode a specific PR number into the RFC destination's Path
  Prefix for production use** — that was only ever meant for connection
  testing.
