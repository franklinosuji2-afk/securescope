# Inviting people to a workspace

Owners and administrators invite people by email from the **Team** page. This is the way to give a consulting
client read-only access to their results.

## How it works

1. On **Team → Invite by email**, enter the address and a role. The default is **Viewer**, which can read
   scans, findings and reports but cannot start scans or change anything. **Owner** cannot be invited; invite
   first, then change the role.
2. SecureScope emails a single-use link (`/accept-invite?token=...`). It works for **7 days**, only once, and
   only for the invited address. Sending a new invitation to the same address cancels the earlier link.
3. The person opens the link, signs in with Google, GitHub or a password (or creates an account), and presses
   **Accept and join**. If they were signed out, the link is remembered for the trip to the sign-in page.
4. Their account's email must be confirmed and must match the invited address, otherwise the server refuses.
   A mismatch does not use the invitation up.

## Safety properties

- Only a SHA-256 digest of the link token is stored; the token itself exists only in the email.
- An admin can invite only roles below their own; an owner can invite any role except owner.
- Pending invitations can be listed and revoked on the Team page. At most 50 can be pending per workspace and
  20 invitations can be sent per person per hour.
- The preview and accept endpoints are rate limited per client address.
- Events `org.invitation.created`, `org.invitation.accepted` and `org.invitation.revoked` appear in the audit log.
- Used, revoked and expired invitations are deleted a month after they expire. The privacy notice describes
  what is stored.

## What a viewer sees

Viewers are meant for clients. They see the sites, scans, findings and reports of the workspace, and nothing
else. The server returns only their own entry in the member list (`GET /organizations/{id}`), so a client
cannot learn the owner's address or who the other clients are. Members, analysts, administrators and owners
still see the full list. If the invited address has not been confirmed yet, the invitation page offers to send
the confirmation email.

## Checking it on the live site

1. Invite a second address you control (not your main one) as Viewer.
2. Open the email, then the link in a private window. It should show the workspace and role.
3. Sign in or create an account with that address, accept, and confirm the workspace opens read-only: no scan
   form, no Team controls.
4. Back as owner, check the audit log for the three event types and that the pending list is empty.

If the email never arrives, check the mail provider settings (`docs/EMAIL_SETUP.md`) and the logs for
`mail send failed`. The inviter is not told about a delivery failure; send the invitation again.
