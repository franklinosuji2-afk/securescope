import { useCallback, useEffect, useState, type FormEvent } from "react";
import * as api from "../api";
import { ApiError } from "../api";
import { useAuth } from "../auth";
import { ErrorNotice, Loading } from "../components/ui";
import { formatDate } from "../format";
import type { Invitation, OrganizationDetail, PlanInfo, Role } from "../types";
import { ROLES, canManageMembers } from "../types";

export default function Team() {
  const { organization, user } = useAuth();
  const [detail, setDetail] = useState<OrganizationDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("VIEWER");
  const [invitations, setInvitations] = useState<Invitation[]>([]);
  const [notice, setNotice] = useState<string | null>(null);
  const [plan, setPlan] = useState<PlanInfo | null>(null);
  const orgId = organization?.id ?? null;

  const load = useCallback(async () => {
    if (!orgId) return;
    try {
      const next = await api.getOrganization(orgId);
      setDetail(next);
      setError(null);
      if (canManageMembers(next.role)) {
        const pending = await api.listInvitations(orgId);
        setInvitations(Array.isArray(pending) ? pending : []);
      } else {
        setInvitations([]);
      }
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Could not load the team.",
      );
    }
  }, [orgId]);

  const canManage = organization ? canManageMembers(organization.role) : false;

  useEffect(() => {
    if (!orgId || !canManage) return;
    let live = true;
    api
      .getPlan(orgId)
      .then((next) => {
        if (live) setPlan(next);
      })
      .catch(() => undefined); // the server still enforces the plan if this can't load
    return () => {
      live = false;
    };
  }, [orgId, canManage]);

  useEffect(() => {
    let cancelled = false;
    if (orgId) {
      api
        .getOrganization(orgId)
        .then(async (d) => {
          if (cancelled) return;
          setDetail(d);
          if (canManageMembers(d.role)) {
            const pending = await api.listInvitations(orgId);
            if (!cancelled)
              setInvitations(Array.isArray(pending) ? pending : []);
          }
        })
        .catch(
          (err: unknown) =>
            !cancelled &&
            setError(
              err instanceof ApiError
                ? err.message
                : "Could not load the team.",
            ),
        );
    }
    return () => {
      cancelled = true;
    };
  }, [orgId]);

  async function run(action: () => Promise<unknown>): Promise<boolean> {
    setError(null);
    try {
      await action();
      await load();
      return true;
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "That did not work.");
      return false;
    }
  }

  async function invite(e: FormEvent) {
    e.preventDefault();
    if (!orgId) return;
    const address = email.trim();
    setNotice(null);
    // On a failure `run` shows the reason and the address stays in the field.
    if (await run(() => api.createInvitation(orgId, address, role))) {
      setEmail("");
      setNotice(`Invitation sent to ${address}.`);
    }
  }

  const manage = organization ? canManageMembers(organization.role) : false;

  return (
    <div className="stack">
      <header className="page-head">
        <h1>Team</h1>
        <p>
          {organization
            ? organization.role === "VIEWER"
              ? `Your access to ${organization.name}. Your role: VIEWER. Other members are not shown to viewers.`
              : `Members of ${organization.name}. Your role: ${organization.role}.`
            : "No organization."}{" "}
          Roles are enforced by the server.
        </p>
      </header>
      {error && <ErrorNotice message={error} />}
      {!detail && !error && <Loading label="Loading team…" />}
      {detail && (
        <div
          className="card table-wrap"
          role="region"
          tabIndex={0}
          aria-label="Team members"
        >
          <table className="stack-table">
            <thead>
              <tr>
                <th scope="col">Member</th>
                <th scope="col">Role</th>
                <th scope="col">Joined</th>
                <th scope="col">
                  <span className="visually-hidden">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {detail.members.map((m) => (
                <tr key={m.user_id}>
                  <td className="st-main" style={{ overflowWrap: "anywhere" }}>
                    {m.email}
                    {m.user_id === user?.id && (
                      <span className="muted"> (you)</span>
                    )}
                  </td>
                  <td>
                    {manage ? (
                      <select
                        className="input"
                        style={{ flex: "none", padding: "6px 8px" }}
                        aria-label={`Role for ${m.email}`}
                        value={m.role}
                        onChange={(e) =>
                          void run(() =>
                            api.updateMember(
                              detail.id,
                              m.user_id,
                              e.target.value as Role,
                            ),
                          )
                        }
                      >
                        {ROLES.map((r) => (
                          <option key={r} value={r}>
                            {r}
                          </option>
                        ))}
                      </select>
                    ) : (
                      m.role
                    )}
                  </td>
                  <td className="st-joined">{formatDate(m.joined_at)}</td>
                  <td className="st-action">
                    {(manage || m.user_id === user?.id) && (
                      <button
                        className="btn-ghost"
                        type="button"
                        onClick={() =>
                          void run(() => api.removeMember(detail.id, m.user_id))
                        }
                        aria-label={
                          m.user_id === user?.id
                            ? "Leave organization"
                            : `Remove ${m.email}`
                        }
                      >
                        {m.user_id === user?.id ? "Leave" : "Remove"}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {manage && invitations.length > 0 && (
        <div
          className="card table-wrap"
          role="region"
          tabIndex={0}
          aria-label="Pending invitations (scrolls sideways on small screens)"
        >
          <h2>Pending invitations</h2>
          <table>
            <thead>
              <tr>
                <th scope="col">Email</th>
                <th scope="col">Role</th>
                <th scope="col">Expires</th>
                <th scope="col">
                  <span className="visually-hidden">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {invitations.map((i) => (
                <tr key={i.id}>
                  <td style={{ overflowWrap: "anywhere" }}>{i.email}</td>
                  <td>{i.role}</td>
                  <td>{formatDate(i.expires_at)}</td>
                  <td>
                    <button
                      className="btn-ghost"
                      type="button"
                      aria-label={`Revoke invitation for ${i.email}`}
                      onClick={() =>
                        void run(() => api.revokeInvitation(orgId ?? "", i.id))
                      }
                    >
                      Revoke
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {manage && plan && !plan.limits.can_invite && (
        <section className="card" aria-labelledby="invite-upgrade">
          <h2 id="invite-upgrade">Invite by email</h2>
          <p className="small">
            Inviting teammates and clients is part of the Agency plan. This
            workspace is on the {plan.name} plan.
          </p>
        </section>
      )}
      {manage && !(plan && !plan.limits.can_invite) && (
        <form className="card scan-form" onSubmit={invite}>
          <h2>Invite by email</h2>
          <p className="muted small">
            We email a single-use link that works for 7 days and only for this
            address. The person signs in with Google, GitHub or a password, or
            creates an account, and joins as the role you choose. Use Viewer for
            clients who should only read results.
          </p>
          {notice && (
            <div className="notice notice-info" role="status">
              {notice}
            </div>
          )}
          <div className="input-row">
            <input
              className="input"
              type="email"
              placeholder="client@example.com"
              aria-label="Email to invite"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
            <select
              className="input"
              style={{ flex: "none" }}
              aria-label="Role"
              value={role}
              onChange={(e) => setRole(e.target.value as Role)}
            >
              {ROLES.filter((r) => r !== "OWNER").map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>
            <button className="btn" type="submit">
              Send invitation
            </button>
          </div>
        </form>
      )}
    </div>
  );
}
