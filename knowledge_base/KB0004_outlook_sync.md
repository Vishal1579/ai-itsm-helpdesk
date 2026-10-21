---
id: KB0004
title: Outlook Synchronization Troubleshooting
category: Email
subcategory: Outlook
tags: outlook, email, sync, synchronization, ost, cache, exchange, mailbox
owner: Messaging Support
---
# Outlook Synchronization Troubleshooting

Use this guide when Outlook does not receive new email, sent items stay in the Outbox, or the calendar and folders are not up to date.

## Symptoms
- The status bar shows "Disconnected", "Working offline" or "Trying to connect".
- New email appears in Outlook on the web but not in the desktop client.
- Folders show "This folder was last updated..." with an old time.

## Step-by-step troubleshooting
1. Check the Send/Receive tab and make sure "Work Offline" is turned off.
2. Confirm the mailbox works in Outlook on the web (outlook.office.com). If it does not, the problem is with the mailbox or network, not the client.
3. Make sure your password has not expired; Outlook stops syncing when it cannot authenticate (see KB0002).
4. Restart Outlook. If it hangs, end the OUTLOOK.EXE process in Task Manager first.
5. Clear the Outlook offline cache: close Outlook, rename the `.ost` file under `%LOCALAPPDATA%\Microsoft\Outlook`, and open Outlook again to rebuild the cache. The AI helpdesk agent can clear the cache automatically.
6. Check the mailbox size. Mailboxes over 95% of quota stop sending; archive or delete old items.
7. Repair the profile: Control Panel > Mail > Email Accounts > Repair.

## Shared mailboxes and calendars
Shared mailboxes sync slowly in cached mode. Turn off "Download shared folders" under Account Settings > Change > More Settings > Advanced.

## When to escalate
Escalate to Messaging Support if Outlook on the web also fails, or the issue continues after the cache is rebuilt and the profile is repaired.
