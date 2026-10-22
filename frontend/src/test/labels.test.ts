import { describe, expect, it } from "vitest";
import { auditLabel } from "../format";
import { ROLES, roleLabel } from "../types";

describe("readable labels", () => {
  it("names every role in words", () => {
    expect(ROLES.map(roleLabel)).toEqual([
      "Owner",
      "Admin",
      "Security analyst",
      "Member",
      "Viewer",
    ]);
  });

  it("names the audit events the server records, without raw event codes", () => {
    for (const type of [
      "scan.scheduled",
      "schedule.updated",
      "report.created",
      "report.downloaded",
      "auth.oauth.login",
      "auth.oauth.linked",
      "share.created",
      "client.created",
    ]) {
      expect(auditLabel(type)).not.toBe(type);
      expect(auditLabel(type)).not.toMatch(/[._]/);
    }
  });
});
