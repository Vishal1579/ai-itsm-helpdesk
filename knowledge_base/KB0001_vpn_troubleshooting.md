---
id: KB0001
title: VPN Troubleshooting Guide
category: Network
subcategory: VPN
tags: vpn, globalprotect, remote access, authentication, mfa
owner: Network Support
---
# VPN Troubleshooting Guide

The corporate VPN (GlobalProtect client, portal `vpn.corp.example.com`) gives remote access to internal applications. This article covers the most common connection and authentication failures.

## Symptoms
- "Authentication failed" or "Invalid credentials" when connecting.
- The client is stuck on "Connecting..." or keeps disconnecting.
- Connected, but internal sites and file shares do not load.

## Authentication failures
Most VPN authentication failures come from an expired or recently changed password, an out-of-sync MFA token, or an expired device certificate.
1. Confirm your network password still works by signing in to the employee portal. If it has expired, reset it first (see KB0002 Password Reset).
2. Open the authenticator app and check that the device clock is set to automatic time; MFA codes fail when the clock is out of sync.
3. In the GlobalProtect client choose Settings > Refresh Connection, then sign in again with your username in the format `firstname.lastname`.
4. If the error says "certificate not found", the device certificate has expired. Raise an incident with Network Support so a new certificate can be pushed.
5. After three failed attempts your account can be locked for 15 minutes (see KB0003 Account Lockout).

## Connection drops or stuck on connecting
1. Check that your internet connection works by opening a public website.
2. Switch the portal gateway to the nearest region in the client settings.
3. Disconnect, quit the GlobalProtect client fully, and start it again.
4. Disable other VPN or proxy software, which conflicts with the corporate client.
5. Restart the laptop to clear stale network adapters.

## Connected but no internal access
- Flush DNS: on Windows run `ipconfig /flushdns`; on macOS run `sudo dscacheutil -flushcache`.
- Confirm the client shows "Connected - Full tunnel".

## When to escalate
Escalate to Network Support (assignment group: Network Support) if authentication still fails after a password reset and MFA re-sync, if several users report the same problem (possible gateway outage), or if the device certificate has expired.
