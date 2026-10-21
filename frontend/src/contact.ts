/** The public contact addresses. Change them here and nowhere else; the legal pages read from this file. */
export const CONTACT = {
  general: "hello@getsecurescope.com",
  support: "support@getsecurescope.com",
  privacy: "privacy@getsecurescope.com",
  security: "security@getsecurescope.com",
} as const;

export type ContactKind = keyof typeof CONTACT;

export const mailto = (kind: ContactKind): string => `mailto:${CONTACT[kind]}`;
