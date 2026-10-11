import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";
import { EyeIcon, EyeSlashIcon } from "@phosphor-icons/react";
import { authLogin, authRegister, getOrgs, switchOrg } from "@/api";
import { TEXT_LINK_CLASS } from "@/components/text-link";
import { Alert, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";
import {
  clearInviteToken,
  getInviteToken,
  setCurrentOrgName,
  setSessionToken,
  setUserEmail,
} from "@/session";
import { HOME_ROUTE } from "@/app/routes";

const PASSWORD_REGEX = /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).{8,}$/;

type AuthTab = "login" | "register";
type MsgKind = "err" | "info" | "ok";

type StatusMsg = {
  kind: MsgKind;
  text: string;
};

function serverMessage(data: Record<string, unknown>, fallback: string): string {
  return data.message ? String(data.message) : fallback;
}

function StatusAlert({ id, msg }: { id: string; msg: StatusMsg | null }) {
  if (!msg) return null;
  return (
    <Alert id={id} variant={msg.kind === "err" ? "destructive" : "default"}>
      <AlertTitle>{msg.text}</AlertTitle>
    </Alert>
  );
}

function PasswordField({
  id,
  label,
  value,
  onChange,
  autoComplete,
  placeholder,
  hint,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  autoComplete: string;
  placeholder: string;
  hint?: string;
}) {
  const [visible, setVisible] = useState(false);
  return (
    <div className="flex flex-col gap-2">
      <Label htmlFor={id}>{label}</Label>
      <div className="relative">
        <Input
          id={id}
          type={visible ? "text" : "password"}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          autoComplete={autoComplete}
          placeholder={placeholder}
          className="pr-10"
        />
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          className="absolute top-1/2 right-1 -translate-y-1/2"
          tabIndex={-1}
          aria-label={visible ? "Hide password" : "Show password"}
          onClick={() => setVisible((current) => !current)}
        >
          {visible ? <EyeSlashIcon /> : <EyeIcon />}
        </Button>
      </div>
      {hint ? <p className="text-xs text-muted-foreground">{hint}</p> : null}
    </div>
  );
}

