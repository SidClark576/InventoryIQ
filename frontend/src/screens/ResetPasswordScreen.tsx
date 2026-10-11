import { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router";
import { EyeIcon, EyeSlashIcon } from "@phosphor-icons/react";
import { toast } from "sonner";
import { AUTH_ENDPOINT } from "@/config";
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

const PASSWORD_REGEX = /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).{8,}$/;

type MsgKind = "err" | "info" | "ok";

type StatusMsg = {
  kind: MsgKind;
  text: string;
};

function showToast(kind: MsgKind, text: string): void {
  if (kind === "err") toast.error(text);
  else if (kind === "ok") toast.success(text);
  else toast.info(text);
}

function PasswordField({
  id,
  label,
  value,
  onChange,
  placeholder,
  hint,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
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
          autoComplete="new-password"
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

export function ResetPasswordScreen() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token") || "";
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [msg, setMsg] = useState<StatusMsg | null>(null);
  const [invalid, setInvalid] = useState(!token);
  const [pending, setPending] = useState(false);
  const redirectTimer = useRef<number | null>(null);

  useEffect(() => {
    document.title = "InventoryIQ | Reset Password";
    return () => {
      if (redirectTimer.current !== null) window.clearTimeout(redirectTimer.current);
    };
  }, []);

  useEffect(() => {
    if (!token) setInvalid(true);
  }, [token]);

  async function handleReset(event: React.FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (!password || !confirm) {
      const text = "Both fields are required.";
      setMsg({ kind: "err", text });
      showToast("err", text);
      return;
    }
    if (password !== confirm) {
      const text = "Passwords do not match.";
      setMsg({ kind: "err", text });
      showToast("err", text);
      return;
    }
    if (!PASSWORD_REGEX.test(password)) {
      const text = "Password must be 8+ chars with uppercase, lowercase, and a number.";
      setMsg({ kind: "err", text });
      showToast("err", text);
      return;
    }
    setPending(true);
    setMsg({ kind: "info", text: "Resetting password..." });
    showToast("info", "Resetting password...");
    let succeeded = false;
    try {
      const res = await fetch(`${AUTH_ENDPOINT}/reset-password`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, newPassword: password }),
      });
      const data = (await res.json()) as { message?: unknown };
      if (res.status === 200) {
        succeeded = true;
        const text = "Password reset! Redirecting to login...";
        setMsg({ kind: "ok", text });
        showToast("ok", text);
        redirectTimer.current = window.setTimeout(() => {
          navigate("/login", { replace: true });
        }, 2000);
        return;
      }
      if (res.status === 400) {
        setInvalid(true);
        return;
      }
      const text = data.message ? String(data.message) : "Reset failed. Please try again.";
      setMsg({ kind: "err", text });
      showToast("err", text);
    } catch {
      const text = "Network error. Please try again.";
      setMsg({ kind: "err", text });
      showToast("err", text);
    } finally {
      if (!succeeded) setPending(false);
    }
  }

  return (
    <main className="flex min-h-svh items-center justify-center bg-background px-6 py-10">
      <div className="flex w-full max-w-[400px] flex-col gap-6">
        <p className="text-center text-base font-semibold tracking-tight">InventoryIQ</p>
        <Card>
          {invalid ? (
            <CardHeader className="items-center text-center">
              <CardTitle>Invalid or expired reset link.</CardTitle>
              <CardDescription>Reset links expire after 1 hour.</CardDescription>
              <Button type="button" className="mt-2" onClick={() => navigate("/forgot-password")}>
                Request New Link
              </Button>
            </CardHeader>
          ) : (
            <>
              <CardHeader>
                <CardTitle>Reset password</CardTitle>
                <CardDescription>Enter your new password below.</CardDescription>
              </CardHeader>
              <CardContent>
                <form id="reset-form" className="flex flex-col gap-5" onSubmit={(event) => void handleReset(event)}>
                  <PasswordField
                    id="rp-password"
                    label="New Password"
                    value={password}
                    onChange={setPassword}
                    placeholder="••••••••"
                    hint="Min 8 chars, uppercase, lowercase, and a number."
                  />
                  <PasswordField
                    id="rp-confirm"
                    label="Confirm Password"
                    value={confirm}
                    onChange={setConfirm}
                    placeholder="••••••••"
                  />
                  <Button type="submit" className="w-full" disabled={pending}>
                    Set New Password
                  </Button>
                  {msg ? (
                    <Alert id="rp-msg" variant={msg.kind === "err" ? "destructive" : "default"}>
                      <AlertTitle>{msg.text}</AlertTitle>
                    </Alert>
                  ) : null}
                </form>
              </CardContent>
            </>
          )}
        </Card>
      </div>
    </main>
  );
}
