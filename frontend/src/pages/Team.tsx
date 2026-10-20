import { useCallback, useEffect, useState, type FormEvent } from "react";
import * as api from "../api";
import { ApiError } from "../api";
import { useAuth } from "../auth";
import { ErrorNotice, Loading } from "../components/ui";
import { formatDate } from "../format";
import type { OrganizationDetail, Role } from "../types";
import { ROLES, canManageMembers } from "../types";

export default function Team() {
  const { organization, user } = useAuth();
  const [detail, setDetail] = useState<OrganizationDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("MEMBER");
  const orgId = organization?.id ?? null;

  const load = useCallback(async () => {
    if (!orgId) return;
    try {
      setDetail(await api.getOrganization(orgId));
      setError(null);
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Could not load the team.",
      );
    }
  }, [orgId]);

  useEffect(() => {
    let cancelled = false;
    if (orgId) {
      api
        .getOrganization(orgId)
        .then((d) => !cancelled && setDetail(d))
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

  async function run(action: () => Promise<unknown>) {
    setError(null);
    try {
      await action();
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "That did not work.");
    }
  }

  async function add(e: FormEvent) {
    e.preventDefault();
    if (!orgId) return;
    await run(() => api.addMember(orgId, email.trim(), role));
    setEmail("");
  }

  const manage = organization ? canManageMembers(organization.role) : false;

  return (
    <div className="stack">
      <header className="page-head">
        <h1>Team</h1>
        <p>
          {organization
            ? `Members of ${organization.name}. Your role: ${organization.role}.`
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
          aria-label="Team members (scrolls sideways on small screens)"
        >
          <table>
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
                  <td style={{ overflowWrap: "anywhere" }}>
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
                  <td>{formatDate(m.joined_at)}</td>
                  <td>
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
      {manage && (
        <form className="card scan-form" onSubmit={add}>
          <h2>Add a member</h2>
          <p className="muted small">
            The person must already have a SecureScope account. Email
            invitations are not implemented yet.
          </p>
          <div className="input-row">
            <input
              className="input"
              type="email"
              placeholder="colleague@example.com"
              aria-label="Member email"
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
              {ROLES.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>
            <button className="btn" type="submit">
              Add
            </button>
          </div>
        </form>
      )}
    </div>
  );
}
