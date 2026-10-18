import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import * as api from "./api";
import type { Organization, User } from "./types";

interface AuthValue {
  user: User | null;
  loading: boolean;
  organization: Organization | null;
  setOrganizationId: (id: string) => void;
  signIn: (email: string, password: string) => Promise<void>;
  signUp: (
    email: string,
    password: string,
    organizationName?: string,
  ) => Promise<void>;
  signOut: () => Promise<void>;
  reload: () => Promise<void>;
}

const AuthContext = createContext<AuthValue | null>(null);
const ORG_KEY = "securescope.org";

function storedOrg(): string | null {
  try {
    return window.sessionStorage.getItem(ORG_KEY);
  } catch {
    return null;
  }
}
function storeOrg(id: string | null): void {
  try {
    if (id) window.sessionStorage.setItem(ORG_KEY, id);
    else window.sessionStorage.removeItem(ORG_KEY);
  } catch {
    /* per-tab convenience only */
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [orgId, setOrgId] = useState<string | null>(storedOrg);

  const organization = useMemo(() => {
    if (!user || user.organizations.length === 0) return null;
    return (
      user.organizations.find((o) => o.id === orgId) ??
      user.organizations[0] ??
      null
    );
  }, [user, orgId]);

  useEffect(() => {
    api.setActiveOrganization(organization?.id ?? null);
  }, [organization]);

  const clear = useCallback(() => {
    setUser(null);
    setOrgId(null);
    storeOrg(null);
    api.setActiveOrganization(null);
  }, []);

  useEffect(() => {
    api.setUnauthorizedHandler(clear);
    return () => api.setUnauthorizedHandler(null);
  }, [clear]);

  const reload = useCallback(async () => {
    try {
      setUser(await api.fetchMe());
    } catch {
      setUser(null);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    api
      .fetchMe()
      .then((me) => !cancelled && setUser(me))
      .catch(() => !cancelled && setUser(null))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, []);

  const value = useMemo<AuthValue>(
    () => ({
      user,
      loading,
      organization,
      setOrganizationId: (id) => {
        setOrgId(id);
        storeOrg(id);
      },
      signIn: async (email, password) =>
        setUser(await api.login(email, password)),
      signUp: async (email, password, organizationName) =>
        setUser(await api.register(email, password, organizationName)),
      signOut: async () => {
        try {
          await api.logout();
        } finally {
          clear();
        }
      },
      reload,
    }),
    [user, loading, organization, clear, reload],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
