---
id: KB0003
title: Account Lockout Resolution
category: Access
subcategory: Account Lockout
tags: locked out, account locked, unlock, failed sign-in
owner: Identity & Access Management
---
# Account Lockout Resolution

Accounts are locked automatically after 5 failed sign-in attempts within 15 minutes. The lock is released automatically after 30 minutes, or straight away through a verified unlock.

## Common causes
- Typing an old password after a recent password change.
- A phone, tablet or mapped drive still using an old saved password.
- Repeated VPN sign-in attempts with an expired password.

## How to unlock
1. Ask the IT Helpdesk chatbot to unlock your account, or use the self-service portal.
2. Complete MFA verification.
3. The account is unlocked immediately. Sign in again within a few minutes.

## Preventing repeat lockouts
- Remove or update old saved passwords on mobile devices and in Windows Credential Manager.
- Disconnect mapped drives that use stored credentials, then reconnect them.

## When to escalate
If the account locks again within an hour of unlocking, a device is still using old credentials. Raise an incident for Identity & Access Management to trace the lockout source.
