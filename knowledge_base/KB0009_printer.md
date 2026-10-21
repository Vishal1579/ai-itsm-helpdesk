---
id: KB0009
title: Printer and Print Queue Problems
category: Hardware
subcategory: Printer
tags: printer, print, spooler, print queue, stuck, follow-me printing
owner: Desktop Support
---
# Printer and Print Queue Problems

Offices use Follow-Me printing: send a job to `FollowMe-Print` and release it at any printer with your badge.

## Symptoms
- Print jobs are stuck in the queue or show "Error - Printing".
- The printer does not appear in the list.
- The badge is not recognised at the printer.

## Fixing a stuck print queue
1. Open Settings > Printers & scanners > FollowMe-Print > Open print queue and cancel all documents.
2. Restart the Print Spooler service: run `services.msc`, find "Print Spooler", and choose Restart. The AI helpdesk agent can restart the Print Spooler service remotely.
3. Send the document again.

## Printer missing
Add the printer again from the Company Portal: search for "FollowMe Print" and choose Install.

## When to escalate
Raise an incident for Desktop Support with the printer location if the printer hardware shows an error, a paper jam cannot be cleared, or toner is empty.
