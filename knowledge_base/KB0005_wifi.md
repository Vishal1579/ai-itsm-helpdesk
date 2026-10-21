---
id: KB0005
title: Wi-Fi Connectivity Issues
category: Network
subcategory: Wi-Fi
tags: wifi, wi-fi, wireless, corp-secure, network, connectivity
owner: Network Support
---
# Wi-Fi Connectivity Issues

Office Wi-Fi uses the `CORP-SECURE` network (certificate-based 802.1X) for corporate laptops and `CORP-GUEST` for visitors and personal devices.

## Symptoms
- Cannot see or join `CORP-SECURE`.
- Connected to Wi-Fi with "No internet" or very slow speeds.
- Frequent disconnections when moving between floors.

## Troubleshooting steps
1. Turn Wi-Fi off and on again, or switch on Airplane mode for 10 seconds and then off.
2. Forget the `CORP-SECURE` network and reconnect; the device certificate is selected automatically.
3. Confirm your laptop date and time are correct; certificate authentication fails when the clock is wrong.
4. Run the network troubleshooter (Windows: Settings > Network > Network troubleshooter).
5. Update the wireless driver through the Company Portal.
6. Move closer to an access point. Meeting rooms with glass walls often have weaker signal.

## Home Wi-Fi
For home networks, restart the router and use the 5 GHz band when available. Corporate applications require the VPN when working from home (see KB0001).

## When to escalate
Escalate to Network Support with your floor, building and the time of the problem if several users nearby are affected, or if `CORP-SECURE` rejects the device certificate.
