---
id: KB0002
title: Password Reset and Expired Passwords
category: Access
subcategory: Password
tags: password, expired, reset, self-service, sspr, active directory
owner: Identity & Access Management
---
# Password Reset and Expired Passwords

Corporate network passwords (Active Directory / Entra ID) expire every 90 days. Expired passwords block sign-in to Windows, VPN, Outlook and most business applications.

## Symptoms
- "Your password has expired and must be changed" at sign-in.
- VPN or Outlook keeps asking for the password.
- Sign-in fails right after the expiry reminder emails.

## Self-service password reset (SSPR)
1. Go to the self-service password portal or ask the IT Helpdesk chatbot to reset your password.
2. Verify your identity with MFA (authenticator push or SMS code to your registered mobile).
3. A temporary password is issued and sent to your registered mobile number. You must change it at next sign-in.
4. Choose a new password: at least 14 characters, including upper case, lower case, a number and a symbol. The last 10 passwords cannot be reused.
5. Sign out of every device and sign in again with the new password, including phone email apps, so they do not lock your account with the old password.

## Automated reset by the helpdesk agent
The AI helpdesk agent can reset an expired password automatically when the identity check (MFA) succeeds and the account is not a privileged or administrator account. Privileged accounts must be reset by the Identity & Access Management team.

## After resetting
- Update the saved password in VPN, Outlook and Wi-Fi profiles.
- Allow up to 5 minutes for the new password to sync to all systems.

## When to escalate
Escalate to Identity & Access Management if MFA verification fails, if you no longer have access to your registered mobile, or if the account is privileged.