export function LoginScreen() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [tab, setTab] = useState<AuthTab>("login");
  const [loginEmail, setLoginEmail] = useState("");
  const [loginPassword, setLoginPassword] = useState("");
  const [regEmail, setRegEmail] = useState("");
  const [regPassword, setRegPassword] = useState("");
  const [loginMsg, setLoginMsg] = useState<StatusMsg | null>(() =>
    searchParams.get("expired") === "1"
      ? { kind: "err", text: "Session expired. Please log in again." }
      : null,
  );
  const [regMsg, setRegMsg] = useState<StatusMsg | null>(null);
  const [loginPending, setLoginPending] = useState(false);
  const [regPending, setRegPending] = useState(false);
  const switchTimer = useRef<number | null>(null);

  useEffect(() => {
    const title = tab === "login" ? "InventoryIQ | Login" : "InventoryIQ | Sign up";
    document.title = title;
  }, [tab]);

  useEffect(() => {
    return () => {
      if (switchTimer.current !== null) window.clearTimeout(switchTimer.current);
    };
  }, []);

  function selectTab(next: unknown): void {
    setTab(next === "register" ? "register" : "login");
  }

  async function handleLogin(event: React.FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    const email = loginEmail.trim();
    const pwd = loginPassword;
    if (!email || !pwd) {
      const text = "Enter email & password.";
      setLoginMsg({ kind: "err", text });
      return;
    }
    setLoginPending(true);
    setLoginMsg({ kind: "info", text: "Logging in..." });
    let signedIn = false;
    try {
      const { status, data } = await authLogin(email, pwd);
      if (status === 200) {
        signedIn = true;
        setSessionToken(String(data.token));
        setUserEmail(String(data.email));
        try {
          const orgData = await getOrgs();
          const orgs = (orgData && orgData.orgs) || [];
          const first = orgs[0];
          if (first) {
            await switchOrg(first.orgID);
            if (first.name) setCurrentOrgName(first.name);
          }
        } catch {
          /* org endpoints not deployed yet */
        }
        const pendingInvite = getInviteToken();
        if (pendingInvite) {
          clearInviteToken();
          navigate(`/accept?token=${encodeURIComponent(pendingInvite)}`, { replace: true });
          return;
        }
        navigate(HOME_ROUTE, { replace: true });
        return;
      }
      const text = serverMessage(data, "Login failed.");
      setLoginMsg({ kind: "err", text });
    } catch {
      const text = "Network error. Please try again.";
      setLoginMsg({ kind: "err", text });
    } finally {
      if (!signedIn) setLoginPending(false);
    }
  }

  async function handleRegister(event: React.FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    const email = regEmail.trim();
    const pwd = regPassword;
    if (!email || !pwd) {
      const text = "Enter email & password.";
      setRegMsg({ kind: "err", text });
      return;
    }
    if (!PASSWORD_REGEX.test(pwd)) {
      const text = "Password must be 8+ chars with uppercase, lowercase, and a number.";
      setRegMsg({ kind: "err", text });
      return;
    }
    setRegPending(true);
    setRegMsg({ kind: "info", text: "Creating account..." });
    let created = false;
    try {
      const { status, data } = await authRegister(email, pwd);
      if (status === 200) {
        created = true;
        const text = "Account created!";
        setRegMsg({ kind: "ok", text });
        switchTimer.current = window.setTimeout(() => setTab("login"), 1500);
        return;
      }
      const text = serverMessage(data, "Registration failed.");
      setRegMsg({ kind: "err", text });
    } catch {
      const text = "Network error. Please try again.";
      setRegMsg({ kind: "err", text });
    } finally {
      if (!created) setRegPending(false);
    }
  }

  const title = tab === "login" ? "Welcome back" : "Create account";
  const subtitle =
    tab === "login"
      ? "Manage your inventory with precision"
      : "Start managing your inventory today";

  return (
    <main className="flex min-h-svh items-center justify-center bg-background px-6 py-10">
      <div className="flex w-full max-w-[400px] flex-col gap-6">
        <p className="text-center text-base font-semibold tracking-tight">InventoryIQ</p>
        <Card>
          <CardHeader>
            <CardTitle id="auth-title">{title}</CardTitle>
            <CardDescription id="auth-subtitle">{subtitle}</CardDescription>
          </CardHeader>
          <CardContent>
            <Tabs value={tab} onValueChange={selectTab} className="gap-5">
              <TabsList className="w-full">
                <TabsTrigger value="login">Log in</TabsTrigger>
                <TabsTrigger value="register">Sign up</TabsTrigger>
              </TabsList>
              <TabsContent value="login">
                <form className="flex flex-col gap-5" onSubmit={(event) => void handleLogin(event)}>
                  <div className="flex flex-col gap-2">
                    <Label htmlFor="login-email">Email address</Label>
                    <Input
                      id="login-email"
                      type="email"
                      autoComplete="email"
                      placeholder="name@company.com"
                      value={loginEmail}
                      onChange={(event) => setLoginEmail(event.target.value)}
                    />
                  </div>
                  <PasswordField
                    id="login-password"
                    label="Password"
                    value={loginPassword}
                    onChange={setLoginPassword}
                    autoComplete="current-password"
                    placeholder="••••••••"
                  />
                  <div className="flex justify-end">
                    <Link
                      to="/forgot-password"
                      className={cn(TEXT_LINK_CLASS, "text-sm")}
                    >
                      Forgot password?
                    </Link>
                  </div>
                  <Button type="submit" className="w-full" disabled={loginPending}>
                    Login
                  </Button>
                  <StatusAlert id="login-msg" msg={loginMsg} />
                  <p className="border-t pt-5 text-center text-sm text-muted-foreground">
                    Don&apos;t have an account?{" "}
                    <Button
                      type="button"
                      variant="link"
                      className="h-auto px-0"
                      onClick={() => setTab("register")}
                    >
                      Sign Up
                    </Button>
                  </p>
                </form>
              </TabsContent>
              <TabsContent value="register">
                <form className="flex flex-col gap-5" onSubmit={(event) => void handleRegister(event)}>
                  <div className="flex flex-col gap-2">
                    <Label htmlFor="reg-email">Email address</Label>
                    <Input
                      id="reg-email"
                      type="email"
                      autoComplete="email"
                      placeholder="name@company.com"
                      value={regEmail}
                      onChange={(event) => setRegEmail(event.target.value)}
                    />
                  </div>
                  <PasswordField
                    id="reg-password"
                    label="Password"
                    value={regPassword}
                    onChange={setRegPassword}
                    autoComplete="new-password"
                    placeholder="Create password"
                    hint="8+ chars with uppercase, lowercase, and a number."
                  />
                  <Button type="submit" className="w-full" disabled={regPending}>
                    Create Account
                  </Button>
                  <StatusAlert id="reg-msg" msg={regMsg} />
                  <p className="border-t pt-5 text-center text-sm text-muted-foreground">
                    Already have an account?{" "}
                    <Button
                      type="button"
                      variant="link"
                      className="h-auto px-0"
                      onClick={() => setTab("login")}
                    >
                      Log In
                    </Button>
                  </p>
                </form>
              </TabsContent>
            </Tabs>
          </CardContent>
        </Card>
      </div>
    </main>
  );
}
